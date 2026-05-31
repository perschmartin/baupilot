"""Chatbot-Router — POST /api/v1/chat/send mit SSE-Streaming."""
from __future__ import annotations

import json
import logging
import time

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth.dependencies import CurrentUser, get_current_user
from chat.service import stream_chat
from database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


class ChatMessage(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    history: list[dict] = Field(default_factory=list)
    kontext: str | None = Field(default=None, max_length=500)


@router.post("/send")
def chat_send(
    body: ChatMessage,
    user: CurrentUser,
    db: Session = Depends(get_db),
):
    """Sendet eine Nachricht. SSE-Stream mit Antwort + Tool-Meta-Events.

    Audit (G3): Frage + User wird via standard request_logging-Middleware
    erfasst. Tool-Calls werden im Server-Log gefuehrt.
    """
    logger.info("Chat-Frage von %s: %r", user.get("email", "?"), body.message[:100])
    t_start = time.time()

    def gen():
        antwort_acc = []
        tool_calls_acc = []
        fehler_acc = None
        try:
            for evt in stream_chat(
                db=db,
                user_message=body.message.strip(),
                history=body.history or [],
                kontext=body.kontext,
            ):
                # SSE-Event durchreichen und parallel fuer Audit-Log mitschneiden
                yield evt
                if not evt.startswith("data: "):
                    continue
                payload = evt[6:].strip()
                if payload == "[DONE]" or not payload:
                    continue
                try:
                    data = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if data.get("type") == "token":
                    antwort_acc.append(data.get("content", ""))
                elif data.get("type") == "meta" and data.get("tool_calls"):
                    tool_calls_acc.extend(data["tool_calls"])
                elif data.get("type") == "error":
                    fehler_acc = data.get("content")
        finally:
            # G3 Audit-Log — best effort, kein Crash bei DB-Fehler
            try:
                db.execute(
                    text("""
                        INSERT INTO shared.chat_log
                          (benutzer_id, benutzer_email, mandant_slug, frage, antwort, tool_calls, fehler, dauer_ms)
                        VALUES
                          (:uid, :email, :mandant, :frage, :antwort, CAST(:tools AS jsonb), :fehler, :dauer_ms)
                    """),
                    {
                        "uid": user.get("sub"),
                        "email": user.get("email"),
                        "mandant": user.get("mandant_slug"),
                        "frage": body.message[:4000],
                        "antwort": "".join(antwort_acc)[:50000] or None,
                        "tools": json.dumps(tool_calls_acc, ensure_ascii=False),
                        "fehler": fehler_acc,
                        "dauer_ms": int((time.time() - t_start) * 1000),
                    },
                )
                db.commit()
            except Exception as e:
                logger.warning("chat_log-Insert fehlgeschlagen: %s", e)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
