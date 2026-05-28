import secrets
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session
from .. import models, schemas
from ..config import settings
from ..database import get_db
from ..auth import verify_password, get_password_hash, create_access_token

router = APIRouter()


# ── Email / password ───────────────────────────────────────────────────────────

@router.post("/register", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED)
def register(user_in: schemas.UserCreate, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.email == user_in.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = models.User(
        email=user_in.email,
        password_hash=get_password_hash(user_in.password),
        name=user_in.name,
        phone=user_in.phone,
        user_type=user_in.user_type,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(data={"sub": str(user.user_id)})
    return {"access_token": token, "token_type": "bearer"}


# ── Google OAuth ───────────────────────────────────────────────────────────────

class GoogleTokenRequest(BaseModel):
    credential: str  # ID token from Google Identity Services


@router.post("/google", response_model=schemas.Token)
def google_login(body: GoogleTokenRequest, db: Session = Depends(get_db)):
    if not settings.google_client_id:
        raise HTTPException(status_code=501, detail="Google OAuth not configured on this server")

    try:
        from google.oauth2 import id_token
        from google.auth.transport import requests as google_requests

        idinfo = id_token.verify_oauth2_token(
            body.credential,
            google_requests.Request(),
            settings.google_client_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid Google token: {exc}")

    google_id = idinfo["sub"]
    email = idinfo.get("email", "")
    name = idinfo.get("name") or email.split("@")[0]

    # Find existing user by google_id or email
    user = (
        db.query(models.User).filter(models.User.google_id == google_id).first()
        or db.query(models.User).filter(models.User.email == email).first()
    )

    if user:
        # Link google_id if not linked yet
        if not user.google_id:
            user.google_id = google_id
            db.commit()
    else:
        # Auto-register new Google user
        user = models.User(
            email=email,
            password_hash=get_password_hash(secrets.token_hex(32)),  # random unusable password
            name=name,
            phone="",
            user_type="general",
            google_id=google_id,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_access_token(data={"sub": str(user.user_id)})
    return {"access_token": token, "token_type": "bearer"}
