#!/usr/bin/env python3
"""Run database migrations with proper path setup."""

import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Change to backend directory for alembic.ini
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(backend_dir)

from alembic.config import Config
from alembic import command


def upgrade():
    """Run migrations to latest version."""
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    print("✓ Migrations completed successfully")


def downgrade(revision: str = "-1"):
    """Downgrade to a specific revision."""
    alembic_cfg = Config("alembic.ini")
    command.downgrade(alembic_cfg, revision)
    print(f"✓ Downgraded to {revision}")


def current():
    """Show current revision."""
    alembic_cfg = Config("alembic.ini")
    command.current(alembic_cfg, verbose=True)


def history():
    """Show migration history."""
    alembic_cfg = Config("alembic.ini")
    command.history(alembic_cfg, verbose=True)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run database migrations")
    parser.add_argument(
        "command",
        choices=["upgrade", "downgrade", "current", "history"],
        default="upgrade",
        nargs="?",
        help="Migration command to run",
    )
    parser.add_argument(
        "--revision",
        default="-1",
        help="Target revision for downgrade",
    )

    args = parser.parse_args()

    if args.command == "upgrade":
        upgrade()
    elif args.command == "downgrade":
        downgrade(args.revision)
    elif args.command == "current":
        current()
    elif args.command == "history":
        history()
