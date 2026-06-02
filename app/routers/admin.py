from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from typing import Optional
from datetime import date
from .. import models, schemas
from ..database import get_db
from ..deps import get_admin_user

router = APIRouter()


@router.get("/stats")
def get_stats(db: Session = Depends(get_db), _=Depends(get_admin_user)):
    today = date.today()
    return {
        "total_revenue": db.query(func.sum(models.Order.total_amount)).filter(
            models.Order.payment_status == "paid").scalar() or 0,
        "today_revenue": db.query(func.sum(models.Order.total_amount)).filter(
            models.Order.payment_status == "paid",
            func.date(models.Order.created_at) == today,
        ).scalar() or 0,
        "total_orders": db.query(func.count(models.Order.order_id)).scalar() or 0,
        "paid_orders": db.query(func.count(models.Order.order_id)).filter(
            models.Order.payment_status == "paid").scalar() or 0,
        "unpaid_orders": db.query(func.count(models.Order.order_id)).filter(
            models.Order.payment_status == "unpaid").scalar() or 0,
        "cancelled_orders": db.query(func.count(models.Order.order_id)).filter(
            models.Order.payment_status == "cancelled").scalar() or 0,
        "total_users": db.query(func.count(models.User.user_id)).filter(
            models.User.user_type != "admin").scalar() or 0,
        "active_schedules": db.query(func.count(models.Schedule.schedule_id)).filter(
            models.Schedule.departure_date >= today).scalar() or 0,
    }


@router.get("/users", response_model=list[schemas.UserResponse])
def list_users(
    user_type: Optional[str] = None,
    db: Session = Depends(get_db),
    _=Depends(get_admin_user),
):
    q = db.query(models.User)
    if user_type:
        q = q.filter(models.User.user_type == user_type)
    return q.order_by(models.User.created_at.desc()).all()


@router.put("/users/{user_id}", response_model=schemas.UserResponse)
def admin_update_user(
    user_id: int,
    updates: schemas.AdminUserUpdate,
    db: Session = Depends(get_db),
    _=Depends(get_admin_user),
):
    user = db.query(models.User).filter(models.User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if updates.name is not None:
        user.name = updates.name
    if updates.phone is not None:
        user.phone = updates.phone
    if updates.user_type is not None:
        if updates.user_type not in ("general", "corporate", "admin"):
            raise HTTPException(status_code=400, detail="Invalid user_type")
        user.user_type = updates.user_type
    db.commit()
    db.refresh(user)
    return user


@router.get("/orders")
def list_all_orders(
    payment_status: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
    _=Depends(get_admin_user),
):
    q = (
        db.query(models.Order)
        .options(joinedload(models.Order.user), joinedload(models.Order.tickets))
        .order_by(models.Order.created_at.desc())
    )
    if payment_status:
        q = q.filter(models.Order.payment_status == payment_status)
    if start_date:
        q = q.filter(func.date(models.Order.created_at) >= start_date)
    if end_date:
        q = q.filter(func.date(models.Order.created_at) <= end_date)
    return [
        {
            "order_id": o.order_id,
            "booking_code": o.booking_code,
            "user_id": o.user_id,
            "user_name": o.user.name if o.user else "",
            "user_email": o.user.email if o.user else "",
            "total_amount": o.total_amount,
            "payment_status": o.payment_status,
            "ticket_count": len(o.tickets),
            "created_at": o.created_at.isoformat(),
        }
        for o in q.all()
    ]


@router.get("/schedules", response_model=list[schemas.ScheduleWithStops])
def list_all_schedules(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
    _=Depends(get_admin_user),
):
    q = db.query(models.Schedule).order_by(models.Schedule.departure_date, models.Schedule.train_no)
    if start_date:
        q = q.filter(models.Schedule.departure_date >= start_date)
    if end_date:
        q = q.filter(models.Schedule.departure_date <= end_date)
    return q.all()


@router.get("/waitlists")
def list_all_waitlists(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    _=Depends(get_admin_user),
):
    q = (
        db.query(models.Waitlist)
        .options(
            joinedload(models.Waitlist.user),
            joinedload(models.Waitlist.start_station),
            joinedload(models.Waitlist.end_station),
            joinedload(models.Waitlist.schedule),
        )
        .order_by(models.Waitlist.created_at.desc())
    )
    if status:
        q = q.filter(models.Waitlist.status == status)
    return [
        {
            "waitlist_id": wl.waitlist_id,
            "user_id": wl.user_id,
            "user_name": wl.user.name if wl.user else "",
            "user_email": wl.user.email if wl.user else "",
            "schedule_id": wl.schedule_id,
            "train_no": wl.schedule.train_no if wl.schedule else "",
            "start_station_name": wl.start_station.station_name if wl.start_station else "",
            "end_station_name": wl.end_station.station_name if wl.end_station else "",
            "preferred_seat_type": wl.preferred_seat_type,
            "status": wl.status,
            "created_at": wl.created_at.isoformat(),
        }
        for wl in q.all()
    ]


@router.put("/waitlists/{waitlist_id}", response_model=schemas.WaitlistResponse)
def update_waitlist_status(
    waitlist_id: int,
    status: str,
    db: Session = Depends(get_db),
    _=Depends(get_admin_user),
):
    if status not in ("waiting", "matched", "expired", "cancelled"):
        raise HTTPException(status_code=400, detail="Invalid status")
    wl = db.query(models.Waitlist).filter(models.Waitlist.waitlist_id == waitlist_id).first()
    if not wl:
        raise HTTPException(status_code=404, detail="Waitlist not found")
    wl.status = status
    db.commit()
    db.refresh(wl)
    return wl
