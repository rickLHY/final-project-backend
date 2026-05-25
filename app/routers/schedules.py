from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date
from .. import models, schemas
from ..database import get_db
from ..deps import get_admin_user, get_current_user

router = APIRouter()


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

        results.append(schemas.ScheduleSearchResult(
            schedule_id=schedule.schedule_id,
            train_no=schedule.train_no,
            train_type=schedule.train.train_type,
            departure_date=schedule.departure_date,
            non_reserved_start_carriage=schedule.non_reserved_start_carriage,
            origin_departure_time=origin_stop.departure_time,
            destination_arrival_time=dest_stop.arrival_time,
        ))

    results.sort(key=lambda r: r.origin_departure_time)
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

    # Seats already booked with an overlapping segment for this schedule
    booked_tickets = (
        db.query(models.OrderTicket)
        .join(models.Order)
        .filter(
            models.OrderTicket.schedule_id == schedule_id,
            models.OrderTicket.ticket_status == "valid",
            models.Order.payment_status.in_(["unpaid", "paid"]),
        )
        .all()
    )

    # station sequence cache
    seq_cache: dict[int, int] = {}

    def get_seq(station_id: int) -> int:
        if station_id not in seq_cache:
            s = db.query(models.Station).filter(models.Station.station_id == station_id).first()
            seq_cache[station_id] = s.sequence_no if s else 0
        return seq_cache[station_id]

    req_start_seq = start_station.sequence_no
    req_end_seq = end_station.sequence_no

    booked_seat_ids: set[int] = set()
    for ticket in booked_tickets:
        t_start_seq = get_seq(ticket.start_station_id)
        t_end_seq = get_seq(ticket.end_station_id)
        # Two segments [A,B) and [C,D) overlap if A < D and C < B
        if req_start_seq < t_end_seq and t_start_seq < req_end_seq:
            booked_seat_ids.add(ticket.seat_id)

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
