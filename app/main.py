import asyncio
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .auth import decode_token
from .database import engine, SessionLocal
from . import models
from .routers import auth, users, stations, trains, seats, ticket_prices, schedules, orders, waitlists, admin


# ── Access logger ─────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("access.log", encoding="utf-8"),
    ],
)
_log = logging.getLogger("access")


# ── DB migration: add google_id column if not exists ──────────────────────────

def _upgrade_db():
    with engine.connect() as conn:
        conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS google_id VARCHAR(100) UNIQUE"
        ))
        conn.execute(text(
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS tgo_points_earned INTEGER DEFAULT 0"
        ))
        conn.commit()


# ── Background task: cancel unpaid orders older than 30 min ──────────────────

async def _auto_cancel_loop():
    while True:
        await asyncio.sleep(300)  # run every 5 minutes
        db = SessionLocal()
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
            expired = (
                db.query(models.Order)
                .filter(
                    models.Order.payment_status == "unpaid",
                    models.Order.created_at < cutoff,
                )
                .all()
            )
            if expired:
                for order in expired:
                    order.payment_status = "cancelled"
                    for ticket in order.tickets:
                        if ticket.ticket_status == "valid":
                            ticket.ticket_status = "refunded"
                db.commit()
                _log.info(f"[auto-cancel] Cancelled {len(expired)} expired order(s)")
        except Exception as exc:
            _log.error(f"[auto-cancel] Error: {exc}")
            db.rollback()
        finally:
            db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    models.Base.metadata.create_all(bind=engine)
    try:
        _upgrade_db()
    except Exception:
        pass  # column may already exist
    task = asyncio.create_task(_auto_cancel_loop())
    yield
    task.cancel()


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="台灣高鐵訂票系統 API",
    description="THSR Ticket Booking System — Database Final Project",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def access_log(request: Request, call_next):
    start = time.perf_counter()

    # Identify caller: decode JWT if present, else "anonymous"
    actor = "anonymous"
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        uid = decode_token(auth_header[7:])
        if uid:
            actor = f"user:{uid}"

    response = await call_next(request)

    ms = int((time.perf_counter() - start) * 1000)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _log.info(f"{now}  {actor:<12}  {request.method:<7}  {request.url.path:<45}  {response.status_code}  {ms}ms")

    return response


app.include_router(auth.router,          prefix="/auth",          tags=["Auth"])
app.include_router(users.router,         prefix="/users",         tags=["Users"])
app.include_router(stations.router,      prefix="/stations",      tags=["Stations"])
app.include_router(trains.router,        prefix="/trains",        tags=["Trains"])
app.include_router(seats.router,         prefix="/seats",         tags=["Seats"])
app.include_router(ticket_prices.router, prefix="/ticket-prices", tags=["Ticket Prices"])
app.include_router(schedules.router,     prefix="/schedules",     tags=["Schedules"])
app.include_router(orders.router,        prefix="/orders",        tags=["Orders"])
app.include_router(waitlists.router,     prefix="/waitlists",     tags=["Waitlists"])
app.include_router(admin.router,         prefix="/admin",         tags=["Admin"])


@app.get("/", tags=["Health"])
def root():
    return {"message": "THSR Ticket Booking API is running"}
