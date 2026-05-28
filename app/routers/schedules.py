from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date
from .. import models, schemas
from ..database import get_db
from ..deps import get_admin_user

router = APIRouter()


def _get_booked_seat_ids(db: Session, schedule_id: int, req_lo: int, req_hi: int) -> set[int]:
    """Return seat_ids that are booked for an overlapping segment on this schedule."""
    booked = (
        db.query(models.OrderTicket)
        .join(models.Order)
        .filter(
            models.OrderTicket.schedule_id == schedule_id,
            models.OrderTicket.ticket_status == "valid",
            models.Order.payment_status.in_(["unpaid", "paid"]),
        )
        .all()
    )
    seq_cache: dict[int, int] = {}

    def get_seq(station_id: int) -> int:
        if station_id not in seq_cache:
            s = db.query(models.Station).filter(models.Station.station_id == station_id).first()
            seq_cache[station_id] = s.sequence_no if s else 0
        return seq_cache[station_id]

    result: set[int] = set()
    for ticket in booked:
        t_lo = min(get_seq(ticket.start_station_id), get_seq(ticket.end_station_id))
        t_hi = max(get_seq(ticket.start_station_id), get_seq(ticket.end_station_id))
        if req_lo < t_hi and t_lo < req_hi:
            result.add(ticket.seat_id)
    return result


@router.get("/", response_model=list[schemas.ScheduleSearchResult])
def search_schedules(
    departure_date: date,
    start_station_id: int,
    end_station_id: int,
    db: Session = Depends(get_db),
):
    """Search for schedules between two stations on a given date."""
    start_station = db.query(models.Station).filter(models.Station.station_id == start_station_id).first()
    end_station = db.query(models.Station).filter(models.Station.station_id == end_station_id).first()
    if not start_station or not end_station:
        raise HTTPException(status_code=404, detail="Station not found")
    if start_station.sequence_no == end_station.sequence_no:
        raise HTTPException(status_code=400, detail="Start and end stations must be different")

    # Find schedules that stop at both stations
    schedules = (
        db.query(models.Schedule)
        .filter(models.Schedule.departure_date == departure_date)
        .join(models.Train)
        .all()
    )

    results = []
    for schedule in schedules:
        stop_map = {st.station_id: st for st in schedule.stop_times}
        if start_station_id not in stop_map or end_station_id not in stop_map:
            continue

        origin_stop = stop_map[start_station_id]
        dest_stop = stop_map[end_station_id]

        # Validate direction: origin departure_time must be before destination arrival_time
        if origin_stop.departure_time is None or dest_stop.arrival_time is None:
            continue
        if origin_stop.departure_time >= dest_stop.arrival_time:
            continue

        # Count available reserved seats for this segment
        req_lo = min(start_station.sequence_no, end_station.sequence_no)
        req_hi = max(start_station.sequence_no, end_station.sequence_no)
        booked_ids = _get_booked_seat_ids(db, schedule.schedule_id, req_lo, req_hi)
        total_reserved = db.query(models.Seat).filter(
            models.Seat.carriage_no < schedule.non_reserved_start_carriage
        ).count()
        available_count = max(0, total_reserved - len(booked_ids))

        results.append(schemas.ScheduleSearchResult(
            schedule_id=schedule.schedule_id,
            train_no=schedule.train_no,
            train_type=schedule.train.train_type,
            departure_date=schedule.departure_date,
            non_reserved_start_carriage=schedule.non_reserved_start_carriage,
            origin_departure_time=origin_stop.departure_time,
            destination_arrival_time=dest_stop.arrival_time,
            available_seats=available_count,
        ))

    results.sort(key=lambda r: r.origin_departure_time)
    return results


