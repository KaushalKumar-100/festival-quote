import base64
import hashlib
import hmac
import json
import secrets
from datetime import date

from workers import fetch

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from workers import asgi

app = FastAPI(title="FestivalQuote API", version="1.2.0")
Default = asgi.entrypoint(app)


def db(request: Request):
    return request.scope["env"].DB


def admin_guard(request: Request, x_admin_key: str | None):
    expected = getattr(request.scope["env"], "ADMIN_KEY", "")
    if not expected or x_admin_key != expected:
        raise HTTPException(status_code=401, detail="Invalid admin key")


async def rows(database, sql, *params):
    result = await database.prepare(sql).bind(*params).run()
    return result.results


def provider_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def provider_guard(request: Request, x_provider_token: str | None):
    if not x_provider_token or len(x_provider_token) > 256:
        raise HTTPException(status_code=401, detail="Provider access token required")
    provider = await db(request).prepare(
        """SELECT id,name,city,service,phone,whatsapp,active
           FROM providers WHERE portal_token_hash=?"""
    ).bind(provider_token_hash(x_provider_token)).first()
    if not provider:
        raise HTTPException(status_code=401, detail="Invalid provider access token")
    if not provider["active"]:
        raise HTTPException(status_code=403, detail="Provider access is inactive")
    return provider


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": "Something went wrong. Please try again."},
    )


class RequestIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=7, max_length=30)
    email: str | None = Field(default=None, max_length=254)
    city: str = Field(min_length=2, max_length=100)
    festival: str = Field(default="Other Festival", max_length=100)
    service: str = Field(min_length=2, max_length=100)
    event_date: date
    budget: str = Field(min_length=1, max_length=60)
    details: str = Field(default="", max_length=2000)


class ProviderIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    city: str = Field(min_length=2, max_length=100)
    service: str = Field(min_length=2, max_length=160)
    phone: str = Field(default="", max_length=30)
    whatsapp: str | None = Field(default=None, max_length=30)
    source_url: str | None = Field(default=None, max_length=500)
    notes: str = Field(default="", max_length=2000)
    lead_fee: int = Field(default=150, ge=0, le=100000)


class QuoteIn(BaseModel):
    request_id: int
    provider_id: int
    price: int | None = Field(default=None, ge=0)
    package: str = Field(default="", max_length=1000)
    availability: str = Field(default="unknown", max_length=40)
    response_note: str = Field(default="", max_length=2000)
    lead_fee: int = Field(default=0, ge=0, le=100000)


class QuoteStatusIn(BaseModel):
    lead_status: str
    customer_selected: bool = False
    provider_paid: bool = False


class PaymentCreateIn(BaseModel):
    amount: int | None = Field(default=None, ge=1, le=1000000)
    payment_url: str | None = Field(default=None, max_length=1000)


class PaymentStatusIn(BaseModel):
    status: str
    reference: str = Field(default="", max_length=160)
    payment_url: str | None = Field(default=None, max_length=1000)
    failure_reason: str = Field(default="", max_length=500)


@app.get("/api/health")
async def health():
    return {"ok": True, "service": "FestivalQuote", "environment": "cloudflare-workers"}


@app.post("/api/requests")
async def create_request(payload: RequestIn, request: Request):
    database = db(request)
    token = secrets.token_urlsafe(18)
    result = await database.prepare(
        """INSERT INTO requests
        (name,phone,email,city,festival,service,event_date,budget,details,status,tracking_token)
        VALUES (?,?,?,?,?,?,?,?,?,'new',?)"""
    ).bind(
        payload.name, payload.phone, payload.email, payload.city, payload.festival,
        payload.service, payload.event_date.isoformat(), payload.budget,
        payload.details, token
    ).run()
    return {
        "id": result.meta.last_row_id,
        "status": "new",
        "tracking_token": token,
        "tracking_path": f"/track.html?id={result.meta.last_row_id}&token={token}",
    }


