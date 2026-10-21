"""The dairy owner's admin login. No username or password is written in the code: the first admin
is created from DAIRY_ADMIN_USERNAME / DAIRY_ADMIN_PASSWORD, or with backend/create_admin.py."""
import logging
import os
import re
from typing import Optional

from sqlalchemy.orm import Session

from backend.app.core.security import MIN_PASSWORD_LENGTH, hash_password
from backend.app.models.entities import Branch, User

logger = logging.getLogger("dairy_erp")
USERNAME_RE = re.compile(r"^[a-z0-9_.]{3,50}$")


def save_admin(db: Session, username: str, password: str, full_name: str = "") -> User:
    """Add an admin login, or set a new password for an existing one."""
    username = (username or "").strip().lower()
    if not USERNAME_RE.match(username):
        raise ValueError("Username: 3-50 letters, digits, dot or underscore")
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    user = db.query(User).filter(User.username == username).first()
    if user:
        if user.role not in ("super_admin", "admin"):
            raise ValueError(f"'{username}' is a {user.role} login, not an admin")
        user.password_hash = hash_password(password)
        user.is_active = True
        if full_name.strip():
            user.full_name = full_name.strip()
    else:
        branch = db.query(Branch).order_by(Branch.id).first()
        user = User(
            branch_id=branch.id if branch else None,
            username=username,
            email=f"{username}@admin.local",  # the users table needs an email; admins log in by username
            password_hash=hash_password(password),
            full_name=full_name.strip() or "Admin",
            phone=f"admin:{username}"[:20],  # unique; never a real mobile number
            role="super_admin",
            is_active=True,
        )
        db.add(user)
    db.commit()
    db.refresh(user)
    return user


def ensure_first_admin(db: Session) -> Optional[User]:
    """A database with no logins at all gets its admin from the environment, if given."""
    if db.query(User).first():
        return None
    username, password = os.getenv("DAIRY_ADMIN_USERNAME"), os.getenv("DAIRY_ADMIN_PASSWORD")
    if not (username and password):
        logger.warning("No admin login exists. Create one with: python backend/create_admin.py")
        return None
    user = save_admin(db, username, password)
    logger.info("First admin login created from DAIRY_ADMIN_USERNAME.")
    return user
