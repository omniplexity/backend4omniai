"""CLI script to create the first admin user.

Usage:
    python -m backend.scripts.create_admin --username admin --email admin@example.com --password 'YourP@ss1'

This script will only create an admin if no admin user exists yet.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy.orm import sessionmaker

from backend.auth.password import hash_password, validate_password_complexity
from backend.db.database import get_engine
from backend.db.models import User


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the first OmniAI admin user")
    parser.add_argument("--username", required=True, help="Admin username")
    parser.add_argument("--email", required=True, help="Admin email")
    parser.add_argument("--password", required=True, help="Admin password")
    args = parser.parse_args()

    # Validate password complexity
    pw_err = validate_password_complexity(args.password)
    if pw_err:
        print(f"Error: {pw_err}", file=sys.stderr)
        sys.exit(1)

    engine = get_engine()
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    try:
        existing_admin = db.query(User).filter(User.is_admin == True).first()
        if existing_admin:
            print("An admin user already exists. Aborting.", file=sys.stderr)
            sys.exit(1)

        conflict = db.query(User).filter(
            (User.username == args.username) | (User.email == args.email)
        ).first()
        if conflict:
            print(
                f"A user with username '{args.username}' or email '{args.email}' already exists.",
                file=sys.stderr,
            )
            sys.exit(1)

        admin = User(
            email=args.email,
            username=args.username,
            hashed_password=hash_password(args.password),
            is_admin=True,
            is_active=True,
        )
        db.add(admin)
        db.commit()
        print(f"Admin user '{args.username}' created successfully.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
