from pydantic import BaseModel, EmailStr, field_validator
from datetime import datetime, date, time
from typing import Optional, List
from decimal import Decimal


# ── Auth ──────────────────────────────────────────────────────────────────────

class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    user_id: Optional[int] = None


# ── Users ─────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str
    phone: str
    user_type: str = "general"

    @field_validator("user_type")
    @classmethod
    def validate_user_type(cls, v: str) -> str:
        if v not in ("general", "corporate", "admin"):
            raise ValueError("user_type must be general, corporate, or admin")
        return v


class UserUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None


class UserResponse(BaseModel):
    user_id: int
    email: str
    name: str
    phone: str
    user_type: str
    tgo_balance: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Stations ──────────────────────────────────────────────────────────────────

class StationCreate(BaseModel):
    station_name: str
    sequence_no: int
    latitude: Optional[Decimal] = None
    longitude: Optional[Decimal] = None


class StationResponse(BaseModel):
    station_id: int
    station_name: str
    sequence_no: int
    latitude: Optional[Decimal]
    longitude: Optional[Decimal]

    model_config = {"from_attributes": True}


# ── Trains ────────────────────────────────────────────────────────────────────

class TrainCreate(BaseModel):
    train_no: str
    train_type: str
    total_carriages: int = 12


class TrainResponse(BaseModel):
    train_no: str
    train_type: str
    total_carriages: int

    model_config = {"from_attributes": True}


# ── Seats ─────────────────────────────────────────────────────────────────────

class SeatResponse(BaseModel):
    seat_id: int
    carriage_no: int
    row_no: int
    seat_letter: str
    is_business_class: bool

    model_config = {"from_attributes": True}


# ── Ticket Prices ─────────────────────────────────────────────────────────────

class TicketPriceCreate(BaseModel):
    start_station_id: int
    end_station_id: int
    is_business: bool = False
    base_price: int


class TicketPriceResponse(BaseModel):
    price_id: int
    start_station_id: int
    end_station_id: int
    is_business: bool
    base_price: int
    start_station: Optional[StationResponse] = None
    end_station: Optional[StationResponse] = None

    model_config = {"from_attributes": True}


# ── Stop Times ────────────────────────────────────────────────────────────────

class StopTimeCreate(BaseModel):
    station_id: int
    arrival_time: Optional[time] = None
    departure_time: Optional[time] = None


class StopTimeResponse(BaseModel):
    stop_id: int
    schedule_id: int
    station_id: int
    arrival_time: Optional[time]
    departure_time: Optional[time]
    station: Optional[StationResponse] = None

    model_config = {"from_attributes": True}


# ── Early Bird Pools ──────────────────────────────────────────────────────────

class EarlyBirdPoolCreate(BaseModel):
    discount_rate: Decimal
    initial_quota: int
    available_quota: int


class EarlyBirdPoolResponse(BaseModel):
    pool_id: int
    schedule_id: int
    discount_rate: Decimal
    initial_quota: int
    available_quota: int

    model_config = {"from_attributes": True}


# ── Schedules ─────────────────────────────────────────────────────────────────

class ScheduleCreate(BaseModel):
    train_no: str
    departure_date: date
    non_reserved_start_carriage: int = 10
    stop_times: List[StopTimeCreate] = []


class ScheduleResponse(BaseModel):
    schedule_id: int
    train_no: str
    departure_date: date
    non_reserved_start_carriage: int
    train: Optional[TrainResponse] = None

    model_config = {"from_attributes": True}


class ScheduleWithStops(ScheduleResponse):
    stop_times: List[StopTimeResponse] = []
    early_bird_pools: List[EarlyBirdPoolResponse] = []


class ScheduleSearchResult(BaseModel):
    """Enriched result for schedule search — includes origin departure and destination arrival."""
    schedule_id: int
    train_no: str
    train_type: str
    departure_date: date
    non_reserved_start_carriage: int
    origin_departure_time: Optional[time]
    destination_arrival_time: Optional[time]
    available_seats: Optional[int] = None

    model_config = {"from_attributes": True}


# ── Orders ────────────────────────────────────────────────────────────────────

VALID_TICKET_TYPES = {"全票", "早鳥", "大學生", "敬老", "愛心", "愛陪", "兒童"}


class TicketCreate(BaseModel):
    seat_id: int
    start_station_id: int
    end_station_id: int
    ticket_type: str
    companion_idx: Optional[int] = None  # 0-based index in tickets list; required for 愛陪

    @field_validator("ticket_type")
    @classmethod
    def validate_ticket_type(cls, v: str) -> str:
        if v not in VALID_TICKET_TYPES:
            raise ValueError(f"ticket_type must be one of {VALID_TICKET_TYPES}")
        return v


class OrderCreate(BaseModel):
    schedule_id: int
    tickets: List[TicketCreate]

    @field_validator("tickets")
    @classmethod
    def validate_ticket_count(cls, v: list) -> list:
        if not (1 <= len(v) <= 6):
            raise ValueError("An order must contain 1 to 6 tickets")
        return v


class OrderTicketResponse(BaseModel):
    ticket_id: int
    order_id: int
    schedule_id: int
    seat_id: int
    start_station_id: int
    end_station_id: int
    ticket_type: str
    companion_ticket_id: Optional[int]
    actual_price: int
    ticket_status: str
    seat: Optional[SeatResponse] = None
    start_station: Optional[StationResponse] = None
    end_station: Optional[StationResponse] = None

    model_config = {"from_attributes": True}


class OrderResponse(BaseModel):
    order_id: int
    user_id: int
    booking_code: str
    total_amount: int
    payment_status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class OrderWithTickets(OrderResponse):
    tickets: List[OrderTicketResponse] = []


# ── Non-reserved availability ─────────────────────────────────────────────────

class NonReservedAvailability(BaseModel):
    schedule_id: int
    train_no: str
    train_type: str
    departure_time: Optional[time]
    non_reserved_total: int
    non_reserved_sold: int
    non_reserved_available: int
    congestion_level: str  # "low" / "medium" / "high" / "full"

    model_config = {"from_attributes": True}


# ── Peak sales stats ──────────────────────────────────────────────────────────

class PeakSalesSummary(BaseModel):
    schedule_id: int
    train_no: str
    train_type: str
    departure_date: date
    first_departure_time: Optional[time]
    last_arrival_time: Optional[time]
    total_seats: int
    sold_seats: int
    available_seats: int
    occupancy_rate: float

    model_config = {"from_attributes": True}


# ── Waitlists ─────────────────────────────────────────────────────────────────

class WaitlistCreate(BaseModel):
    schedule_id: int
    start_station_id: int
    end_station_id: int
    preferred_seat_type: str = "any"

    @field_validator("preferred_seat_type")
    @classmethod
    def validate_seat_type(cls, v: str) -> str:
        if v not in ("standard", "business", "any"):
            raise ValueError("preferred_seat_type must be standard, business, or any")
        return v


class WaitlistResponse(BaseModel):
    waitlist_id: int
    user_id: int
    schedule_id: int
    start_station_id: int
    end_station_id: int
    preferred_seat_type: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
