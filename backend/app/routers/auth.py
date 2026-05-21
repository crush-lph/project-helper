"""认证路由：注册、登录。"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..database import Database
from ..deps import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


class AuthRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=40, pattern=r"^[a-zA-Z0-9_-]+$")
    password: str = Field(..., min_length=6, max_length=128)


@router.post("/register")
def register(payload: AuthRequest, db: Database = Depends(get_db)):
    """注册用户，成功后直接创建会话。"""
    try:
        user = db.create_user(payload.username, payload.password)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="用户名已存在。") from exc
    token = db.create_session(user["id"])
    return {"user": user, "token": token}


@router.post("/login")
def login(payload: AuthRequest, db: Database = Depends(get_db)):
    """用户名密码登录。"""
    user = db.verify_user_password(payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误。")
    token = db.create_session(user["id"])
    return {"user": user, "token": token}
