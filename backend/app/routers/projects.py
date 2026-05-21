"""项目 CRUD 路由。"""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl

from ..config import Settings
from ..database import Database
from ..deps import get_current_user, get_db, get_existing_project, get_settings
from ..core.repository import RepositoryError, normalize_repo_url, project_id_for, project_name_for

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    repo_url: HttpUrl


class ProjectPinUpdate(BaseModel):
    pinned: bool


@router.get("")
def list_projects(current_user: dict = Depends(get_current_user), db: Database = Depends(get_db)):
    return {"projects": db.list_projects_for_user(current_user["id"], include_report=False)}


@router.post("")
def create_project(
    payload: ProjectCreate,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """创建新项目（或返回已存在的项目）。"""
    try:
        repo_url = normalize_repo_url(str(payload.repo_url), settings.allowed_host_set)
    except RepositoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    existing = db.get_project_by_repo_for_user(repo_url, current_user["id"])
    if existing:
        return existing

    project_id = project_id_for(f"{current_user['id']}:{repo_url}")
    project = {
        "id": project_id,
        "user_id": current_user["id"],
        "repo_url": repo_url,
        "name": project_name_for(repo_url),
        "local_path": str(settings.clone_dir / project_id),
        "status": "created",
    }
    return db.upsert_project_for_user(current_user["id"], project)


@router.get("/{project_id}")
def get_project(project_id: str, current_user: dict = Depends(get_current_user), db: Database = Depends(get_db)):
    project = db.get_project_for_user(project_id, current_user["id"])
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project_id: str,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    project = get_existing_project(project_id, current_user, db)

    if not db.delete_project_for_user(project_id, current_user["id"]):
        raise HTTPException(status_code=404, detail="项目不存在")

    local_path = Path(project["local_path"]).resolve()
    clone_root = settings.clone_dir.resolve()
    if local_path == clone_root or clone_root not in local_path.parents:
        return None

    shutil.rmtree(local_path, ignore_errors=True)
    return None


@router.patch("/{project_id}/pin")
def update_project_pin(
    project_id: str,
    payload: ProjectPinUpdate,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    get_existing_project(project_id, current_user, db)
    project = db.set_pinned(project_id, payload.pinned)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project
