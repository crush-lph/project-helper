"""分析流路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ..config import Settings
from ..database import Database
from ..deps import get_current_user_from_query, get_db, get_settings
from ..services.analysis import analyze_project_stream

router = APIRouter(prefix="/api/projects/{project_id}/analyze", tags=["analysis"])


@router.get("/stream")
def stream_analysis(
    project_id: str,
    current_user: dict = Depends(get_current_user_from_query),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """SSE 流式分析端点。"""
    project = db.get_project_for_user(project_id, current_user["id"])
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return StreamingResponse(
        analyze_project_stream(db, settings, project),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