@router.get("/non-reserved-availability", response_model=list[schemas.NonReservedAvailability])
def non_reserved_availability(
    departure_date: date,
    station_id: int,
    db: Session = Depends(get_db),
):
    """Non-reserved seat occupancy for all trains stopping at a station on a given date."""
    station = db.query(models.Station).filter(models.Station.station_id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station not found")

    schedules = (
        db.query(models.Schedule)
        .filter(models.Schedule.departure_date == departure_date)
        .join(models.Train)
        .all()
    )

    # Total non-reserved seats (same across all schedules — depends only on non_reserved_start_carriage)
    results = []
    for schedule in schedules:
        stop_map = {st.station_id: st for st in schedule.stop_times}
        if station_id not in stop_map:
            continue
        departure_time = stop_map[station_id].departure_time

        non_reserved_total = db.query(models.Seat).filter(
            models.Seat.carriage_no >= schedule.non_reserved_start_carriage
        ).count()

        non_reserved_sold = (
            db.query(models.OrderTicket)
            .join(models.Order)
            .join(models.Seat, models.OrderTicket.seat_id == models.Seat.seat_id)
            .filter(
                models.OrderTicket.schedule_id == schedule.schedule_id,
                models.OrderTicket.ticket_status == "valid",
                models.Order.payment_status.in_(["unpaid", "paid"]),
                models.Seat.carriage_no >= schedule.non_reserved_start_carriage,
            )
            .count()
        )

        non_reserved_available = max(0, non_reserved_total - non_reserved_sold)
        rate = non_reserved_sold / non_reserved_total if non_reserved_total else 0
        if rate >= 1.0:
            level = "full"
        elif rate >= 0.8:
            level = "high"
        elif rate >= 0.5:
            level = "medium"
        else:
            level = "low"

        results.append(schemas.NonReservedAvailability(
            schedule_id=schedule.schedule_id,
            train_no=schedule.train_no,
            train_type=schedule.train.train_type,
            departure_time=departure_time,
            non_reserved_total=non_reserved_total,
            non_reserved_sold=non_reserved_sold,
            non_reserved_available=non_reserved_available,
            congestion_level=level,
        ))

    results.sort(key=lambda r: r.departure_time or "")
    return results


@router.get("/peak-sales", response_model=list[schemas.PeakSalesSummary])
def peak_sales_stats(
    start_date: date,
    end_date: date,
    db: Session = Depends(get_db),
):
    """Ticket sales occupancy for all schedules within a date range."""
    schedules = (
        db.query(models.Schedule)
        .filter(
            models.Schedule.departure_date >= start_date,
            models.Schedule.departure_date <= end_date,
        )
        .join(models.Train)
        .order_by(models.Schedule.departure_date)
        .all()
    )

    total_seats_all = db.query(models.Seat).count()

    results = []
    for schedule in schedules:
        stop_times = sorted(schedule.stop_times, key=lambda s: s.departure_time or s.arrival_time or "")
        first_dep = stop_times[0].departure_time if stop_times else None
        last_arr = stop_times[-1].arrival_time if stop_times else None

        sold = (
            db.query(models.OrderTicket)
            .join(models.Order)
            .filter(
                models.OrderTicket.schedule_id == schedule.schedule_id,
                models.OrderTicket.ticket_status == "valid",
                models.Order.payment_status.in_(["unpaid", "paid"]),
            )
            .count()
        )

        avail = max(0, total_seats_all - sold)
        rate = round(sold / total_seats_all * 100, 1) if total_seats_all else 0.0

        results.append(schemas.PeakSalesSummary(
            schedule_id=schedule.schedule_id,
            train_no=schedule.train_no,
            train_type=schedule.train.train_type,
            departure_date=schedule.departure_date,
            first_departure_time=first_dep,
            last_arrival_time=last_arr,
            total_seats=total_seats_all,
            sold_seats=sold,
            available_seats=avail,
            occupancy_rate=rate,
        ))

    return results


@router.get("/{schedule_id}", response_model=schemas.ScheduleWithStops)
def get_schedule(schedule_id: int, db: Session = Depends(get_db)):
    schedule = db.query(models.Schedule).filter(models.Schedule.schedule_id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return schedule


@router.post("/", response_model=schemas.ScheduleWithStops, status_code=status.HTTP_201_CREATED)
def create_schedule(
    data: schemas.ScheduleCreate,
    db: Session = Depends(get_db),
    _=Depends(get_admin_user),
):
    if not db.query(models.Train).filter(models.Train.train_no == data.train_no).first():
        raise HTTPException(status_code=404, detail="Train not found")

    schedule = models.Schedule(
        train_no=data.train_no,
        departure_date=data.departure_date,
        non_reserved_start_carriage=data.non_reserved_start_carriage,
    )
    db.add(schedule)
    db.flush()

    for st in data.stop_times:
        stop = models.StopTime(schedule_id=schedule.schedule_id, **st.model_dump())
        db.add(stop)

    db.commit()
    db.refresh(schedule)
    return schedule


@router.get("/{schedule_id}/available-seats", response_model=list[schemas.SeatResponse])
def get_available_seats(
    schedule_id: int,
    start_station_id: int,
    end_station_id: int,
    is_business: Optional[bool] = None,
    db: Session = Depends(get_db),
):
    """Return seats not yet booked for the requested segment on this schedule."""
    schedule = db.query(models.Schedule).filter(models.Schedule.schedule_id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    start_station = db.query(models.Station).filter(models.Station.station_id == start_station_id).first()
    end_station = db.query(models.Station).filter(models.Station.station_id == end_station_id).first()
    if not start_station or not end_station:
        raise HTTPException(status_code=404, detail="Station not found")

    req_lo = min(start_station.sequence_no, end_station.sequence_no)
    req_hi = max(start_station.sequence_no, end_station.sequence_no)
    booked_seat_ids = _get_booked_seat_ids(db, schedule_id, req_lo, req_hi)

    # Query available seats (only reserved carriages)
    q = db.query(models.Seat).filter(
        models.Seat.carriage_no < schedule.non_reserved_start_carriage
    )
    if is_business is not None:
        q = q.filter(models.Seat.is_business_class == is_business)

    available = [s for s in q.all() if s.seat_id not in booked_seat_ids]
    return available


@router.get("/{schedule_id}/early-bird", response_model=list[schemas.EarlyBirdPoolResponse])
def get_early_bird_pools(schedule_id: int, db: Session = Depends(get_db)):
    schedule = db.query(models.Schedule).filter(models.Schedule.schedule_id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return schedule.early_bird_pools


@router.post("/{schedule_id}/early-bird", response_model=schemas.EarlyBirdPoolResponse, status_code=status.HTTP_201_CREATED)
def create_early_bird_pool(
    schedule_id: int,
    data: schemas.EarlyBirdPoolCreate,
    db: Session = Depends(get_db),
    _=Depends(get_admin_user),
):
    if not db.query(models.Schedule).filter(models.Schedule.schedule_id == schedule_id).first():
        raise HTTPException(status_code=404, detail="Schedule not found")
    pool = models.EarlyBirdPool(schedule_id=schedule_id, **data.model_dump())
    db.add(pool)
    db.commit()
    db.refresh(pool)
    return pool
