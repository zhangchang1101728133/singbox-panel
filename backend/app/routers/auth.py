"""认证路由"""
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
import bcrypt
import jwt
from jwt import PyJWTError
from pydantic import BaseModel

from ..models.database import get_db

router = APIRouter()

SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ── 登录限速 ────────────────────────────────────────────────
# 面板是单实例，用进程内计数即可。目的：挡住对未认证登录接口的暴力破解
# （默认配置下管理员密码可猜，这一层必须存在）。
LOGIN_MAX_FAILURES = int(os.getenv("LOGIN_MAX_FAILURES", "5"))
LOGIN_WINDOW_SECONDS = int(os.getenv("LOGIN_WINDOW_SECONDS", "900"))     # 统计窗口 15 分钟
LOGIN_LOCKOUT_SECONDS = int(os.getenv("LOGIN_LOCKOUT_SECONDS", "900"))   # 触发后锁定 15 分钟

# 只有在反向代理后面才应信任 X-Forwarded-For：面板直接暴露时该头可被伪造，
# 信任它等于送攻击者一个绕过限速的后门。
TRUST_PROXY_HEADERS = os.getenv("TRUST_PROXY_HEADERS", "").lower() in ("1", "true", "yes")

_failures: Dict[str, List[float]] = {}
_locked_until: Dict[str, float] = {}


def _client_ip(request: Request) -> str:
    if TRUST_PROXY_HEADERS:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_rate_limit(ip: str) -> None:
    remaining = _locked_until.get(ip, 0) - time.time()
    if remaining > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"登录失败次数过多，请 {int(remaining) + 1} 秒后再试",
        )


def _record_failure(ip: str) -> None:
    now = time.time()
    recent = [t for t in _failures.get(ip, []) if now - t < LOGIN_WINDOW_SECONDS]
    recent.append(now)
    if len(recent) >= LOGIN_MAX_FAILURES:
        _locked_until[ip] = now + LOGIN_LOCKOUT_SECONDS
        _failures.pop(ip, None)
    else:
        _failures[ip] = recent
    _prune_rate_limit()


def _reset_failures(ip: str) -> None:
    _failures.pop(ip, None)
    _locked_until.pop(ip, None)


def _prune_rate_limit() -> None:
    """清掉过期条目，避免字典随攻击者伪造的 IP 无限增长"""
    now = time.time()
    for ip in [i for i, until in _locked_until.items() if until <= now]:
        _locked_until.pop(ip, None)
    for ip in [i for i, ts in _failures.items()
               if not ts or now - ts[-1] > LOGIN_WINDOW_SECONDS]:
        _failures.pop(ip, None)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user_optional(request: Request) -> Optional[dict]:
    """从 cookie 获取当前用户（可选）"""
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
    except PyJWTError:
        return None

    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = await cursor.fetchone()
        return dict(user) if user else None


async def get_current_user(request: Request) -> dict:
    """从 cookie 获取当前用户（必须）"""
    user = await get_current_user_optional(request)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    return user


@router.post("/login")
async def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    """登录（带失败次数限速）"""
    ip = _client_ip(request)
    _check_rate_limit(ip)

    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM users WHERE username = ?", (form_data.username,))
        user = await cursor.fetchone()
        # 用户名不存在与密码错误返回同一提示，避免用户名枚举
        if not user or not verify_password(form_data.password, user["password_hash"]):
            _record_failure(ip)
            raise HTTPException(status_code=401, detail="用户名或密码错误")

        _reset_failures(ip)
        access_token = create_access_token(data={"sub": user["username"]})
        response = Response(content='{"message": "登录成功"}', media_type="application/json")
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            max_age=86400,
            samesite="lax"
        )
        return response


@router.post("/logout")
async def logout():
    """登出"""
    response = Response(content='{"message": "已登出"}', media_type="application/json")
    response.delete_cookie("access_token")
    return response


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    """当前登录用户信息，未登录返回 401"""
    return {"id": user["id"], "username": user["username"], "is_admin": bool(user["is_admin"])}
