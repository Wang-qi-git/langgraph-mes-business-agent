"""会话存储测试"""
import os
import pytest
import tempfile

# 用临时数据库，不污染真实数据
@pytest.fixture(autouse=True)
def temp_db(monkeypatch, tmp_path):
    """每个测试用独立的临时数据库"""
    import session_store
    test_db = tmp_path / "test_sessions.db"
    monkeypatch.setattr(session_store, "DB_PATH", str(test_db))
    session_store.init_db()
    yield
    if test_db.exists():
        test_db.unlink()


def test_create_session():
    import session_store
    sid = session_store.create_session("alice")
    assert isinstance(sid, str)
    assert len(sid) == 12


def test_append_and_get_messages():
    import session_store
    sid = session_store.create_session("bob")
    session_store.append_message(sid, "user", "你好")
    session_store.append_message(sid, "assistant", "您好")

    msgs = session_store.get_messages(sid)
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "你好"
    assert msgs[1]["role"] == "assistant"


def test_session_belongs_to():
    import session_store
    sid = session_store.create_session("alice")
    assert session_store.session_belongs_to(sid, "alice") is True
    assert session_store.session_belongs_to(sid, "bob") is False


def test_clear_session():
    import session_store
    sid = session_store.create_session("alice")
    session_store.append_message(sid, "user", "test")
    session_store.clear_session(sid)
    assert session_store.get_messages(sid) == []


def test_list_sessions():
    import session_store
    sid1 = session_store.create_session("alice")
    sid2 = session_store.create_session("bob")
    session_store.append_message(sid1, "user", "q1")
    session_store.append_message(sid2, "user", "q2")

    sessions = session_store.list_sessions()
    assert len(sessions) == 2