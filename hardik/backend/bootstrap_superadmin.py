"""Explicit bootstrap/reset operation for the initial Super Admin account."""

import os

from backend.auth.security import hash_password
from backend.database.session import SessionLocal
from backend.models import Role, User

EMAIL = "admin@gmail.com"


def bootstrap() -> None:
    password = os.environ.get("INITIAL_SUPERADMIN_PASSWORD")
    if password is not None and len(password) < 12:
        raise SystemExit("INITIAL_SUPERADMIN_PASSWORD must be at least 12 characters")

    with SessionLocal() as db:
        user = db.query(User).filter(User.email == EMAIL).first()
        if user is None:
            raise SystemExit(f"Required existing account not found: {EMAIL}")
        role = db.query(Role).filter(Role.role_name == "Super Admin").first()
        if role is None:
            raise SystemExit("Protected Super Admin role is missing")
        if role.authority_level != 100 or not role.is_system_role or role.is_assignable:
            raise SystemExit("Existing Super Admin role metadata is invalid")

        user.role_id = role.id
        user.status = "active"
        user.max_concurrent_sessions = 3
        if password is not None:
            user.password_hash = hash_password(password)
        db.commit()

    print(f"Bootstrapped {EMAIL} as Super Admin")
    if password is not None:
        print("Password updated from INITIAL_SUPERADMIN_PASSWORD")
    else:
        print("Password unchanged")


if __name__ == "__main__":
    bootstrap()
