"""Migrate SQLite data into Postgres.

Usage:
  python scripts/migrate_sqlite_to_postgres.py \
    --sqlite sqlite:///./data/omniai.db \
    --postgres postgresql://user:pass@host:5432/omniai \
    --dry-run
"""
import argparse
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db.models import (
    User,
    Session,
    Conversation,
    Message,
    InviteCode,
    ToolReceipt,
    ToolFavorite,
    ToolSetting,
    MediaAsset,
    MediaJob,
)

MODELS = [
    User,
    Session,
    Conversation,
    Message,
    InviteCode,
    ToolReceipt,
    ToolFavorite,
    ToolSetting,
    MediaAsset,
    MediaJob,
]


def parse_args():
    parser = argparse.ArgumentParser(description="Migrate SQLite to Postgres")
    parser.add_argument("--sqlite", required=True, help="SQLite database URL")
    parser.add_argument("--postgres", required=True, help="Postgres database URL")
    parser.add_argument("--dry-run", action="store_true", help="Do not write to Postgres")
    return parser.parse_args()


def copy_model(src_session, dest_session, model, dry_run: bool):
    rows = src_session.query(model).all()
    print(f"{model.__tablename__}: {len(rows)} rows")
    if dry_run:
        return
    for row in rows:
        dest_session.merge(row)
    dest_session.commit()


def main():
    args = parse_args()
    src_engine = create_engine(
        args.sqlite,
        connect_args={"check_same_thread": False} if args.sqlite.startswith("sqlite") else {},
    )
    dest_engine = create_engine(args.postgres)

    SrcSession = sessionmaker(bind=src_engine)
    DestSession = sessionmaker(bind=dest_engine)

    src_session = SrcSession()
    dest_session = DestSession()

    try:
        print(f"Starting migration at {datetime.utcnow().isoformat()}Z")
        for model in MODELS:
            copy_model(src_session, dest_session, model, args.dry_run)
        print("Migration complete")
    finally:
        src_session.close()
        dest_session.close()


if __name__ == "__main__":
    main()
