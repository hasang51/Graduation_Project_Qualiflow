from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.models_db import User
from app.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def get_current_user_optional(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    if not token:
        return None
    try:
        payload = decode_access_token(token)
        user_id = int(payload.get("sub", "0"))
    except Exception:
        return None
    return db.get(User, user_id)


def get_current_user(
    user: User | None = Depends(get_current_user_optional),
) -> User:
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user
