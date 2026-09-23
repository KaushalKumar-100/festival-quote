import os
from datetime import date, datetime
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import Date, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./festivalquote.db")
ADMIN_KEY = os.getenv("ADMIN_KEY", "change-this-before-production")
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class Request(Base):
    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(30))
    email: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    city: Mapped[str] = mapped_column(String(100))
    service: Mapped[str] = mapped_column(String(80))
    event_date: Mapped[date] = mapped_column(Date)
    budget: Mapped[str] = mapped_column(String(60))
    details: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="new")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    city: Mapped[str] = mapped_column(String(100))
    service: Mapped[str] = mapped_column(String(80))
    phone: Mapped[str] = mapped_column(String(30))
    whatsapp: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    lead_fee: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[int] = mapped_column(Integer, default=1)


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(Integer)
    provider_id: Mapped[int] = mapped_column(Integer)
    price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    package: Mapped[str] = mapped_column(String(240), default="")
    availability: Mapped[str] = mapped_column(String(60), default="unknown")
    response_note: Mapped[str] = mapped_column(Text, default="")


Base.metadata.create_all(engine)

app = FastAPI(title="FestivalQuote API", version="0.1.0")

origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "*").split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def require_admin(x_admin_key: Optional[str] = Header(default=None)):
    if x_admin_key != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Admin key required")


class RequestIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=7, max_length=30)
    email: Optional[str] = None
    city: str = Field(min_length=2, max_length=100)
    service: str
    event_date: date
    budget: str
    details: str = ""


class ProviderIn(BaseModel):
    name: str
    city: str
    service: str
    phone: str
    whatsapp: Optional[str] = None
    source_url: Optional[str] = None
    notes: str = ""
    lead_fee: int = 0


class QuoteIn(BaseModel):
    request_id: int
    provider_id: int
    price: Optional[int] = None
    package: str = ""
    availability: str = "unknown"
    response_note: str = ""


@app.get("/api/health")
def health():
    return {"ok": True, "service": "FestivalQuote"}


@app.post("/api/requests")
def create_request(payload: RequestIn, session: Session = Depends(get_db)):
    item = Request(**payload.model_dump())
    session.add(item)
    session.commit()
    session.refresh(item)
    return {"id": item.id, "status": item.status}


@app.get("/api/requests")
def list_requests(_: None = Depends(require_admin), session: Session = Depends(get_db)):
    items = session.query(Request).order_by(Request.created_at.desc()).all()
    return [
        {
            "id": x.id,
            "name": x.name,
            "phone": x.phone,
            "email": x.email,
            "city": x.city,
            "service": x.service,
            "event_date": x.event_date.isoformat(),
            "budget": x.budget,
            "details": x.details,
            "status": x.status,
            "created_at": x.created_at.isoformat(),
        }
        for x in items
    ]


@app.patch("/api/requests/{request_id}/status")
def update_request_status(
    request_id: int,
    status: str,
    _: None = Depends(require_admin),
    session: Session = Depends(get_db),
):
    item = session.get(Request, request_id)
    if not item:
        raise HTTPException(status_code=404, detail="Request not found")
    item.status = status
    session.commit()
    return {"id": item.id, "status": item.status}


@app.post("/api/providers")
def create_provider(
    payload: ProviderIn,
    _: None = Depends(require_admin),
    session: Session = Depends(get_db),
):
    item = Provider(**payload.model_dump())
    session.add(item)
    session.commit()
    session.refresh(item)
    return {"id": item.id}


@app.get("/api/providers")
def list_providers(
    city: Optional[str] = None,
    service: Optional[str] = None,
    _: None = Depends(require_admin),
    session: Session = Depends(get_db),
):
    query = session.query(Provider).filter(Provider.active == 1)
    if city:
        query = query.filter(Provider.city.ilike(f"%{city}%"))
    if service:
        query = query.filter(Provider.service.ilike(f"%{service}%"))

    return [
        {
            "id": x.id,
            "name": x.name,
            "city": x.city,
            "service": x.service,
            "phone": x.phone,
            "whatsapp": x.whatsapp,
            "source_url": x.source_url,
            "notes": x.notes,
            "lead_fee": x.lead_fee,
        }
        for x in query.order_by(Provider.name).all()
    ]


@app.post("/api/quotes")
def create_quote(
    payload: QuoteIn,
    _: None = Depends(require_admin),
    session: Session = Depends(get_db),
):
    if not session.get(Request, payload.request_id):
        raise HTTPException(status_code=400, detail="Request not found")
    if not session.get(Provider, payload.provider_id):
        raise HTTPException(status_code=400, detail="Provider not found")

    item = Quote(**payload.model_dump())
    session.add(item)

    req = session.get(Request, payload.request_id)
    req.status = "quotes_ready"

    session.commit()
    session.refresh(item)
    return {"id": item.id}


@app.get("/api/requests/{request_id}/quotes")
def request_quotes(request_id: int, session: Session = Depends(get_db)):
    req = session.get(Request, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    rows = (
        session.query(Quote, Provider)
        .join(Provider, Provider.id == Quote.provider_id)
        .filter(Quote.request_id == request_id)
        .all()
    )

    return {
        "request": {
            "id": req.id,
            "city": req.city,
            "service": req.service,
            "event_date": req.event_date.isoformat(),
            "budget": req.budget,
        },
        "quotes": [
            {
                "id": q.id,
                "provider": p.name,
                "phone": p.phone,
                "whatsapp": p.whatsapp,
                "price": q.price,
                "package": q.package,
                "availability": q.availability,
                "response_note": q.response_note,
                "source_url": p.source_url,
            }
            for q, p in rows
        ],
    }


@app.get("/api/stats")
def stats(_: None = Depends(require_admin), session: Session = Depends(get_db)):
    total = session.query(Request).count()
    new = session.query(Request).filter(Request.status == "new").count()
    ready = session.query(Request).filter(Request.status == "quotes_ready").count()
    providers = session.query(Provider).filter(Provider.active == 1).count()
    return {
        "requests": total,
        "new": new,
        "quotes_ready": ready,
        "providers": providers,
    }
