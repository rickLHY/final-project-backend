from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from .. import models, schemas
from ..database import get_db
from ..deps import get_admin_user

router = APIRouter()


@router.get("/", response_model=list[schemas.StationResponse])
def list_stations(db: Session = Depends(get_db)):
    return db.query(models.Station).order_by(models.Station.sequence_no).all()


@router.get("/{station_id}", response_model=schemas.StationResponse)
def get_station(station_id: int, db: Session = Depends(get_db)):
    station = db.query(models.Station).filter(models.Station.station_id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station not found")
    return station


@router.post("/", response_model=schemas.StationResponse, status_code=status.HTTP_201_CREATED)
def create_station(
    data: schemas.StationCreate,
    db: Session = Depends(get_db),
    _=Depends(get_admin_user),
):
    station = models.Station(**data.model_dump())
    db.add(station)
    db.commit()
    db.refresh(station)
    return station
