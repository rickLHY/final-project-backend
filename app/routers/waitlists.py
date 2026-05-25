from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user

router = APIRouter()


@router.post("/", response_model=schemas.WaitlistResponse, status_code=status.HTTP_201_CREATED)
def join_waitlist(
    data: schemas.WaitlistCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not db.query(models.Schedule).filter(models.Schedule.schedule_id == data.schedule_id).first():
        raise HTTPException(status_code=404, detail="Schedule not found")

    # Prevent duplicate waitlist entries
    existing = db.query(models.Waitlist).filter(
        models.Waitlist.user_id == current_user.user_id,
        models.Waitlist.schedule_id == data.schedule_id,
        models.Waitlist.start_station_id == data.start_station_id,
        models.Waitlist.end_station_id == data.end_station_id,
        models.Waitlist.status == "waiting",
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Already on the waitlist for this trip")

    entry = models.Waitlist(
        user_id=current_user.user_id,
        **data.model_dump(),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.get("/my", response_model=list[schemas.WaitlistResponse])
def get_my_waitlists(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return (
        db.query(models.Waitlist)
        .filter(models.Waitlist.user_id == current_user.user_id)
        .order_by(models.Waitlist.created_at.desc())
        .all()
    )


@router.get("/{waitlist_id}", response_model=schemas.WaitlistResponse)
def get_waitlist(
    waitlist_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    entry = db.query(models.Waitlist).filter(models.Waitlist.waitlist_id == waitlist_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Waitlist entry not found")
    if entry.user_id != current_user.user_id and current_user.user_type != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
    return entry


@router.delete("/{waitlist_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_waitlist(
    waitlist_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    entry = db.query(models.Waitlist).filter(models.Waitlist.waitlist_id == waitlist_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Waitlist entry not found")
    if entry.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    if entry.status != "waiting":
        raise HTTPException(status_code=400, detail=f"Cannot cancel a waitlist with status '{entry.status}'")
    entry.status = "cancelled"
    db.commit()
