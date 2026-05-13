"""
FastAPI 应用入口 —— 定义所有 HTTP 路由

这个文件做什么？
  定义 10 个 REST API 端点，包括：
    - 健康检查、项目 CRUD、源码浏览
    - SSE 流式分析和问答

前端类比：
  这个文件相当于 Express.js/Koa 的路由文件，或者 Next.js 的 API routes。
  - @app.get("/api/health")  类似 router.get("/api/health", handler)
  - @app.post(...)           类似 router.post(...)
  - FastAPI 自动做请求校验（基于 Pydantic 模型），类似 Express + Joi/Zod

Python 知识点 —— 装饰器路由：
  @app.get("/api/health")
  def health():
      ...
  @app.get 是装饰器，它把 health 函数注册为 GET /api/health 的处理函数。
  类似 Express 的 app.get("/api/health", (req, res) => {...})

Python 知识点 —— Pydantic BaseModel：
  class ChatRequest(BaseModel):
      question: str = Field(..., min_length=1, max_length=2000)
  定义请求体的结构和校验规则。
  FastAPI 会自动：
    1. 解析 JSON 请求体
    2. 校验类型和约束
    3. 如果校验失败，返回 422 错误
  类似 Express + Zod schema 校验。

Python 知识点 —— raise：
  raise HTTPException(status_code=404, detail="项目不存在")
  抛出异常。类似 JS 的 throw new Error()。
  FastAPI 会捕获 HTTPException，返回对应的 HTTP 响应。
"""

from __future__ import annotations

import asyncio
import os
import shutil
from collections import defaultdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, HttpUrl

from .config import get_settings
from .database import Database
from .guardrails import check_prompt_injection
from .observability import get_metrics
from .repository import RepositoryError, normalize_repo_url, project_id_for, project_name_for
from .services.analysis import analyze_project_stream
from .services.chat import chat_stream
from .source_scan import SourceBrowseError, build_source_tree, read_source_file

settings = get_settings()

os.environ.pop("SSL_CERT_FILE", None)
if settings.ssl_cert_file:
    os.environ["SSL_CERT_FILE"] = settings.ssl_cert_file

db = Database(settings.db_path)
_analysis_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

app = FastAPI(title="project-helper API", version="0.1.0")

# CORS — 根据环境配置允许的来源
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)

# ---- Static file directory (production: frontend dist) ----
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


# ---- Rate Limiting (simple in-memory) ----

class _RateLimiter:
    """Simple sliding-window rate limiter per IP."""

    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = window_seconds
        self._requests: dict[str, list[float]] = {}

    def is_allowed(self, key: str) -> bool:
        import time
        now = time.monotonic()
        cutoff = now - self.window
        timestamps = self._requests.setdefault(key, [])
        # Prune old entries
        self._requests[key] = [t for t in timestamps if t > cutoff]
        if len(self._requests[key]) >= self.max_requests:
            return False
        self._requests[key].append(now)
        return True


_rate_limiter = _RateLimiter(max_requests=30, window_seconds=60)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # Only rate-limit expensive endpoints
    if request.url.path.endswith("/chat/stream") or request.url.path.endswith("/analyze/stream"):
        client_ip = request.client.host if request.client else "unknown"
        if not _rate_limiter.is_allowed(client_ip):
            return JSONResponse(status_code=429, content={"detail": "请求过于频繁，请稍后重试。"})
    response = await call_next(request)
    # Security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# ---- 请求体模型 ----

class ProjectCreate(BaseModel):
    """
    创建项目的请求体。

    Python 知识点 —— Pydantic 自动校验：
      repo_url: HttpUrl
      HttpUrl 是 Pydantic 内置的 URL 类型，会自动校验格式。
      如果用户传的不是合法 URL，FastAPI 自动返回 422 错误。
      类似 Zod 的 z.string().url()
    """
    repo_url: HttpUrl


class ProjectPinUpdate(BaseModel):
    """更新项目置顶状态的请求体。"""
    pinned: bool


class ChatRequest(BaseModel):
    """
    问答请求体。

    Field(..., min_length=1, max_length=2000) 的含义：
      ...        → 必填（类似 Zod 的 .min(1)）
      min_length → 最短 1 个字符
      max_length → 最长 2000 个字符
    超出范围时，FastAPI 自动返回 422 错误。

    注意：聊天历史由 Agent checkpointer 自动管理，不再需要前端传递 history。
    """
    question: str = Field(..., min_length=1, max_length=2000)
    file_paths: list[str] = Field(default_factory=list, max_length=10)


class SourceAnnotationCreate(BaseModel):
    """创建源码批注的请求体。"""
    path: str = Field(..., min_length=1, max_length=1000)
    line: int | None = Field(default=None, ge=1)
    body: str = Field(..., min_length=1, max_length=4000)


