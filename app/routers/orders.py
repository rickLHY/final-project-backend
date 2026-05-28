import csv
import io
import random
import string
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user

router = APIRouter()

# Discount rates by ticket type (relative to base_price)
DISCOUNT_RATES: dict[str, float] = {
    "全票": 1.0,
    "大學生": 0.8,
    "敬老": 0.8,
    "愛心": 0.5,
    "愛陪": 0.5,
    "兒童": 0.5,
}


def _generate_booking_code(db: Session) -> str:
    while True:
        code = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
        if not db.query(models.Order).filter(models.Order.booking_code == code).first():
            return code


def _get_base_price(db: Session, start_station_id: int, end_station_id: int, is_business: bool) -> int:
    price = db.query(models.TicketPrice).filter(
        models.TicketPrice.start_station_id == start_station_id,
        models.TicketPrice.end_station_id == end_station_id,
        models.TicketPrice.is_business == is_business,
    ).first()
    if not price:
        raise HTTPException(status_code=400, detail=f"No ticket price defined for station pair ({start_station_id}→{end_station_id})")
    return price.base_price


def _check_seat_available(
    db: Session, schedule_id: int, seat_id: int,
    start_seq: int, end_seq: int,
) -> bool:
    """Return True if the seat has no conflicting booking for the requested segment."""
    booked = (
        db.query(models.OrderTicket)
        .join(models.Order)
        .filter(
            models.OrderTicket.schedule_id == schedule_id,
            models.OrderTicket.seat_id == seat_id,
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

    # Normalize ranges so low < high regardless of travel direction
    req_lo, req_hi = min(start_seq, end_seq), max(start_seq, end_seq)

    for ticket in booked:
        t_start = get_seq(ticket.start_station_id)
        t_end = get_seq(ticket.end_station_id)
        t_lo, t_hi = min(t_start, t_end), max(t_start, t_end)
        if req_lo < t_hi and t_lo < req_hi:
            return False
    return True


# ── Create Order ───────────────────────────────────────────────────────────────

@router.post("/", response_model=schemas.OrderWithTickets, status_code=status.HTTP_201_CREATED)
def create_order(
    data: schemas.OrderCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    schedule = db.query(models.Schedule).filter(models.Schedule.schedule_id == data.schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    # Validate all tickets before creating anything
    station_seq: dict[int, int] = {}

    def get_seq(station_id: int) -> int:
        if station_id not in station_seq:
            s = db.query(models.Station).filter(models.Station.station_id == station_id).first()
            if not s:
                raise HTTPException(status_code=404, detail=f"Station {station_id} not found")
            station_seq[station_id] = s.sequence_no
        return station_seq[station_id]

    # Pre-validate each ticket
    for idx, ticket_data in enumerate(data.tickets):
        seat = db.query(models.Seat).filter(models.Seat.seat_id == ticket_data.seat_id).first()
        if not seat:
            raise HTTPException(status_code=404, detail=f"Seat {ticket_data.seat_id} not found")

        # Non-reserved carriages cannot be booked
        if seat.carriage_no >= schedule.non_reserved_start_carriage:
            raise HTTPException(
                status_code=400,
                detail=f"Carriage {seat.carriage_no} is non-reserved (自由座) and cannot be booked",
            )

        start_seq = get_seq(ticket_data.start_station_id)
        end_seq = get_seq(ticket_data.end_station_id)
        if start_seq == end_seq:
            raise HTTPException(status_code=400, detail="Start and end stations must be different")

        if not _check_seat_available(db, data.schedule_id, ticket_data.seat_id, start_seq, end_seq):
            raise HTTPException(
                status_code=409,
                detail=f"Seat {ticket_data.seat_id} is already booked for an overlapping segment",
            )

        # Companion ticket validation
        if ticket_data.ticket_type == "愛陪":
            if ticket_data.companion_idx is None:
                raise HTTPException(status_code=400, detail="愛陪 ticket must specify companion_idx")
            ci = ticket_data.companion_idx
            if ci < 0 or ci >= len(data.tickets):
                raise HTTPException(status_code=400, detail="companion_idx out of range")
            if data.tickets[ci].ticket_type != "愛心":
                raise HTTPException(status_code=400, detail="companion_idx must point to a 愛心 ticket")

    # ── Create Order record ──────────────────────────────────────────────────
    order = models.Order(
        user_id=current_user.user_id,
        booking_code=_generate_booking_code(db),
        total_amount=0,  # updated after tickets are priced
        payment_status="unpaid",
    )
    db.add(order)
    db.flush()  # get order_id

    created_tickets: list[models.OrderTicket] = []
    total = 0

    for ticket_data in data.tickets:
        seat = db.query(models.Seat).filter(models.Seat.seat_id == ticket_data.seat_id).first()
        base_price = _get_base_price(
            db, ticket_data.start_station_id, ticket_data.end_station_id, seat.is_business_class
        )

        if ticket_data.ticket_type == "早鳥":
            # Consume one quota from the cheapest available early-bird pool
            pool = (
                db.query(models.EarlyBirdPool)
                .filter(
                    models.EarlyBirdPool.schedule_id == data.schedule_id,
                    models.EarlyBirdPool.available_quota > 0,
                )
                .order_by(models.EarlyBirdPool.discount_rate)
                .first()
            )
            if not pool:
                raise HTTPException(status_code=409, detail="No early-bird quota available for this schedule")
            actual_price = int(base_price * float(pool.discount_rate))
            pool.available_quota -= 1
        else:
            rate = DISCOUNT_RATES.get(ticket_data.ticket_type, 1.0)
            actual_price = int(base_price * rate)

        ticket = models.OrderTicket(
            order_id=order.order_id,
            schedule_id=data.schedule_id,
            seat_id=ticket_data.seat_id,
            start_station_id=ticket_data.start_station_id,
            end_station_id=ticket_data.end_station_id,
            ticket_type=ticket_data.ticket_type,
            actual_price=actual_price,
            ticket_status="valid",
        )
        db.add(ticket)
        created_tickets.append(ticket)
        total += actual_price

    db.flush()  # get ticket_ids

    # Link companion (愛陪) tickets
    for idx, ticket_data in enumerate(data.tickets):
        if ticket_data.ticket_type == "愛陪" and ticket_data.companion_idx is not None:
            created_tickets[idx].companion_ticket_id = created_tickets[ticket_data.companion_idx].ticket_id

    order.total_amount = total
    db.commit()
    db.refresh(order)
    return order


# ── Lookup ─────────────────────────────────────────────────────────────────────

@router.get("/booking/{booking_code}", response_model=schemas.OrderWithTickets)
def get_by_booking_code(booking_code: str, db: Session = Depends(get_db)):
    order = db.query(models.Order).filter(models.Order.booking_code == booking_code).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


# ── CSV Export ─────────────────────────────────────────────────────────────────

@router.get("/export-csv")
def export_orders_csv(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    orders = (
        db.query(models.Order)
        .filter(models.Order.user_id == current_user.user_id)
        .order_by(models.Order.created_at.desc())
        .all()
    )

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["訂單編號", "訂位代號", "付款狀態", "總金額", "建立時間",
                     "票種", "起站", "終站", "座位", "票價", "票況"])

    for order in orders:
        for ticket in order.tickets:
            start = db.query(models.Station).filter(
                models.Station.station_id == ticket.start_station_id
            ).first()
            end = db.query(models.Station).filter(
                models.Station.station_id == ticket.end_station_id
            ).first()
            seat = ticket.seat
            writer.writerow([
                order.order_id,
                order.booking_code,
                order.payment_status,
                order.total_amount,
                order.created_at.strftime("%Y-%m-%d %H:%M"),
                ticket.ticket_type,
                start.station_name if start else ticket.start_station_id,
                end.station_name if end else ticket.end_station_id,
                f"{seat.carriage_no}車{seat.row_no}{seat.seat_letter}" if seat else ticket.seat_id,
                ticket.actual_price,
                ticket.ticket_status,
            ])

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue().encode("utf-8-sig")]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=my-orders.csv"},
    )


@router.get("/{order_id}", response_model=schemas.OrderWithTickets)
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    order = db.query(models.Order).filter(models.Order.order_id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.user_id != current_user.user_id and current_user.user_type != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
    return order


# ── Pay ────────────────────────────────────────────────────────────────────────

@router.put("/{order_id}/pay", response_model=schemas.OrderResponse)
def pay_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    order = db.query(models.Order).filter(models.Order.order_id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    if order.payment_status != "unpaid":
        raise HTTPException(status_code=400, detail=f"Order is already {order.payment_status}")

    order.payment_status = "paid"
    db.commit()
    db.refresh(order)
    return order


# ── Cancel Order ───────────────────────────────────────────────────────────────

@router.put("/{order_id}/cancel", response_model=schemas.OrderResponse)
def cancel_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    order = db.query(models.Order).filter(models.Order.order_id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.user_id != current_user.user_id and current_user.user_type != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
    if order.payment_status == "cancelled":
        raise HTTPException(status_code=400, detail="Order is already cancelled")

    order.payment_status = "cancelled"
    for ticket in order.tickets:
        if ticket.ticket_status == "valid":
            ticket.ticket_status = "refunded"
            _restore_early_bird_quota(db, ticket)
            _trigger_waitlist(db, ticket)

    db.commit()
    db.refresh(order)
    return order


# ── Refund Single Ticket ───────────────────────────────────────────────────────

@router.put("/{order_id}/tickets/{ticket_id}/refund", response_model=schemas.OrderTicketResponse)
def refund_ticket(
    order_id: int,
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    order = db.query(models.Order).filter(models.Order.order_id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.user_id != current_user.user_id and current_user.user_type != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    ticket = db.query(models.OrderTicket).filter(
        models.OrderTicket.ticket_id == ticket_id,
        models.OrderTicket.order_id == order_id,
    ).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found in this order")
    if ticket.ticket_status != "valid":
        raise HTTPException(status_code=400, detail=f"Ticket status is already {ticket.ticket_status}")

    # If refunding a 愛心 ticket, also refund its paired 愛陪 ticket
    paired_companion = db.query(models.OrderTicket).filter(
        models.OrderTicket.companion_ticket_id == ticket.ticket_id,
        models.OrderTicket.ticket_status == "valid",
    ).first()
    if paired_companion:
        paired_companion.ticket_status = "refunded"
        _restore_early_bird_quota(db, paired_companion)
        _trigger_waitlist(db, paired_companion)

    ticket.ticket_status = "refunded"
    _restore_early_bird_quota(db, ticket)
    _trigger_waitlist(db, ticket)

    # Recalculate order total
    order.total_amount = sum(
        t.actual_price for t in order.tickets if t.ticket_status == "valid"
    )

    db.commit()
    db.refresh(ticket)
    return ticket


# ── Helpers ────────────────────────────────────────────────────────────────────

def _restore_early_bird_quota(db: Session, ticket: models.OrderTicket) -> None:
    """Restore one quota to the matching early-bird pool when an early-bird ticket is refunded."""
    if ticket.ticket_type != "早鳥":
        return
    pool = (
        db.query(models.EarlyBirdPool)
        .filter(models.EarlyBirdPool.schedule_id == ticket.schedule_id)
        .order_by(models.EarlyBirdPool.discount_rate)
        .first()
    )
    if pool:
        pool.available_quota = min(pool.available_quota + 1, pool.initial_quota)


def _trigger_waitlist(db: Session, ticket: models.OrderTicket) -> None:
    """Mark the earliest matching waitlist entry as 'matched' when a ticket is freed."""
    start_station = db.query(models.Station).filter(
        models.Station.station_id == ticket.start_station_id
    ).first()
    end_station = db.query(models.Station).filter(
        models.Station.station_id == ticket.end_station_id
    ).first()
    if not start_station or not end_station:
        return

    seat = db.query(models.Seat).filter(models.Seat.seat_id == ticket.seat_id).first()
    pref = "business" if (seat and seat.is_business_class) else "standard"

    candidates = (
        db.query(models.Waitlist)
        .filter(
            models.Waitlist.schedule_id == ticket.schedule_id,
            models.Waitlist.status == "waiting",
            models.Waitlist.preferred_seat_type.in_([pref, "any"]),
        )
        .order_by(models.Waitlist.created_at)
        .all()
    )

    freed_start_seq = start_station.sequence_no
    freed_end_seq = end_station.sequence_no

    for wl in candidates:
        wl_start = db.query(models.Station).filter(models.Station.station_id == wl.start_station_id).first()
        wl_end = db.query(models.Station).filter(models.Station.station_id == wl.end_station_id).first()
        if not wl_start or not wl_end:
            continue
        # Freed segment must fully cover the waitlist segment
        if wl_start.sequence_no >= freed_start_seq and wl_end.sequence_no <= freed_end_seq:
            wl.status = "matched"
            break
