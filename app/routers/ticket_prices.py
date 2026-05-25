from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from .. import models, schemas
from ..database import get_db
from ..deps import get_admin_user

router = APIRouter()


@router.get("/", response_model=list[schemas.TicketPriceResponse])
def list_ticket_prices(
    start_station_id: Optional[int] = None,
    end_station_id: Optional[int] = None,
    is_business: Optional[bool] = None,
    db: Session = Depends(get_db),
):
    q = db.query(models.TicketPrice)
    if start_station_id:
        q = q.filter(models.TicketPrice.start_station_id == start_station_id)
    if end_station_id:
        q = q.filter(models.TicketPrice.end_station_id == end_station_id)
    if is_business is not None:
        q = q.filter(models.TicketPrice.is_business == is_business)
    return q.all()


@router.post("/", response_model=schemas.TicketPriceResponse, status_code=status.HTTP_201_CREATED)
def create_ticket_price(
    data: schemas.TicketPriceCreate,
    db: Session = Depends(get_db),
    _=Depends(get_admin_user),
):
    price = models.TicketPrice(**data.model_dump())
    db.add(price)
    db.commit()
    db.refresh(price)
    return price


@router.put("/{price_id}", response_model=schemas.TicketPriceResponse)
def update_ticket_price(
    price_id: int,
    base_price: int,
    db: Session = Depends(get_db),
    _=Depends(get_admin_user),
):
    price = db.query(models.TicketPrice).filter(models.TicketPrice.price_id == price_id).first()
    if not price:
        raise HTTPException(status_code=404, detail="Ticket price not found")
    price.base_price = base_price
    db.commit()
    db.refresh(price)
    return price
