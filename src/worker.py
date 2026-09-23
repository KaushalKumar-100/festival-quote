import os
from datetime import date
from urllib.parse import urlparse

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from workers import asgi

app = FastAPI(title="FestivalQuote API", version="0.2.0")
Default = asgi.entrypoint(app)


def db(request: Request):
    return request.scope["env"].DB


def admin_guard(request: Request, x_admin_key: str | None):
    expected = getattr(request.scope["env"], "ADMIN_KEY", "")
    if not expected or x_admin_key != expected:
        raise HTTPException(status_code=401, detail="Admin key required")


class RequestIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=7, max_length=30)
    email: str | None = None
    city: str = Field(min_length=2, max_length=100)
    service: str = Field(min_length=2, max_length=100)
    event_date: date
    budget: str = Field(min_length=1, max_length=60)
    details: str = Field(default="", max_length=2000)


class ProviderIn(BaseModel):
    name: str
    city: str
    service: str
    phone: str = ""
    whatsapp: str | None = None
    source_url: str | None = None
    notes: str = ""
    lead_fee: int = 0


class QuoteIn(BaseModel):
    request_id: int
    provider_id: int
    price: int | None = None
    package: str = ""
    availability: str = "unknown"
    response_note: str = ""


async def query(database, sql, *params):
    result = await database.prepare(sql).bind(*params).run()
    return result.results


@app.get("/api/health")
async def health():
    return {"ok": True, "service": "FestivalQuote", "environment": "cloudflare-workers"}


@app.post("/api/requests")
async def create_request(payload: RequestIn, request: Request):
    database = db(request)
    result = await database.prepare(
        """INSERT INTO requests
        (name, phone, email, city, service, event_date, budget, details, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'new')"""
    ).bind(
        payload.name, payload.phone, payload.email, payload.city, payload.service,
        payload.event_date.isoformat(), payload.budget, payload.details
    ).run()
    return {"id": result.meta.last_row_id, "status": "new"}


@app.get("/api/requests")
async def list_requests(request: Request, x_admin_key: str | None = Header(default=None)):
    admin_guard(request, x_admin_key)
    rows = await query(
        db(request),
        """SELECT id,name,phone,email,city,service,event_date,budget,details,status,created_at
        FROM requests ORDER BY created_at DESC LIMIT 200"""
    )
    return rows


@app.patch("/api/requests/{request_id}/status")
async def update_request_status(
    request_id: int,
    status: str,
    request: Request,
    x_admin_key: str | None = Header(default=None),
):
    admin_guard(request, x_admin_key)
    allowed = {"new", "sourcing", "quotes_ready", "customer_contacted", "booked", "closed"}
    if status not in allowed:
        raise HTTPException(status_code=400, detail="Invalid status")
    await query(db(request), "UPDATE requests SET status=? WHERE id=?", status, request_id)
    return {"id": request_id, "status": status}


@app.post("/api/providers")
async def create_provider(
    payload: ProviderIn,
    request: Request,
    x_admin_key: str | None = Header(default=None),
):
    admin_guard(x_admin_key)
    result = await db(request).prepare(
        """INSERT INTO providers
        (name,city,service,phone,whatsapp,source_url,notes,lead_fee,active)
        VALUES (?,?,?,?,?,?,?,?,1)"""
    ).bind(
        payload.name, payload.city, payload.service, payload.phone,
        payload.whatsapp, payload.source_url, payload.notes, payload.lead_fee
    ).run()
    return {"id": result.meta.last_row_id}


@app.get("/api/providers")
async def list_providers(
    request: Request,
    city: str | None = None,
    service: str | None = None,
    x_admin_key: str | None = Header(default=None),
):
    admin_guard(x_admin_key)
    database = db(request)
    if city and service:
        rows = await query(database, "SELECT * FROM providers WHERE active=1 AND city LIKE ? AND service LIKE ? ORDER BY name", f"%{city}%", f"%{service}%")
    elif city:
        rows = await query(database, "SELECT * FROM providers WHERE active=1 AND city LIKE ? ORDER BY name", f"%{city}%")
    elif service:
        rows = await query(database, "SELECT * FROM providers WHERE active=1 AND service LIKE ? ORDER BY name", f"%{service}%")
    else:
        rows = await query(database, "SELECT * FROM providers WHERE active=1 ORDER BY name LIMIT 500")
    return rows


@app.post("/api/quotes")
async def create_quote(
    payload: QuoteIn,
    request: Request,
    x_admin_key: str | None = Header(default=None),
):
    admin_guard(x_admin_key)
    database = db(request)
    request_row = await database.prepare("SELECT id FROM requests WHERE id=?").bind(payload.request_id).first()
    provider_row = await database.prepare("SELECT id FROM providers WHERE id=?").bind(payload.provider_id).first()
    if not request_row:
        raise HTTPException(status_code=400, detail="Request not found")
    if not provider_row:
        raise HTTPException(status_code=400, detail="Provider not found")

    result = await database.prepare(
        """INSERT INTO quotes
        (request_id,provider_id,price,package,availability,response_note)
        VALUES (?,?,?,?,?,?)"""
    ).bind(
        payload.request_id, payload.provider_id, payload.price, payload.package,
        payload.availability, payload.response_note
    ).run()

    await database.prepare("UPDATE requests SET status='quotes_ready' WHERE id=?").bind(payload.request_id).run()
    return {"id": result.meta.last_row_id}


@app.get("/api/requests/{request_id}/quotes")
async def request_quotes(request_id: int, request: Request):
    database = db(request)
    req = await database.prepare(
        "SELECT id,city,service,event_date,budget,status FROM requests WHERE id=?"
    ).bind(request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    rows = await query(
        database,
        """SELECT q.id,q.price,q.package,q.availability,q.response_note,
        p.name AS provider,p.phone,p.whatsapp,p.source_url
        FROM quotes q JOIN providers p ON p.id=q.provider_id
        WHERE q.request_id=? ORDER BY q.price IS NULL, q.price ASC""",
        request_id,
    )
    return {"request": req, "quotes": rows}


@app.get("/api/stats")
async def stats(request: Request, x_admin_key: str | None = Header(default=None)):
    admin_guard(x_admin_key)
    database = db(request)
    counts = await database.prepare(
        """SELECT
        (SELECT COUNT(*) FROM requests) AS requests,
        (SELECT COUNT(*) FROM requests WHERE status='new') AS new,
        (SELECT COUNT(*) FROM requests WHERE status='quotes_ready') AS quotes_ready,
        (SELECT COUNT(*) FROM providers WHERE active=1) AS providers,
        (SELECT COUNT(*) FROM quotes) AS quotes"""
    ).first()
    return counts


@app.get("/{path:path}")
async def frontend(path: str, request: Request):
    asset_url = "https://assets.local/" + path
    response = await request.scope["env"].ASSETS.fetch(asset_url)
    body = await response.bytes()
    return Response(content=body, status_code=response.status, headers=dict(response.headers))
