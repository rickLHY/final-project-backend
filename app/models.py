from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Date, Time,
    Numeric, ForeignKey, func, CheckConstraint, UniqueConstraint
)
from sqlalchemy.orm import relationship
from .database import Base


class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(50), nullable=False)
    phone = Column(String(20), nullable=False)
    user_type = Column(String(20), default="general")  # general, corporate, admin
    tgo_balance = Column(Integer, default=0)
    google_id = Column(String(100), unique=True, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        CheckConstraint("tgo_balance >= 0", name="ck_users_tgo_balance_non_negative"),
        CheckConstraint("user_type IN ('general', 'corporate', 'admin')", name="ck_users_user_type"),
    )

    orders = relationship("Order", back_populates="user")
    waitlists = relationship("Waitlist", back_populates="user")


class Station(Base):
    __tablename__ = "stations"

    station_id = Column(Integer, primary_key=True, autoincrement=True)
    station_name = Column(String(20), unique=True, nullable=False)
    sequence_no = Column(Integer, unique=True, nullable=False)
    latitude = Column(Numeric(9, 6))
    longitude = Column(Numeric(9, 6))


class Train(Base):
    __tablename__ = "trains"

    train_no = Column(String(10), primary_key=True)
    train_type = Column(String(20))  # standard, express
    total_carriages = Column(Integer, default=12)

    schedules = relationship("Schedule", back_populates="train")


class Seat(Base):
    __tablename__ = "seats"

    seat_id = Column(Integer, primary_key=True, autoincrement=True)
    carriage_no = Column(Integer, nullable=False)
    row_no = Column(Integer, nullable=False)
    seat_letter = Column(String(1), nullable=False)  # A, B, C, D, E
    is_business_class = Column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint("carriage_no", "row_no", "seat_letter", name="uq_seats_position"),
    )


class TicketPrice(Base):
    __tablename__ = "ticket_prices"

    price_id = Column(Integer, primary_key=True, autoincrement=True)
    start_station_id = Column(Integer, ForeignKey("stations.station_id"), nullable=False)
    end_station_id = Column(Integer, ForeignKey("stations.station_id"), nullable=False)
    is_business = Column(Boolean, default=False)
    base_price = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("start_station_id", "end_station_id", "is_business", name="uq_ticket_prices_route"),
    )

    start_station = relationship("Station", foreign_keys=[start_station_id])
    end_station = relationship("Station", foreign_keys=[end_station_id])


class Schedule(Base):
    __tablename__ = "schedules"

    schedule_id = Column(Integer, primary_key=True, autoincrement=True)
    train_no = Column(String(10), ForeignKey("trains.train_no"), nullable=False)
    departure_date = Column(Date, nullable=False)
    non_reserved_start_carriage = Column(Integer, default=10)

    __table_args__ = (
        UniqueConstraint("train_no", "departure_date", name="uq_schedules_train_date"),
    )

    train = relationship("Train", back_populates="schedules")
    stop_times = relationship("StopTime", back_populates="schedule", cascade="all, delete-orphan", order_by="StopTime.stop_id")
    early_bird_pools = relationship("EarlyBirdPool", back_populates="schedule", cascade="all, delete-orphan")
    order_tickets = relationship("OrderTicket", back_populates="schedule")
    waitlists = relationship("Waitlist", back_populates="schedule")


class StopTime(Base):
    __tablename__ = "stop_times"

    stop_id = Column(Integer, primary_key=True, autoincrement=True)
    schedule_id = Column(Integer, ForeignKey("schedules.schedule_id", ondelete="CASCADE"), nullable=False)
    station_id = Column(Integer, ForeignKey("stations.station_id"), nullable=False)
    arrival_time = Column(Time, nullable=True)    # NULL for the first station
    departure_time = Column(Time, nullable=True)  # NULL for the last station

    __table_args__ = (
        UniqueConstraint("schedule_id", "station_id", name="uq_stop_times_schedule_station"),
    )

    schedule = relationship("Schedule", back_populates="stop_times")
    station = relationship("Station")


