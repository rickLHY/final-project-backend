from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from .. import models, schemas
from ..database import get_db
from ..deps import get_admin_user

router = APIRouter()


@router.get("/", response_model=list[schemas.TrainResponse])
def list_trains(db: Session = Depends(get_db)):
    return db.query(models.Train).order_by(models.Train.train_no).all()


@router.get("/{train_no}", response_model=schemas.TrainResponse)
def get_train(train_no: str, db: Session = Depends(get_db)):
    train = db.query(models.Train).filter(models.Train.train_no == train_no).first()
    if not train:
        raise HTTPException(status_code=404, detail="Train not found")
    return train


@router.post("/", response_model=schemas.TrainResponse, status_code=status.HTTP_201_CREATED)
def create_train(
    data: schemas.TrainCreate,
    db: Session = Depends(get_db),
    _=Depends(get_admin_user),
):
    if db.query(models.Train).filter(models.Train.train_no == data.train_no).first():
        raise HTTPException(status_code=400, detail="Train number already exists")
    train = models.Train(**data.model_dump())
    db.add(train)
    db.commit()
    db.refresh(train)
    return train
