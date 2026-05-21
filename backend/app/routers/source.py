"""源码浏览和批注路由。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..database import Database
from ..deps import get_current_user, get_db, get_existing_project
from ..source_scan import SourceBrowseError, build_source_tree, read_source_file

router = APIRouter(prefix="/api/projects/{project_id}/source", tags=["source"])


class SourceAnnotationCreate(BaseModel):
    path: str = Field(..., min_length=1, max_length=1000)
    line: int | None = Field(default=None, ge=1)
    body: str = Field(..., min_length=1, max_length=4000)


class SourceAnnotationUpdate(BaseModel):
    body: str = Field(..., min_length=1, max_length=4000)


def get_ready_project(project_id: str, current_user: dict, db: Database) -> dict[str, Any]:
    """获取已完成分析的项目。"""
    project = db.get_project_for_user(project_id, current_user["id"])
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    if project["status"] != "ready":
        raise HTTPException(status_code=409, detail="项目尚未完成分析，暂不能查看源码。")
    local_path = Path(project["local_path"])
    if not local_path.exists() or not local_path.is_dir():
        raise HTTPException(status_code=404, detail="本地源码目录不存在，请重新分析项目。")
    return project


def validate_annotation_target(project_id: str, current_user: dict, db: Database, path: str, line: int | None) -> str:
    """校验批注目标文件。"""
    project = get_ready_project(project_id, current_user, db)
    try:
        source_file = read_source_file(Path(project["local_path"]), path)
    except SourceBrowseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if line is not None:
        line_count = len(source_file["content"].split("\n")) if source_file["content"] else 0
        if line_count == 0 or line > line_count:
            raise HTTPException(status_code=400, detail="批注行号超出文件范围。")
    return source_file["path"]


@router.get("/tree")
def get_source_tree(project_id: str, current_user: dict = Depends(get_current_user), db: Database = Depends(get_db)):
    """获取源码目录树。"""
    project = get_ready_project(project_id, current_user, db)
    return {"tree": build_source_tree(Path(project["local_path"]))}


@router.get("/file")
def get_source_file(
    project_id: str,
    path: str = Query(..., min_length=1),
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """读取单个源码文件。"""
    project = get_ready_project(project_id, current_user, db)
    try:
        return read_source_file(Path(project["local_path"]), path)
    except SourceBrowseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/annotations")
def list_source_annotations(
    project_id: str,
    path: str | None = Query(default=None, min_length=1),
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """获取项目源码批注。"""
    get_existing_project(project_id, current_user, db)
    return {"annotations": db.list_source_annotations(project_id, path)}


@router.post("/annotations")
def create_source_annotation(
    project_id: str,
    payload: SourceAnnotationCreate,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """为源码文件或源码行创建批注。"""
    normalized_path = validate_annotation_target(project_id, current_user, db, payload.path, payload.line)
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=400, detail="批注内容不能为空。")
    return db.create_source_annotation(
        project_id=project_id,
        path=normalized_path,
        line=payload.line,
        body=body,
    )


@router.patch("/annotations/{annotation_id}")
def update_source_annotation(
    project_id: str,
    annotation_id: str,
    payload: SourceAnnotationUpdate,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """更新源码批注正文。"""
    get_existing_project(project_id, current_user, db)
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=400, detail="批注内容不能为空。")
    annotation = db.update_source_annotation(
        project_id=project_id,
        annotation_id=annotation_id,
        body=body,
    )
    if not annotation:
        raise HTTPException(status_code=404, detail="批注不存在")
    return annotation


@router.delete("/annotations/{annotation_id}", status_code=204)
def delete_source_annotation(
    project_id: str,
    annotation_id: str,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """删除源码批注。"""
    get_existing_project(project_id, current_user, db)
    if not db.delete_source_annotation(project_id=project_id, annotation_id=annotation_id):
        raise HTTPException(status_code=404, detail="批注不存在")
    return None
