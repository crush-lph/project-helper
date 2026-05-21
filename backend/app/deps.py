"""FastAPI 依赖注入：数据库、配置、认证。"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, Header, HTTPException, Query, Request

from .config import Settings
from .database import Database


def _token_from_authorization(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def get_db(request: Request) -> Database:
    return request.app.state.db


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    token = _token_from_authorization(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="请先登录。")
    user = db.get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录。")
    return user


def get_current_user_from_query(
    token: str = Query(..., min_length=1),
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    user = db.get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录。")
    return user


def get_existing_project(project_id: str, current_user: dict[str, Any], db: Database) -> dict[str, Any]:
    """获取项目，不要求项目已完成分析。"""
    project = db.get_project_for_user(project_id, current_user["id"])
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project
