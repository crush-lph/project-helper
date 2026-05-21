"""SSE (Server-Sent Events) 格式化工具。"""

from __future__ import annotations

import json
from typing import Any


def sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def parse_sse_data(chunk: str, event: str = "token") -> dict[str, Any] | None:
    """Parse the JSON data from an SSE chunk. Returns None if not matching."""
    prefix = f"event: {event}\ndata: "
    if not chunk.startswith(prefix):
        return None
    try:
        return json.loads(chunk[len(prefix):].strip())
    except (json.JSONDecodeError, ValueError):
        return None
