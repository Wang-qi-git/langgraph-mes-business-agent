"""
JWT 认证模块
- 用户库（生产环境应换成 DB + bcrypt）
- Token 生成/解析
- FastAPI 依赖：get_current_user
"""
import os
import hashlib
from datetime import datetime, timedelta
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# ==================== 配置 ====================
JWT_SECRET = os.getenv("JWT_SECRET", "mes-agent-secret-change-me-in-prod")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24

# ==================== 用户库 ====================
# 密码用 SHA256 简化；生产环境应换 bcrypt
def _h(pwd: str) -> str:
    return hashlib.sha256(pwd.encode("utf-8")).hexdigest()

USERS = {
    "operator": {
        "password_hash": _h("op123"),
        "role": "operator",
        "name": "车间操作员",
    },
    "supervisor": {
        "password_hash": _h("sup123"),
        "role": "supervisor",
        "name": "班组长",
    },
    "admin": {
        "password_hash": _h("admin123"),
        "role": "admin",
        "name": "系统管理员",
    },
}

# ==================== Bearer 解析器 ====================
bearer_scheme = HTTPBearer(auto_error=False)


# ==================== 工具函数 ====================
def verify_password(username: str, password: str) -> bool:
    user = USERS.get(username)
    if not user:
        return False
    return _h(password) == user["password_hash"]


def get_user_info(username: str) -> Optional[dict]:
    u = USERS.get(username)
    if not u:
        return None
    return {"username": username, "role": u["role"], "name": u["name"]}


def create_access_token(username: str) -> str:
    user = USERS[username]
    now = datetime.utcnow()
    payload = {
        "sub": username,
        "role": user["role"],
        "name": user["name"],
        "iat": now,
        "exp": now + timedelta(hours=JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ==================== FastAPI 依赖 ====================
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    """从 Authorization: Bearer xxx 解析出 {username, role, name}"""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少认证信息",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {
        "username": payload["sub"],
        "role": payload["role"],
        "name": payload["name"],
    }