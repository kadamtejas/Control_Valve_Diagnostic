"""
auth.py - JWT-based authentication for Valve Diagnostics POC

Users are stored in users.json at the project root.
JWT token is issued on login and stored as an HTTP-only cookie.
"""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import jwt
from fastapi import Cookie, HTTPException, status

# ── Config ────────────────────────────────────────────────────────────────────
SECRET_KEY = "ingenero-valve-poc-secret-key-2024"   # change before Azure deploy
ALGORITHM  = "HS256"
TOKEN_TTL_HOURS = 8

USERS_FILE = Path(__file__).parent.parent / "users.json"


# ── User store ────────────────────────────────────────────────────────────────

def _load_users() -> list[dict]:
    with open(USERS_FILE, "r") as f:
        return json.load(f)["users"]


def authenticate_user(email: str, password: str) -> Optional[dict]:
    """Return user dict if credentials match, else None."""
    email = email.strip().lower()
    for user in _load_users():
        if user["email"].lower() == email and user["password"] == password:
            return user
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
    """Decode and validate a JWT.  Raises HTTPException on failure."""
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
