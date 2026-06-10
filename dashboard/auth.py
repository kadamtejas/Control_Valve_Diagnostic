"""
auth.py - JWT-based authentication for Valve Diagnostics POC

Users are stored in users.json at the project root.
JWT token is issued on login and stored as an HTTP-only cookie.
"""

import json
import os
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import jwt
from fastapi import Cookie, HTTPException, status

# ── Config ────────────────────────────────────────────────────────────────────
SECRET_KEY = os.environ.get("SECRET_KEY", "ingenero-valve-poc-secret-key-2024")
ALGORITHM  = "HS256"
TOKEN_TTL_HOURS = 8

USERS_FILE = Path(__file__).parent.parent / "users.json"

# ── Built-in fallback users (used when users.json is not present e.g. on Render)
FALLBACK_USERS = [
    {
        "email": "admin@ingenero.com",
        "password": "ingenero@2024",
        "name": "Ingenero Admin",
        "role": "admin"
    }
]

# ── In-memory user store (survives within a single server process, wiped on restart)
_runtime_users: list[dict] = []


# ── User store ────────────────────────────────────────────────────────────────

def _hash_password(password: str) -> str:
    """Simple SHA-256 hash for password storage."""
    return hashlib.sha256(password.encode()).hexdigest()


def _load_users() -> list[dict]:
    """Return combined list: file users + runtime-registered users."""
    file_users = []
    if USERS_FILE.exists():
        try:
            with open(USERS_FILE, "r") as f:
                file_users = json.load(f)["users"]
        except Exception:
            file_users = list(FALLBACK_USERS)
    else:
        file_users = list(FALLBACK_USERS)
    # Merge: runtime users take precedence (avoid duplicates by email)
    file_emails = {u["email"].lower() for u in file_users}
    extra = [u for u in _runtime_users if u["email"].lower() not in file_emails]
    return file_users + extra


def register_user(email: str, password: str, name: str) -> tuple[bool, str]:
    """
    Register a new user. Returns (success, message).
    Saves to users.json if writable, otherwise stores in memory only.
    """
    email = email.strip().lower()
    if not email or not password or not name:
        return False, "All fields are required."
    # Check duplicate across all users
    for u in _load_users():
        if u["email"].lower() == email:
            return False, "An account with this email already exists."
    new_user = {
        "email": email,
        "password": _hash_password(password),
        "name": name.strip(),
        "role": "client",
        "hashed": True,
    }
    # Try to persist to users.json
    try:
        if USERS_FILE.exists():
            with open(USERS_FILE, "r") as f:
                data = json.load(f)
        else:
            data = {"users": list(FALLBACK_USERS)}
        data["users"].append(new_user)
        with open(USERS_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        # Filesystem not writable (e.g. Render) — store in memory only
        pass
    _runtime_users.append(new_user)
    return True, "Account created successfully."


def authenticate_user(email: str, password: str) -> Optional[dict]:
    """Return user dict if credentials match, else None."""
    email = email.strip().lower()
    for user in _load_users():
        stored_pw = user["password"]
        # Support both hashed (new) and plain-text (legacy) passwords
        if user.get("hashed"):
            match = stored_pw == _hash_password(password)
        else:
            match = stored_pw == password
        if user["email"].lower() == email and match:
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