class SourceAnnotationUpdate(BaseModel):
    """更新源码批注正文的请求体。"""
    body: str = Field(..., min_length=1, max_length=4000)


# ---- 路由定义 ----

@app.get("/api/health")
def health():
    return {"ok": True, "model": settings.deepseek_model, "llm_configured": bool(settings.deepseek_api_key)}


@app.get("/api/metrics")
def metrics():
    return get_metrics().snapshot()


@app.get("/api/projects")
def list_projects():
    """
    获取所有项目列表。

    include_report=False 表示不返回完整的报告内容（太大了），
    只返回摘要信息用于侧边栏显示。
    """
    return {"projects": db.list_projects(include_report=False)}


@app.post("/api/projects")
def create_project(payload: ProjectCreate):
    """
    创建新项目（或返回已存在的项目）。

    Python 知识点 —— 函数参数中的 Pydantic 模型：
      def create_project(payload: ProjectCreate):
      FastAPI 会自动把 JSON 请求体解析为 ProjectCreate 实例。
      如果解析失败（比如 repo_url 不是合法 URL），自动返回 422。
      类似 Express 中间件的 body 校验。
    """
    try:
        repo_url = normalize_repo_url(str(payload.repo_url), settings.allowed_host_set)
    except RepositoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
        # raise ... from exc 保留原始异常链，方便调试

    # 如果这个仓库已经分析过，直接返回现有记录（幂等）
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
    """
    获取单个项目详情。

    Python 知识点 —— 路径参数：
      {project_id} 是路径参数，FastAPI 自动提取并传给函数参数。
      类似 Express 的 router.get("/:projectId", handler)
    """
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


def get_ready_project(project_id: str) -> dict:
    """
    获取已完成分析的项目（内部辅助函数）。

    这个函数被源码浏览端点共用，做了三重检查：
      1. 项目是否存在
      2. 项目是否已完成分析（status == "ready"）
      3. 本地源码目录是否存在
    """
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    if project["status"] != "ready":
        raise HTTPException(status_code=409, detail="项目尚未完成分析，暂不能查看源码。")
    # 409 Conflict：请求本身没问题，但当前状态不允许这个操作
    local_path = Path(project["local_path"])
    if not local_path.exists() or not local_path.is_dir():
        raise HTTPException(status_code=404, detail="本地源码目录不存在，请重新分析项目。")
    return project


def get_existing_project(project_id: str) -> dict:
    """获取项目，不要求项目已完成分析。"""
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


def validate_annotation_target(project_id: str, path: str, line: int | None) -> str:
    """
    校验批注目标文件。

    批注不会写回源码，但创建时仍复用源码浏览的安全路径和文本文件校验。
    """
    project = get_ready_project(project_id)
    try:
        source_file = read_source_file(Path(project["local_path"]), path)
    except SourceBrowseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if line is not None:
        line_count = len(source_file["content"].split("\n")) if source_file["content"] else 0
        if line_count == 0 or line > line_count:
            raise HTTPException(status_code=400, detail="批注行号超出文件范围。")
    return source_file["path"]


@app.get("/api/projects/{project_id}/source/tree")
def get_source_tree(project_id: str):
    """获取源码目录树（用于前端文件浏览器）。"""
    project = get_ready_project(project_id)
    return {"tree": build_source_tree(Path(project["local_path"]))}


@app.get("/api/projects/{project_id}/source/file")
def get_source_file(project_id: str, path: str = Query(..., min_length=1)):
    """
    读取单个源码文件。

    Python 知识点 —— Query 参数：
      path: str = Query(..., min_length=1)
      声明 URL 查询参数（?path=xxx），带校验。
      ... 表示必填，min_length=1 表示不能为空。
      类似 Express 的 req.query.path + Zod 校验。
    """
    project = get_ready_project(project_id)
    try:
        return read_source_file(Path(project["local_path"]), path)
    except SourceBrowseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}/source/annotations")
def list_source_annotations(project_id: str, path: str | None = Query(default=None, min_length=1)):
    """获取项目源码批注，可按文件路径过滤。"""
    get_existing_project(project_id)
    return {"annotations": db.list_source_annotations(project_id, path)}


@app.post("/api/projects/{project_id}/source/annotations")
def create_source_annotation(project_id: str, payload: SourceAnnotationCreate):
    """为源码文件或源码行创建批注。"""
    normalized_path = validate_annotation_target(project_id, payload.path, payload.line)
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=400, detail="批注内容不能为空。")
    return db.create_source_annotation(
        project_id=project_id,
        path=normalized_path,
        line=payload.line,
        body=body,
    )


@app.patch("/api/projects/{project_id}/source/annotations/{annotation_id}")
def update_source_annotation(project_id: str, annotation_id: str, payload: SourceAnnotationUpdate):
    """更新源码批注正文。"""
    get_existing_project(project_id)
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


