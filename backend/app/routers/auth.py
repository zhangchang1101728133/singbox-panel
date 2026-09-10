"""认证路由"""
import os
from datetime import datetime, timedelta
from typing import Optional

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
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """登录"""
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM users WHERE username = ?", (form_data.username,))
        user = await cursor.fetchone()
        if not user or not verify_password(form_data.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="用户名或密码错误")

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
