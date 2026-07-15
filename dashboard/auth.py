"""
auth.py - JWT-based authentication for Valve Diagnostics POC

Users are stored in Postgres (see db_store.get_user_by_email / create_user).
JWT token is issued on login and stored as an HTTP-only cookie.

SECRET_KEY has no hardcoded fallback — it must be set as an environment
variable, or the app refuses to start. Same for the initial admin account:
there is no built-in credential; call ensure_bootstrap_admin() once at
startup and it creates ADMIN_EMAIL/ADMIN_PASSWORD (from env) as the first
user, if those env vars are set and that account doesn't already exist.
"""

import hashlib
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Cookie, HTTPException, status

import db_store

# ── Config ────────────────────────────────────────────────────────────────────
SECRET_KEY = os.environ.get("SECRET_KEY", "").strip()
if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY environment variable is not set. Generate one, e.g.\n"
        '    python -c "import secrets; print(secrets.token_hex(32))"\n'
        "and add it to your .env (local) / Render environment settings (prod)."
    )
ALGORITHM  = "HS256"
TOKEN_TTL_HOURS = 8


# ── User store ────────────────────────────────────────────────────────────────

def _hash_password(password: str) -> str:
    """Simple SHA-256 hash for password storage."""
    return hashlib.sha256(password.encode()).hexdigest()


async def ensure_bootstrap_admin():
    """Create the initial admin account from ADMIN_EMAIL/ADMIN_PASSWORD env
    vars, if it doesn't already exist. No-op (with a warning) if those env
    vars aren't set — there is no hardcoded fallback credential. Call this
    once at app startup."""
    admin_email = os.getenv("ADMIN_EMAIL", "").strip().lower()
    admin_password = os.getenv("ADMIN_PASSWORD", "").strip()
    if not admin_email or not admin_password:
        print("⚠️  ADMIN_EMAIL / ADMIN_PASSWORD not set — no bootstrap admin "
              "created. Set both env vars if you need an initial admin login.")
        return
    if await db_store.get_user_by_email(admin_email):
        return
    await db_store.create_user(admin_email, _hash_password(admin_password),
                                "Admin", role="admin")
    print(f"✅  Bootstrap admin created: {admin_email}")


async def register_user(email: str, password: str, name: str) -> tuple[bool, str]:
    """Register a new user in Postgres. Returns (success, message)."""
    email = email.strip().lower()
    if not email or not password or not name:
        return False, "All fields are required."
    ok = await db_store.create_user(email, _hash_password(password), name, role="client")
    if not ok:
        return False, "An account with this email already exists."
    return True, "Account created successfully."


async def authenticate_user(email: str, password: str) -> Optional[dict]:
    """Return user dict if credentials match, else None."""
    email = email.strip().lower()
    user = await db_store.get_user_by_email(email)
    if user and user["password_hash"] == _hash_password(password):
        return {"email": user["email"], "name": user["name"], "role": user["role"]}
    return None


# ── Token creation / verification ─────────────────────────────────────────────

def create_access_token(user: dict) -> str:
    payload = {
        "sub":   user["email"],
        "name":  user["name"],
        "role":  user["role"],
        "exp":   datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT. Raises HTTPException on failure."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired – please log in again.",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token – please log in again.",
        )


# ── FastAPI dependency ─────────────────────────────────────────────────────────

def get_current_user(access_token: Optional[str] = Cookie(default=None)) -> dict:
    """FastAPI dependency: validates cookie and returns the current user payload."""
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
        )
    return decode_token(access_token)