@app.delete("/api/projects/{project_id}/source/annotations/{annotation_id}", status_code=204)
def delete_source_annotation(project_id: str, annotation_id: str):
    """删除源码批注。"""
    get_existing_project(project_id)
    if not db.delete_source_annotation(project_id=project_id, annotation_id=annotation_id):
        raise HTTPException(status_code=404, detail="批注不存在")
    return None


@app.patch("/api/projects/{project_id}/pin")
def update_project_pin(project_id: str, payload: ProjectPinUpdate):
    """切换项目置顶状态。"""
    project = db.set_pinned(project_id, payload.pinned)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


@app.get("/api/projects/{project_id}/chat/messages")
def list_chat_messages(project_id: str):
    """获取项目的问答历史。"""
    get_existing_project(project_id)
    return {"messages": db.list_chat_messages(project_id)}


@app.delete("/api/projects/{project_id}/chat/messages", status_code=204)
def clear_chat_messages(project_id: str):
    """清空项目的问答历史。"""
    get_existing_project(project_id)
    db.clear_chat_messages(project_id)
    return None


@app.delete("/api/projects/{project_id}", status_code=204)
def delete_project(project_id: str):
    """
    删除项目（数据库记录 + 本地仓库副本）。

    status_code=204 表示成功但无返回体（No Content）。
    类似 Express 的 res.status(204).end()

    Python 知识点 —— shutil.rmtree()：
      递归删除目录及其所有内容。
      类似 Node.js 的 fs.rm(path, { recursive: true })
      ignore_errors=True 忽略删除过程中的错误。
    """
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    deleted = db.delete_project(project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 安全检查：确保要删除的目录确实在 clone_dir 下
    local_path = Path(project["local_path"]).resolve()
    clone_root = settings.clone_dir.resolve()
    if local_path == clone_root or clone_root not in local_path.parents:
        return None  # 路径不在预期范围内，不删除（防御性编程）

    shutil.rmtree(local_path, ignore_errors=True)
    return None


@app.get("/api/projects/{project_id}/analyze/stream")
def stream_analysis(project_id: str):
    """
    SSE 流式分析端点。

    返回 text/event-stream 格式的响应，前端通过 EventSource 接收。
    前端代码：const es = new EventSource(`/api/projects/${id}/analyze/stream`)

    Python 知识点 —— StreamingResponse：
      FastAPI 的流式响应，接收一个"异步生成器"，逐块输出数据。
      类似 Express 的 res.write() + res.end() 模式。
      media_type="text/event-stream" 告诉浏览器这是 SSE 流。

    Python 知识点 —— Headers：
      Cache-Control: no-cache     → 告诉浏览器不要缓存
      X-Accel-Buffering: no       → 告诉 Nginx 不要缓冲（SSE 必须实时推送）
    """
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return StreamingResponse(
        analyze_project_stream(db, settings, project, locks=_analysis_locks),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/projects/{project_id}/chat/stream")
def stream_chat(project_id: str, payload: ChatRequest):
    """
    SSE 流式问答端点。

    和分析端点不同的是：这是 POST 请求（因为要发送问题）。
    前端不能用 EventSource（只支持 GET），需要用 fetch + ReadableStream。

    Python 知识点 —— 多重校验：
      1. Pydantic 自动校验 question 的长度（min_length=1, max_length=2000）
      2. 手动校验空白字符串（strip 后为空）
      3. 手动校验 prompt 注入
      这是"纵深防御"思想：多层校验，任何一层都能拦截问题。
    """
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")
    if check_prompt_injection(payload.question):
        raise HTTPException(status_code=400, detail="问题包含不允许的内容。")
    file_paths = [p for p in (payload.file_paths or []) if p.strip()][:10]
    question_text = payload.question.strip()
    db.add_chat_message(project_id, "user", question_text)

    async def _stream_and_save():
        assistant_text = ""
        async for chunk in chat_stream(settings, project, question_text, file_paths=file_paths):
            if chunk.startswith("event: token\ndata: "):
                import json as _json
                try:
                    data = _json.loads(chunk[len("event: token\ndata: "):].strip())
                    assistant_text += data.get("text", "")
                except Exception:
                    pass
            elif chunk.startswith("event: done"):
                if assistant_text.strip():
                    db.add_chat_message(project_id, "assistant", assistant_text.strip())
            yield chunk

    return StreamingResponse(
        _stream_and_save(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---- Static file serving (production: frontend dist) ----
# Register this after all API routes. The catch-all SPA route would otherwise
# intercept /api/* before FastAPI reaches the concrete API handlers.
if STATIC_DIR.is_dir():
    assets_dir = STATIC_DIR / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def _serve_frontend(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("assets/"):
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        index = STATIC_DIR / "index.html"
        if not index.exists():
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        return FileResponse(str(index))
