"""
会话存储：基于 SQLite 的多会话隔离
每个 session_id 对应一段独立的对话历史
"""
import os
import sqlite3
import uuid
import threading
from datetime import datetime
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sessions.db")
_LOCK = threading.Lock()


def _conn():
    """每次调用创建新连接（SQLite 轻量场景够用）"""
    c = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    """初始化表结构（幂等）"""
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
                CREATE INDEX IF NOT EXISTS idx_session
                ON messages(session_id, id)
            """)
            c.commit()
        finally:
            c.close()


def create_session() -> str:
    """生成新的 session_id"""
    return uuid.uuid4().hex[:12]


def append_message(session_id: str, role: str, content: str):
    """追加一条消息"""
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
    """获取会话最近 limit 条消息（按时间正序返回）"""
    c = _conn()
    try:
        rows = c.execute(
            "SELECT role, content, created_at FROM messages "
            "WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        # 倒序取出来后反转，保证时间正序
        return [dict(r) for r in reversed(rows)]
    finally:
        c.close()


def clear_session(session_id: str):
    """清空某会话的所有消息"""
    with _LOCK:
        c = _conn()
        try:
            c.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            c.commit()
        finally:
            c.close()


def list_sessions(limit: int = 20) -> list[dict]:
    """列出最近活跃的会话（调试用）"""
    c = _conn()
    try:
        rows = c.execute("""
            SELECT session_id,
                   COUNT(*) as msg_count,
                   MAX(created_at) as last_active
            FROM messages
            GROUP BY session_id
            ORDER BY last_active DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        c.close()


# 导入时自动建表
init_db()