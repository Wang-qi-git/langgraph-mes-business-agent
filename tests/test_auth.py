"""JWT 认证测试"""
import pytest


def test_verify_password_correct():
    import auth
    assert auth.verify_password("admin", "admin123") is True
    assert auth.verify_password("operator", "op123") is True


def test_verify_password_wrong():
    import auth
    assert auth.verify_password("admin", "wrong") is False
    assert auth.verify_password("nonexistent", "any") is False


def test_create_and_decode_token():
    import auth
    token = auth.create_access_token("admin")
    assert isinstance(token, str)

    payload = auth.decode_token(token)
    assert payload is not None
    assert payload["sub"] == "admin"
    assert payload["role"] == "admin"


def test_decode_invalid_token():
    import auth
    assert auth.decode_token("invalid.token.here") is None


def test_get_user_info():
    import auth
    info = auth.get_user_info("supervisor")
    assert info["role"] == "supervisor"
    assert info["name"] == "班组长"

    assert auth.get_user_info("nonexistent") is None