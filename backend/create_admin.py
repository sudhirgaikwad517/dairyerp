"""Create an admin login, or set a new password for one (e.g. a forgotten password).

    python backend/create_admin.py
    docker exec -it dairyerp python backend/create_admin.py      (on the VPS)
"""
import getpass
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.database import Base, SessionLocal, engine  # noqa: E402
from backend.app.models import entities  # noqa: E402,F401
from backend.app.services.admin_account import save_admin  # noqa: E402

if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    username = input("Admin username: ").strip()
    full_name = input("Full name (optional): ").strip()
    password = getpass.getpass("New password: ")
    if password != getpass.getpass("Type the password again: "):
        sys.exit("Passwords do not match. Nothing changed.")
    with SessionLocal() as db:
        try:
            user = save_admin(db, username, password, full_name)
        except ValueError as e:
            sys.exit(f"Not saved: {e}")
    print(f"Saved. '{user.username}' can now log in to the admin panel.")
