from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, HttpUrl

from .analyzer import analyze_project_stream, chat_stream
from .config import get_settings
from .database import Database
from .repository import RepositoryError, normalize_repo_url, project_id_for, project_name_for
from .source_scan import SourceBrowseError, build_source_tree, read_source_file


settings = get_settings()
db = Database(settings.db_path)

app = FastAPI(title="project-helper API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProjectCreate(BaseModel):
    repo_url: HttpUrl


class ProjectPinUpdate(BaseModel):
    pinned: bool


class ChatRequest(BaseModel):
    question: str


@app.get("/api/health")
def health():
    return {"ok": True, "model": settings.deepseek_model, "llm_configured": bool(settings.deepseek_api_key)}


@app.get("/api/projects")
def list_projects():
    return {"projects": db.list_projects(include_report=False)}


@app.post("/api/projects")
def create_project(payload: ProjectCreate):
    try:
        repo_url = normalize_repo_url(str(payload.repo_url), settings.allowed_host_set)
    except RepositoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    existing = db.get_project_by_repo(repo_url)
    if existing:
        return existing

    project_id = project_id_for(repo_url)
    project = {
        "id": project_id,
        "repo_url": repo_url,
        "name": project_name_for(repo_url),
        "local_path": str(settings.clone_dir / project_id),
        "status": "created",
    }
    return db.upsert_project(project)


@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


def get_ready_project(project_id: str) -> dict:
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    if project["status"] != "ready":
        raise HTTPException(status_code=409, detail="项目尚未完成分析，暂不能查看源码。")
    local_path = Path(project["local_path"])
    if not local_path.exists() or not local_path.is_dir():
        raise HTTPException(status_code=404, detail="本地源码目录不存在，请重新分析项目。")
    return project


@app.get("/api/projects/{project_id}/source/tree")
def get_source_tree(project_id: str):
    project = get_ready_project(project_id)
    return {"tree": build_source_tree(Path(project["local_path"]))}


@app.get("/api/projects/{project_id}/source/file")
def get_source_file(project_id: str, path: str = Query(..., min_length=1)):
    project = get_ready_project(project_id)
    try:
        return read_source_file(Path(project["local_path"]), path)
    except SourceBrowseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/api/projects/{project_id}/pin")
def update_project_pin(project_id: str, payload: ProjectPinUpdate):
    project = db.set_pinned(project_id, payload.pinned)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


@app.delete("/api/projects/{project_id}", status_code=204)
def delete_project(project_id: str):
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    deleted = db.delete_project(project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="项目不存在")

    local_path = Path(project["local_path"]).resolve()
    clone_root = settings.clone_dir.resolve()
    if local_path == clone_root or clone_root not in local_path.parents:
        return None
    shutil.rmtree(local_path, ignore_errors=True)
    return None


@app.get("/api/projects/{project_id}/analyze/stream")
def stream_analysis(project_id: str):
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return StreamingResponse(
        analyze_project_stream(db, settings, project),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/projects/{project_id}/chat/stream")
def stream_chat(project_id: str, payload: ChatRequest):
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")
    return StreamingResponse(
        chat_stream(settings, project, payload.question.strip()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
