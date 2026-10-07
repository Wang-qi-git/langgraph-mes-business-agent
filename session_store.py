"""
会话存储（v2）：每个会话绑定到用户，防止越权访问
"""
import os
import sqlite3
import uuid
import threading
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sessions.db")
_LOCK = threading.Lock()


def _conn():
    c = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with _LOCK:
        c = _conn()
        try:
            c.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    owner TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_session ON messages(session_id, id)")
            c.commit()
        finally:
            c.close()


def create_session(owner: str = "anonymous") -> str:
    sid = uuid.uuid4().hex[:12]
    with _LOCK:
        c = _conn()
        try:
            c.execute(
                "INSERT INTO sessions (session_id, owner, created_at) VALUES (?, ?, ?)",
                (sid, owner, datetime.now().isoformat()),
            )
            c.commit()
        finally:
            c.close()
    return sid


def session_belongs_to(sid: str, owner: str) -> bool:
    """判断会话是否属于该用户"""
    c = _conn()
    try:
        row = c.execute(
            "SELECT owner FROM sessions WHERE session_id = ?", (sid,)
        ).fetchone()
        if row is None:
            # 兼容旧数据：messages 表里有没有这个 sid
            row2 = c.execute(
                "SELECT 1 FROM messages WHERE session_id = ? LIMIT 1", (sid,)
            ).fetchone()
            return row2 is not None
        return row["owner"] == owner
    finally:
        c.close()


def append_message(session_id: str, role: str, content: str):
    with _LOCK:
        c = _conn()
        try:
            c.execute(
                "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (session_id, role, content, datetime.now().isoformat()),
            )
            c.commit()
        finally:
            c.close()


def get_messages(session_id: str, limit: int = 20) -> list[dict]:
    c = _conn()
    try:
        rows = c.execute(
            "SELECT role, content, created_at FROM messages "
            "WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]
    finally:
        c.close()


def clear_session(session_id: str):
    with _LOCK:
        c = _conn()
        try:
            c.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            c.commit()
        finally:
            c.close()


def list_sessions(limit: int = 20) -> list[dict]:
    c = _conn()
    try:
        rows = c.execute("""
            SELECT session_id, COUNT(*) as msg_count, MAX(created_at) as last_active
            FROM messages GROUP BY session_id ORDER BY last_active DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        c.close()


init_db()