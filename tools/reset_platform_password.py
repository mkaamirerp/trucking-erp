#!/usr/bin/env python3
"""
One-off script to set a platform user's password (no "forgot password" flow in app).
Uses platform DB (DATABASE_URL). Run from repo root with app on PYTHONPATH.

Platform migrations: run from repo root, not from tools/:
  cd /path/to/trucking_erp && alembic -c alembic_platform.ini upgrade head

Usage:
  # Prompt for new password (recommended; not stored in shell history):
  RESET_PASSWORD_EMAIL=mkaamir@gmail.com python tools/reset_platform_password.py

  # Or pass email as first arg and password via env:
  RESET_PASSWORD_EMAIL=mkaamir@gmail.com RESET_PASSWORD_NEW='your-new-password' python tools/reset_platform_password.py

  # Inside Docker (use container's env for DATABASE_URL):
  docker exec -e RESET_PASSWORD_EMAIL=mkaamir@gmail.com -e RESET_PASSWORD_NEW=yournewpass truckerp-api python -c "
  import asyncio, os, sys
  sys.path.insert(0, '/app')
  from app.core.database import AsyncSessionLocal
  from app.utils.password import hash_password
  from app.models.platform import PlatformUser
  from sqlalchemy import select, update
  async def run():
      email = os.environ['RESET_PASSWORD_EMAIL'].strip().lower()
      password = os.environ['RESET_PASSWORD_NEW']
      async with AsyncSessionLocal() as session:
          r = await session.execute(update(PlatformUser).where(PlatformUser.email == email).values(password_hash=hash_password(password)))
          if r.rowcount == 0:
              print('No user with that email'); return 1
          await session.commit()
      print('Password updated for', email); return 0
  exit(asyncio.run(run()))
  "
"""
from __future__ import annotations

import asyncio
import getpass
import os
import sys


async def main() -> int:
    email = (os.environ.get("RESET_PASSWORD_EMAIL") or (sys.argv[1] if len(sys.argv) > 1 else "")).strip().lower()
    if not email:
        print("Usage: RESET_PASSWORD_EMAIL=user@example.com python tools/reset_platform_password.py", file=sys.stderr)
        print("   or: python tools/reset_platform_password.py user@example.com", file=sys.stderr)
        return 1

    password = os.environ.get("RESET_PASSWORD_NEW")
    if not password:
        password = getpass.getpass("New password: ")
    if not password.strip():
        print("Password cannot be empty", file=sys.stderr)
        return 1

    # Import after possible getpass so .env can be loaded first
    from app.core.database import AsyncSessionLocal
    from app.models.platform import PlatformUser
    from app.utils.password import hash_password
    from sqlalchemy import update

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            update(PlatformUser)
            .where(PlatformUser.email == email)
            .values(password_hash=hash_password(password))
        )
        if result.rowcount == 0:
            print(f"No user found with email: {email}", file=sys.stderr)
            return 1
        await session.commit()
    print(f"Password updated for {email}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    exit(asyncio.run(main()))
