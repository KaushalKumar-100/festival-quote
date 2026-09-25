import hashlib
import secrets
from datetime import date

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from workers import asgi, fetch

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
        q = q.strip()[:100]
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
                  p.phone,p.whatsapp,p.source_url,p.lead_fee AS default_lead_fee
           FROM quotes q JOIN providers p ON p.id=q.provider_id
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
                  q.customer_selected,q.created_at,
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
    if quote["customer_selected"]:
        raise HTTPException(status_code=409, detail="This quote is locked after customer selection")
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


@app.patch("/api/quotes/{quote_id}/status")
async def update_quote_status(
    quote_id: int,
    payload: QuoteStatusIn,
    request: Request,
    x_admin_key: str | None = Header(default=None),
):
    admin_guard(request, x_admin_key)
    allowed = {"pending", "provider_responded", "contacted", "accepted", "rejected", "waived"}
    if payload.lead_status not in allowed:
        raise HTTPException(status_code=400, detail="Invalid lead status")
    database = db(request)
    quote = await database.prepare("SELECT id,customer_selected FROM quotes WHERE id=?").bind(quote_id).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    if quote["customer_selected"] and not payload.customer_selected:
        raise HTTPException(status_code=409, detail="Customer selection cannot be undone from the admin status control")
    await database.prepare("UPDATE quotes SET lead_status=?,customer_selected=? WHERE id=?").bind(payload.lead_status, int(payload.customer_selected), quote_id).run()
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
        (SELECT COUNT(*) FROM quotes) AS quotes"""
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
