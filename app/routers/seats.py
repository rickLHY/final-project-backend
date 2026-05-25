from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Optional
from .. import models, schemas
from ..database import get_db

router = APIRouter()


@router.get("/", response_model=list[schemas.SeatResponse])
def list_seats(
    carriage_no: Optional[int] = None,
    is_business_class: Optional[bool] = None,
    db: Session = Depends(get_db),
):
    q = db.query(models.Seat)
    if carriage_no is not None:
        q = q.filter(models.Seat.carriage_no == carriage_no)
    if is_business_class is not None:
        q = q.filter(models.Seat.is_business_class == is_business_class)
    return q.order_by(models.Seat.carriage_no, models.Seat.row_no, models.Seat.seat_letter).all()
