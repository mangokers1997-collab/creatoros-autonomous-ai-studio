from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

SESSION_COOKIE = "creatoros_session"
SESSION_DAYS = int(os.getenv("CREATOROS_SESSION_DAYS", "7"))
PBKDF2_ITERATIONS = 310_000

def _db_path() -> Path:
    return Path(os.getenv("CREATOROS_DB_PATH", "creatoros.db"))

def _connect():
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_auth_tables() -> None:
    with _connect() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS auth_users (
            id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS auth_sessions (
            token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL,
            expires_at TEXT NOT NULL, created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES auth_users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_auth_sessions_expiry ON auth_sessions(expires_at);
        """)

def _now() -> datetime:
    return datetime.now(timezone.utc)

def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return "pbkdf2_sha256$" + str(PBKDF2_ITERATIONS) + "$" + salt.hex() + "$" + digest.hex()

def _verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256": return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations))
        return hmac.compare_digest(actual.hex(), digest_hex)
    except (ValueError, TypeError):
        return False

def _public_user(row: sqlite3.Row) -> dict:
    return {"id": row["id"], "username": row["username"], "created_at": row["created_at"]}

def create_owner(username: str, password: str) -> tuple[dict, str]:
    username = username.strip()
    if not 3 <= len(username) <= 40 or not all(ch.isalnum() or ch in "_-" for ch in username):
        raise ValueError("Username must be 3–40 characters using letters, numbers, _ or -.")
    if len(password) < 12 or len(password) > 128:
        raise ValueError("Password must contain 12–128 characters.")
    now = _now()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT 1 FROM auth_users LIMIT 1").fetchone():
            raise RuntimeError("Owner account is already initialized. Use login instead.")
        user_id = secrets.token_urlsafe(18)
        conn.execute("INSERT INTO auth_users(id,username,password_hash,created_at) VALUES(?,?,?,?)",
                     (user_id, username, _hash_password(password), now.isoformat()))
        token = secrets.token_urlsafe(48)
        conn.execute("INSERT INTO auth_sessions(token_hash,user_id,expires_at,created_at) VALUES(?,?,?,?)",
                     (hashlib.sha256(token.encode()).hexdigest(), user_id,
                      (now + timedelta(days=SESSION_DAYS)).isoformat(), now.isoformat()))
        row = conn.execute("SELECT id,username,created_at FROM auth_users WHERE id=?", (user_id,)).fetchone()
        return _public_user(row), token

def login(username: str, password: str) -> tuple[dict, str] | None:
    with _connect() as conn:
        row = conn.execute("SELECT id,username,password_hash,created_at FROM auth_users WHERE username=? COLLATE NOCASE",
                           (username.strip(),)).fetchone()
        if not row or not _verify_password(password, row["password_hash"]): return None
        now = _now()
        token = secrets.token_urlsafe(48)
        conn.execute("INSERT INTO auth_sessions(token_hash,user_id,expires_at,created_at) VALUES(?,?,?,?)",
                     (hashlib.sha256(token.encode()).hexdigest(), row["id"],
                      (now + timedelta(days=SESSION_DAYS)).isoformat(), now.isoformat()))
        return _public_user(row), token

def get_session(token: str | None) -> dict | None:
    if not token or len(token) > 256: return None
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with _connect() as conn:
        row = conn.execute("SELECT u.id,u.username,u.created_at FROM auth_sessions s JOIN auth_users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?",
                           (token_hash, _now().isoformat())).fetchone()
        return _public_user(row) if row else None

def revoke_session(token: str | None) -> None:
    if not token or len(token) > 256: return
    with _connect() as conn:
        conn.execute("DELETE FROM auth_sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))

def owner_exists() -> bool:
    with _connect() as conn:
        return conn.execute("SELECT 1 FROM auth_users LIMIT 1").fetchone() is not None
