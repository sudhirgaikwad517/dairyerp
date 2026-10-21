"""Password hashing, JWT tokens and role checks."""
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.database import get_db
from backend.app.models.entities import Customer, User

ADMIN_ROLES = {"super_admin", "admin"}
MIN_PASSWORD_LENGTH = 6
_DEFAULT_SECRET = "dairy_erp_super_secret_jwt_key_2026"


def _load_secret_key() -> str:
    """
    Use SECRET_KEY from the environment if set. Otherwise keep a random key in a local file,
    so tokens cannot be forged with the default key that is visible in the source code.
    """
    if os.getenv("SECRET_KEY") and settings.SECRET_KEY != _DEFAULT_SECRET:
        return settings.SECRET_KEY
    key_file = Path(__file__).resolve().parents[3] / ".secret_key"
    if key_file.exists():
        return key_file.read_text().strip()
    key = secrets.token_urlsafe(48)
    key_file.write_text(key)
    return key


SECRET_KEY = _load_secret_key()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def is_hashed(value: Optional[str]) -> bool:
    return bool(value) and value.startswith("$2")


def verify_password(password: str, stored: Optional[str]) -> bool:
    if not stored:
        return False
    if is_hashed(stored):
        try:
            return bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8"))
        except ValueError:
            return False
    return secrets.compare_digest(password, stored)  # legacy plain-text value, upgraded after login


def validate_new_password(password: str) -> None:
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise HTTPException(status_code=400, detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters")


def create_access_token(user: User) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user.id), "role": user.role, "exp": expires}
    return jwt.encode(payload, SECRET_KEY, algorithm=settings.ALGORITHM)


def _token_from_request(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    # File downloads (PDF / CSV) are opened as plain links, so they pass the token in the URL
    return request.query_params.get("access_token")


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = _token_from_request(request)
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Please log in again",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise unauthorized
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = int(payload.get("sub"))
    except (jwt.PyJWTError, TypeError, ValueError):
        raise unauthorized
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise unauthorized
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Only the admin can do this")
    return user


def require_driver(user: User = Depends(get_current_user)) -> User:
    if user.role != "driver" and user.role not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Only delivery boys can use this")
    return user


def get_current_customer(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Customer:
    if user.role != "customer":
        raise HTTPException(status_code=403, detail="Only customers can use this")
    customer = db.query(Customer).filter(Customer.user_id == user.id).first()
    if not customer:
        raise HTTPException(status_code=403, detail="This login is not linked to a customer")
    if not customer.is_active:
        raise HTTPException(status_code=403, detail="This customer account is inactive. Please contact the dairy.")
    return customer


def upgrade_plaintext_passwords(db: Session) -> int:
    """Hash any passwords still stored as plain text (older databases / seed data)."""
    count = 0
    for user in db.query(User).all():
        if user.password_hash and not is_hashed(user.password_hash):
            user.password_hash = hash_password(user.password_hash)
            count += 1
    if count:
        db.commit()
    return count
