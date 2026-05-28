from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import engine
from . import models
from .routers import auth, users, stations, trains, seats, ticket_prices, schedules, orders, waitlists

models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="台灣高鐵訂票系統 API",
    description="THSR Ticket Booking System — Database Final Project",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,          prefix="/auth",          tags=["Auth"])
app.include_router(users.router,         prefix="/users",         tags=["Users"])
app.include_router(stations.router,      prefix="/stations",      tags=["Stations"])
app.include_router(trains.router,        prefix="/trains",        tags=["Trains"])
app.include_router(seats.router,         prefix="/seats",         tags=["Seats"])
app.include_router(ticket_prices.router, prefix="/ticket-prices", tags=["Ticket Prices"])
app.include_router(schedules.router,     prefix="/schedules",     tags=["Schedules"])
app.include_router(orders.router,        prefix="/orders",        tags=["Orders"])
app.include_router(waitlists.router,     prefix="/waitlists",     tags=["Waitlists"])


@app.get("/", tags=["Health"])
def root():
    return {"message": "THSR Ticket Booking API is running"}