class EarlyBirdPool(Base):
    __tablename__ = "early_bird_pools"

    pool_id = Column(Integer, primary_key=True, autoincrement=True)
    schedule_id = Column(Integer, ForeignKey("schedules.schedule_id", ondelete="CASCADE"), nullable=False)
    discount_rate = Column(Numeric(3, 2), nullable=False)
    initial_quota = Column(Integer, nullable=False)
    available_quota = Column(Integer, nullable=False)

    __table_args__ = (
        CheckConstraint("available_quota >= 0", name="ck_early_bird_quota_non_negative"),
        CheckConstraint("available_quota <= initial_quota", name="ck_early_bird_quota_cap"),
    )

    schedule = relationship("Schedule", back_populates="early_bird_pools")


class Order(Base):
    __tablename__ = "orders"

    order_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    booking_code = Column(String(10), unique=True, nullable=False)
    total_amount = Column(Integer, nullable=False)
    payment_status = Column(String(20), default="unpaid")  # unpaid, paid, cancelled
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        CheckConstraint("payment_status IN ('unpaid', 'paid', 'cancelled')", name="ck_orders_payment_status"),
    )

    tgo_points_earned = Column(Integer, default=0)

    user = relationship("User", back_populates="orders")
    tickets = relationship("OrderTicket", back_populates="order", cascade="all, delete-orphan")


class OrderTicket(Base):
    __tablename__ = "order_tickets"

    ticket_id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey("orders.order_id", ondelete="CASCADE"), nullable=False)
    schedule_id = Column(Integer, ForeignKey("schedules.schedule_id"), nullable=False)
    seat_id = Column(Integer, ForeignKey("seats.seat_id"), nullable=False)
    start_station_id = Column(Integer, ForeignKey("stations.station_id"), nullable=False)
    end_station_id = Column(Integer, ForeignKey("stations.station_id"), nullable=False)
    ticket_type = Column(String(20), nullable=False)  # 全票, 早鳥, 大學生, 敬老, 愛心, 愛陪, 兒童
    companion_ticket_id = Column(Integer, ForeignKey("order_tickets.ticket_id"), nullable=True)
    actual_price = Column(Integer, nullable=False)
    ticket_status = Column(String(20), default="valid")  # valid, used, refunded

    __table_args__ = (
        CheckConstraint("ticket_status IN ('valid', 'used', 'refunded')", name="ck_order_tickets_status"),
    )

    order = relationship("Order", back_populates="tickets")
    schedule = relationship("Schedule", back_populates="order_tickets")
    seat = relationship("Seat")
    start_station = relationship("Station", foreign_keys=[start_station_id])
    end_station = relationship("Station", foreign_keys=[end_station_id])
    # self-referential: 愛陪 ticket points to its paired 愛心 ticket
    companion_ticket = relationship(
        "OrderTicket",
        foreign_keys=[companion_ticket_id],
        primaryjoin="OrderTicket.companion_ticket_id == OrderTicket.ticket_id",
        remote_side="[OrderTicket.ticket_id]",
    )


class Waitlist(Base):
    __tablename__ = "waitlists"

    waitlist_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    schedule_id = Column(Integer, ForeignKey("schedules.schedule_id"), nullable=False)
    start_station_id = Column(Integer, ForeignKey("stations.station_id"), nullable=False)
    end_station_id = Column(Integer, ForeignKey("stations.station_id"), nullable=False)
    preferred_seat_type = Column(String(20), default="any")  # standard, business, any
    status = Column(String(20), default="waiting")  # waiting, matched, expired, cancelled
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        CheckConstraint("status IN ('waiting', 'matched', 'expired', 'cancelled')", name="ck_waitlists_status"),
        CheckConstraint("preferred_seat_type IN ('standard', 'business', 'any')", name="ck_waitlists_seat_type"),
    )

    user = relationship("User", back_populates="waitlists")
    schedule = relationship("Schedule", back_populates="waitlists")
    start_station = relationship("Station", foreign_keys=[start_station_id])
    end_station = relationship("Station", foreign_keys=[end_station_id])