@app.get("/api/requests")
async def list_requests(
    request: Request,
    status: str | None = None,
    city: str | None = None,
    q: str | None = None,
    x_admin_key: str | None = Header(default=None),
):
    admin_guard(request, x_admin_key)
    database = db(request)
    sql = """SELECT r.*, (SELECT COUNT(*) FROM quotes q WHERE q.request_id=r.id) AS quote_count
             FROM requests r WHERE 1=1"""
    params: list[str] = []
    if status:
        sql += " AND r.status=?"
        params.append(status)
    if city:
        sql += " AND r.city LIKE ?"
        params.append(f"%{city}%")
    if q:
        sql += " AND (r.name LIKE ? OR r.phone LIKE ? OR r.service LIKE ? OR r.festival LIKE ?)"
        params.extend([f"%{q}%"] * 4)
    sql += " ORDER BY r.created_at DESC LIMIT 300"
    items = await rows(database, sql, *params)
    for item in items:
        item["tracking_path"] = (
            f"/track.html?id={item['id']}&token={item['tracking_token']}"
        )
    return items


@app.get("/api/requests/{request_id}")
async def request_detail(
    request_id: int,
    request: Request,
    x_admin_key: str | None = Header(default=None),
):
    admin_guard(request, x_admin_key)
    database = db(request)
    req = await database.prepare("SELECT * FROM requests WHERE id=?").bind(request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    req["tracking_path"] = f"/track.html?id={req['id']}&token={req['tracking_token']}"
    quotes = await rows(
        database,
        """SELECT q.*,p.name AS provider,p.city AS provider_city,p.service AS provider_service,
                  p.phone,p.whatsapp,p.source_url,p.lead_fee AS default_lead_fee,
                  lp.id AS payment_id,lp.status AS payment_status,lp.payment_url
           FROM quotes q JOIN providers p ON p.id=q.provider_id
           LEFT JOIN lead_payments lp ON lp.quote_id=q.id
           WHERE q.request_id=? ORDER BY q.created_at DESC""",
        request_id,
    )
    return {"request": req, "quotes": quotes}


@app.patch("/api/requests/{request_id}/status")
async def update_request_status(
    request_id: int,
    status: str,
    request: Request,
    x_admin_key: str | None = Header(default=None),
):
    admin_guard(request, x_admin_key)
    allowed = {"new", "sourcing", "quotes_ready", "customer_contacted", "booked", "closed", "cancelled"}
    if status not in allowed:
        raise HTTPException(status_code=400, detail="Invalid status")
    database = db(request)
    result = await database.prepare("UPDATE requests SET status=? WHERE id=?").bind(status, request_id).run()
    if not result.meta.changes:
        raise HTTPException(status_code=404, detail="Request not found")
    return {"id": request_id, "status": status}


@app.post("/api/providers")
async def create_provider(
    payload: ProviderIn,
    request: Request,
    x_admin_key: str | None = Header(default=None),
):
    admin_guard(request, x_admin_key)
    result = await db(request).prepare(
        """INSERT INTO providers
        (name,city,service,phone,whatsapp,source_url,notes,lead_fee,active)
        VALUES (?,?,?,?,?,?,?,?,1)"""
    ).bind(
        payload.name, payload.city, payload.service, payload.phone,
        payload.whatsapp, payload.source_url, payload.notes, payload.lead_fee
    ).run()
    return {"id": result.meta.last_row_id}


@app.post("/api/providers/{provider_id}/portal-link")
async def create_provider_portal_link(
    provider_id: int,
    request: Request,
    x_admin_key: str | None = Header(default=None),
):
    admin_guard(request, x_admin_key)
    database = db(request)
    provider = await database.prepare(
        "SELECT id,active FROM providers WHERE id=?"
    ).bind(provider_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    if not provider["active"]:
        raise HTTPException(status_code=409, detail="Activate the provider before creating an access link")

    token = secrets.token_urlsafe(32)
    token_hash = provider_token_hash(token)
    await database.prepare(
        "UPDATE providers SET portal_token_hash=?,portal_token_created_at=CURRENT_TIMESTAMP WHERE id=?"
    ).bind(token_hash, provider_id).run()

    return {
        "provider_id": provider_id,
        "portal_path": f"/provider.html#token={token}",
        "rotated": True,
    }

@app.get("/api/providers")
async def list_providers(
    request: Request,
    city: str | None = None,
    service: str | None = None,
    include_inactive: bool = False,
    x_admin_key: str | None = Header(default=None),
):
    admin_guard(request, x_admin_key)
    database = db(request)
    sql = """SELECT id,name,city,service,phone,whatsapp,source_url,notes,lead_fee,active,created_at,portal_token_created_at FROM providers WHERE 1=1"""
    params: list[str] = []
    if not include_inactive:
        sql += " AND active=1"
    if city:
        sql += " AND city LIKE ?"
        params.append(f"%{city}%")
    if service:
        sql += " AND service LIKE ?"
        params.append(f"%{service}%")
    sql += " ORDER BY active DESC,name LIMIT 500"
    return await rows(database, sql, *params)


@app.patch("/api/providers/{provider_id}/active")
async def toggle_provider(
    provider_id: int,
    active: bool,
    request: Request,
    x_admin_key: str | None = Header(default=None),
):
    admin_guard(request, x_admin_key)
    database = db(request)
    result = await database.prepare("UPDATE providers SET active=? WHERE id=?").bind(int(active), provider_id).run()
    if not result.meta.changes:
        raise HTTPException(status_code=404, detail="Provider not found")
    return {"id": provider_id, "active": active}


class ProviderQuoteResponseIn(BaseModel):
    price: int | None = Field(default=None, ge=0)
    package: str = Field(default="", max_length=1000)
    availability: str = Field(default="available", max_length=40)
    response_note: str = Field(default="", max_length=2000)


@app.get("/api/provider/portal")
async def provider_portal(
    request: Request,
    x_provider_token: str | None = Header(default=None),
):
    provider = await provider_guard(request, x_provider_token)
    quotes = await rows(
        db(request),
        """SELECT q.id,q.price,q.package,q.availability,q.response_note,q.lead_status,
                  q.customer_selected,q.provider_paid,q.created_at,
                  r.id AS request_id,r.festival,r.service,r.event_date,r.budget,r.details,r.city
           FROM quotes q JOIN requests r ON r.id=q.request_id
           WHERE q.provider_id=?
           ORDER BY q.created_at DESC LIMIT 100"""
        , provider["id"],
    )
    return {
        "provider": {"id": provider["id"], "name": provider["name"], "city": provider["city"], "service": provider["service"]},
        "quotes": quotes,
    }


@app.patch("/api/provider/quotes/{quote_id}")
async def provider_update_quote(
    quote_id: int,
    payload: ProviderQuoteResponseIn,
    request: Request,
    x_provider_token: str | None = Header(default=None),
):
    provider = await provider_guard(request, x_provider_token)
    if payload.availability not in {"available", "limited", "unavailable", "unknown"}:
        raise HTTPException(status_code=400, detail="Invalid availability")
    database = db(request)
    quote = await database.prepare(
        """SELECT id,customer_selected,provider_paid
           FROM quotes WHERE id=? AND provider_id=?"""
    ).bind(quote_id, provider["id"]).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    if quote["customer_selected"] or quote["provider_paid"]:
        raise HTTPException(status_code=409, detail="This quote is locked after customer selection or payment")
    await database.prepare(
        """UPDATE quotes
           SET price=?,package=?,availability=?,response_note=?,lead_status='provider_responded'
           WHERE id=? AND provider_id=?"""
    ).bind(payload.price,payload.package,payload.availability,payload.response_note,quote_id,provider["id"]).run()
    await database.prepare(
        "UPDATE requests SET status='quotes_ready' WHERE id=(SELECT request_id FROM quotes WHERE id=?)"
    ).bind(quote_id).run()
    return {"id": quote_id, "updated": True, "lead_status": "provider_responded"}

@app.post("/api/quotes")
async def create_quote(
    payload: QuoteIn,
    request: Request,
    x_admin_key: str | None = Header(default=None),
):
    admin_guard(request, x_admin_key)
    database = db(request)
    req = await database.prepare("SELECT id FROM requests WHERE id=?").bind(payload.request_id).first()
    provider = await database.prepare("SELECT id,lead_fee,active FROM providers WHERE id=?").bind(payload.provider_id).first()
    if not req:
        raise HTTPException(status_code=400, detail="Request not found")
    if not provider:
        raise HTTPException(status_code=400, detail="Provider not found")
    if not provider["active"]:
        raise HTTPException(status_code=409, detail="Provider is inactive")
    fee = payload.lead_fee if payload.lead_fee else int(provider["lead_fee"] or 0)
    result = await database.prepare(
        """INSERT INTO quotes
        (request_id,provider_id,price,package,availability,response_note,lead_fee,lead_status)
        VALUES (?,?,?,?,?,?,?,'pending')"""
    ).bind(
        payload.request_id, payload.provider_id, payload.price, payload.package,
        payload.availability, payload.response_note, fee
    ).run()
    await database.prepare("UPDATE requests SET status='quotes_ready' WHERE id=?").bind(payload.request_id).run()
    return {"id": result.meta.last_row_id, "lead_fee": fee}


@app.get("/api/payments")
async def list_payments(
    request: Request,
    status: str | None = None,
    x_admin_key: str | None = Header(default=None),
):
    admin_guard(request, x_admin_key)
    database = db(request)
    sql = """SELECT lp.id,lp.quote_id,lp.provider_id,lp.amount,lp.currency,lp.status,
                    lp.gateway,lp.gateway_payment_link_id,lp.gateway_payment_id,
                    lp.payment_url,lp.reference_id,lp.failure_reason,lp.created_at,lp.paid_at,
                    p.name AS provider,p.phone,q.request_id,q.customer_selected,q.lead_status,
                    r.name AS customer,r.city,r.service,r.festival
             FROM lead_payments lp
             JOIN providers p ON p.id=lp.provider_id
             JOIN quotes q ON q.id=lp.quote_id
             JOIN requests r ON r.id=q.request_id
             WHERE 1=1"""
    params: list[str] = []
    if status:
        sql += " AND lp.status=?"
        params.append(status)
    sql += " ORDER BY lp.created_at DESC LIMIT 300"
    return await rows(database, sql, *params)


@app.post("/api/quotes/{quote_id}/payment")
async def create_lead_payment(
    quote_id: int,
    payload: PaymentCreateIn,
    request: Request,
    x_admin_key: str | None = Header(default=None),
):
    admin_guard(request, x_admin_key)
    database = db(request)
    quote = await database.prepare(
        """SELECT q.id,q.request_id,q.provider_id,q.lead_fee,q.customer_selected,q.provider_paid,
                  p.name AS provider,p.phone,r.name AS customer
           FROM quotes q JOIN providers p ON p.id=q.provider_id
           JOIN requests r ON r.id=q.request_id WHERE q.id=?"""
    ).bind(quote_id).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    if not quote["customer_selected"]:
        raise HTTPException(status_code=409, detail="Customer must select the quote before lead payment is requested")
    if quote["provider_paid"]:
        raise HTTPException(status_code=409, detail="Lead fee is already paid")
    existing = await database.prepare("SELECT * FROM lead_payments WHERE quote_id=?").bind(quote_id).first()
    if existing:
        return {k: existing[k] for k in ("id","status","amount","payment_url","reference_id","gateway")}
    amount = int(payload.amount or quote["lead_fee"] or 0)
    if amount < 1:
        raise HTTPException(status_code=400, detail="Lead fee must be greater than zero")
    reference_id = f"FQ-Q{quote_id}-{secrets.token_hex(4)}"
    gateway = "manual"
    payment_url = payload.payment_url
    gateway_link_id = None
    key_id = getattr(request.scope["env"], "RAZORPAY_KEY_ID", "")
    key_secret = getattr(request.scope["env"], "RAZORPAY_KEY_SECRET", "")
    if key_id and key_secret and not payment_url:
        auth = base64.b64encode(f"{key_id}:{key_secret}".encode()).decode()
        body = {"amount": amount * 100, "currency": "INR", "reference_id": reference_id,
                "description": f"FestivalQuote lead fee for quote #{quote_id}",
                "customer": {"name": quote["provider"], "contact": quote["phone"] or ""},
                "notify": {"sms": True}, "reminder_enable": True}
        response = await fetch("https://api.razorpay.com/v1/payment_links", method="POST",
            headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
            body=json.dumps(body))
        if not response.ok:
            raise HTTPException(status_code=502, detail="Payment gateway could not create the payment link")
        data = await response.json()
        payment_url = data.get("short_url")
        gateway_link_id = data.get("id")
        gateway = "razorpay"
        if not payment_url or not gateway_link_id:
            raise HTTPException(status_code=502, detail="Payment gateway returned an incomplete payment link")
    await database.prepare(
        """INSERT INTO lead_payments
           (quote_id,provider_id,amount,status,gateway,gateway_payment_link_id,payment_url,reference_id)
           VALUES (?,?,?,"pending",?,?,?,?,?)"""
    ).bind(quote_id,quote["provider_id"],amount,gateway,gateway_link_id,payment_url,reference_id).run()
    payment = await database.prepare("SELECT * FROM lead_payments WHERE quote_id=?").bind(quote_id).first()
    return {k: payment[k] for k in ("id","status","amount","payment_url","reference_id","gateway")}


@app.patch("/api/payments/{payment_id}/status")
async def update_payment_status(
    payment_id: int,
    payload: PaymentStatusIn,
    request: Request,
    x_admin_key: str | None = Header(default=None),
):
    admin_guard(request, x_admin_key)
    allowed = {"pending","paid","failed","waived","refunded"}
    if payload.status not in allowed:
        raise HTTPException(status_code=400, detail="Invalid payment status")
    if payload.status == "paid" and len(payload.reference.strip()) < 2:
        raise HTTPException(status_code=400, detail="Payment reference is required when marking a payment paid")
    database = db(request)
    payment = await database.prepare("SELECT id,quote_id,status FROM lead_payments WHERE id=?").bind(payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment["status"] == "paid" and payload.status not in {"paid","refunded"}:
        raise HTTPException(status_code=409, detail="Paid payments cannot move back to pending or failed")
    if payload.status == "paid":
        await database.prepare("""UPDATE lead_payments SET status="paid",gateway_payment_id=COALESCE(gateway_payment_id,?),
            failure_reason="",paid_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?""" ).bind(payload.reference.strip(),payment_id).run()
        await database.prepare('UPDATE quotes SET provider_paid=1,lead_status=? WHERE id=?').bind('paid',payment['quote_id']).run()
    elif payload.status == "refunded":
        await database.prepare("""UPDATE lead_payments SET status="refunded",updated_at=CURRENT_TIMESTAMP WHERE id=?""" ).bind(payment_id).run()
        await database.prepare("UPDATE quotes SET provider_paid=0 WHERE id=?").bind(payment["quote_id"]).run()
    else:
        await database.prepare(
            "UPDATE lead_payments SET status=?,payment_url=COALESCE(?,payment_url),failure_reason=?,updated_at=CURRENT_TIMESTAMP WHERE id=?"
        ).bind(payload.status,payload.payment_url,payload.failure_reason.strip(),payment_id).run()
    return {"id": payment_id, "status": payload.status}


@app.post("/api/webhooks/razorpay")
async def razorpay_webhook(request: Request):
    secret = getattr(request.scope["env"], "RAZORPAY_WEBHOOK_SECRET", "")
    signature = request.headers.get("X-Razorpay-Signature", "")
    if not secret or not signature:
        raise HTTPException(status_code=401, detail="Webhook authentication failed")
    body = await request.body()
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Webhook authentication failed")
    payload = json.loads(body)
    if payload.get("event") != "payment_link.paid":
        return {"received": True}
    entity = payload.get("payload",{}).get("payment_link",{}).get("entity",{})
    link_id = entity.get("id")
    payments = entity.get("payments") or []
    payment_id = payments[0].get("payment_id") if payments else None
    if not link_id:
        return {"received": True}
    database = db(request)
    payment = await database.prepare("SELECT id,quote_id FROM lead_payments WHERE gateway_payment_link_id=?").bind(link_id).first()
    if not payment:
        return {"received": True}
    await database.prepare("""UPDATE lead_payments SET status="paid",gateway_payment_id=COALESCE(?,gateway_payment_id),
        paid_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?""" ).bind(payment_id,payment["id"]).run()
    await database.prepare('UPDATE quotes SET provider_paid=1,lead_status=? WHERE id=?').bind('paid',payment['quote_id']).run()
    return {"received": True}

@app.patch("/api/quotes/{quote_id}/status")
async def update_quote_status(
    quote_id: int,
    payload: QuoteStatusIn,
    request: Request,
    x_admin_key: str | None = Header(default=None),
):
    admin_guard(request, x_admin_key)
    allowed = {"pending", "provider_responded", "contacted", "accepted", "rejected", "paid", "waived"}
    if payload.lead_status not in allowed:
        raise HTTPException(status_code=400, detail="Invalid lead status")
    database = db(request)
    result = await database.prepare(
        "UPDATE quotes SET lead_status=?,customer_selected=?,provider_paid=? WHERE id=?"
    ).bind(
        payload.lead_status, int(payload.customer_selected), int(payload.provider_paid), quote_id
    ).run()
    if not result.meta.changes:
        raise HTTPException(status_code=404, detail="Quote not found")
    return {"id": quote_id, **payload.model_dump()}


@app.get("/api/track")
async def track_request(request: Request, id: int, token: str):
    database = db(request)
    req = await database.prepare(
        """SELECT id,name,phone,email,city,festival,service,event_date,budget,details,status,created_at
           FROM requests WHERE id=? AND tracking_token=?"""
    ).bind(id, token).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    quotes = await rows(
        database,
        """SELECT q.id,q.price,q.package,q.availability,q.response_note,
                  p.name AS provider,p.phone,p.whatsapp,p.source_url
           FROM quotes q JOIN providers p ON p.id=q.provider_id
           WHERE q.request_id=? ORDER BY q.price IS NULL,q.price ASC""",
        id,
    )
    return {"request": req, "quotes": quotes}


class RequestUpdateIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=7, max_length=30)
    email: str | None = Field(default=None, max_length=254)
    city: str = Field(min_length=2, max_length=100)
    festival: str = Field(default="Other Festival", max_length=100)
    service: str = Field(min_length=2, max_length=100)
    event_date: date
    budget: str = Field(min_length=1, max_length=60)
    details: str = Field(default="", max_length=2000)


@app.patch("/api/requests/{request_id}")
async def update_request(
    request_id: int,
    payload: RequestUpdateIn,
    request: Request,
    x_request_token: str | None = Header(default=None),
):
    if not x_request_token:
        raise HTTPException(status_code=401, detail="Request token required")
    database = db(request)
    existing = await database.prepare(
        "SELECT id FROM requests WHERE id=? AND tracking_token=?"
    ).bind(request_id, x_request_token).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Request not found")
    await database.prepare(
        """UPDATE requests
           SET name=?,phone=?,email=?,city=?,festival=?,service=?,event_date=?,budget=?,details=?
           WHERE id=? AND tracking_token=?"""
    ).bind(
        payload.name, payload.phone, payload.email, payload.city, payload.festival,
        payload.service, payload.event_date.isoformat(), payload.budget, payload.details,
        request_id, x_request_token
    ).run()
    return {"id": request_id, "updated": True}


@app.get("/api/stats")
async def stats(request: Request, x_admin_key: str | None = Header(default=None)):
    admin_guard(request, x_admin_key)
    database = db(request)
    counts = await database.prepare(
        """SELECT
        (SELECT COUNT(*) FROM requests) AS requests,
        (SELECT COUNT(*) FROM requests WHERE status='new') AS new,
        (SELECT COUNT(*) FROM requests WHERE status='sourcing') AS sourcing,
        (SELECT COUNT(*) FROM requests WHERE status='quotes_ready') AS quotes_ready,
        (SELECT COUNT(*) FROM requests WHERE status='booked') AS booked,
        (SELECT COUNT(*) FROM providers WHERE active=1) AS providers,
        (SELECT COUNT(*) FROM quotes) AS quotes,
        (SELECT COUNT(*) FROM lead_payments WHERE status='pending') AS payments_pending,
        (SELECT COUNT(*) FROM lead_payments WHERE status='paid') AS payments_paid,
        (SELECT COALESCE(SUM(amount),0) FROM lead_payments WHERE status='paid') AS revenue"""
    ).first()
    return counts


@app.get("/api/providers/match")
async def match_providers(
    request: Request,
    city: str,
    service: str,
    x_admin_key: str | None = Header(default=None),
):
    admin_guard(request, x_admin_key)
    return await rows(
        db(request),
        """SELECT * FROM providers WHERE active=1
           AND city LIKE ? AND service LIKE ?
           ORDER BY lead_fee ASC,name ASC LIMIT 20""",
        f"%{city}%", f"%{service}%"
    )


@app.get("/{path:path}")
async def frontend(path: str, request: Request):
    asset_url = "https://assets.local/" + path
    response = await request.scope["env"].ASSETS.fetch(asset_url)
    body = await response.bytes()
    return Response(content=body, status_code=response.status, headers=dict(response.headers))
