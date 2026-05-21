"""聊天路由：消息列表、清空、流式问答。"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..config import Settings
from ..database import Database
from ..deps import get_current_user, get_db, get_existing_project, get_settings
from ..utils.errors import classify_error
from ..utils.guardrails import check_prompt_injection
from ..services.chat import chat_stream
from ..utils.sse import parse_sse_data

router = APIRouter(prefix="/api/projects/{project_id}/chat", tags=["chat"])


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    file_paths: list[str] = Field(default_factory=list, max_length=10)


@router.get("/messages")
def list_chat_messages(
    project_id: str,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    get_existing_project(project_id, current_user, db)
    return {"messages": db.list_chat_messages(project_id)}


@router.delete("/messages", status_code=204)
def clear_chat_messages(
    project_id: str,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    get_existing_project(project_id, current_user, db)
    db.clear_chat_messages(project_id)
    return None


@router.post("/stream")
def stream_chat(
    project_id: str,
    payload: ChatRequest,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """SSE 流式问答端点。"""
    project = db.get_project_for_user(project_id, current_user["id"])
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
        try:
            async for chunk in chat_stream(settings, project, question_text, file_paths=file_paths):
                data = parse_sse_data(chunk, "token")
                if data is not None:
                    assistant_text += data.get("text", "")
                elif chunk.startswith("event: done"):
                    if assistant_text.strip():
                        db.add_chat_message(project_id, "assistant", assistant_text.strip())
                yield chunk
        except Exception as exc:
            error_type, message, original = classify_error(exc)
            data = json.dumps(
                {"message": message, "error_type": error_type},
                ensure_ascii=False,
            )
            yield f"event: failed\ndata: {data}\n\n"
            yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        _stream_and_save(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
