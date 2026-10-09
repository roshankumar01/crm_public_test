from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.services.auth import (
    bearer_scheme,
    create_session,
    delete_session,
    get_current_user,
    user_payload,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    username = payload.username.strip().lower()
    user = db.scalar(select(User).where(User.username == username))
    if not user or not user.active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    token, expires_at = create_session(db, user)
    return {
        "token": token,
        "expires_at": expires_at,
        "user": user_payload(user),
    }


@router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return user_payload(current_user)


@router.post("/logout")
def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if credentials:
        delete_session(db, credentials.credentials)
    return {"message": f"{current_user.display_name} logged out."}
