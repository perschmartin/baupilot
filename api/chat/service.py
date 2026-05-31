"""ChatService — orchestriert LiteLLM-Tool-Use + SSE-Streaming.

Ablauf pro User-Nachricht:
  1. System-Prompt + History + neue Frage als 'messages' aufbauen
  2. Non-streaming LiteLLM-Call mit tools=TOOL_DEFINITIONS
  3. Wenn LLM tool_calls liefert: alle Tools ausfuehren, Ergebnisse als
     'tool'-messages anhaengen, naechste Iteration (max 3 Iterationen)
  4. Wenn LLM textuelle Antwort liefert: streamt diese als 'token'-Events
     an den Frontend-SSE-Stream

Format der SSE-Events (analog ENA-CERT):
  data: {"type":"meta","tool_calls":[...]}        -> Tool wird gleich gerufen
  data: {"type":"meta","tool_results":[...]}      -> Tool-Ergebnis kurz
  data: {"type":"token","content":"..."}          -> Antwort-Token
  data: {"type":"error","content":"..."}          -> Fehler
  data: [DONE]                                    -> Stream-Ende
"""
from __future__ import annotations

import json
import logging
import os
from typing import Generator, Iterator

import httpx
from sqlalchemy.orm import Session

from chat.prompts import systemprompt_bauen
from chat.tools import TOOL_DEFINITIONS, tool_aufrufen

logger = logging.getLogger(__name__)

LITELLM_URL = (
    f"http://{os.environ.get('LITELLM_HOST', 'baupilot-litellm')}:"
    f"{os.environ.get('LITELLM_PORT', '4000')}/v1/chat/completions"
)
MODEL_NAME = os.environ.get("BP_CHAT_MODEL", "qwen-32b")
MAX_TOOL_ITERATIONEN = 3
TIMEOUT_SEC = 120


def _sse(typ: str, **kwargs) -> str:
    """Formatiert ein dict als SSE-data-Zeile."""
    payload = {"type": typ, **kwargs}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def stream_chat(
    db: Session,
    user_message: str,
    history: list[dict],
    kontext: str | None,
) -> Generator[str, None, None]:
    """Erzeugt einen SSE-Stream mit der Chatbot-Antwort.

    db        - SQLAlchemy-Session fuer Tool-DB-Zugriffe (sync)
    user_message - aktuelle Frage des Anwenders
    history   - bisheriger Gespraechs-Verlauf (Liste von {role, content})
    kontext   - optionaler Frontend-Kontext-String (z.B. ausgewaehlter Vorgang)
    """
    sysprompt = systemprompt_bauen(kontext)
    messages: list[dict] = [{"role": "system", "content": sysprompt}]

    # Letzte 8 Nachrichten als History (begrenzt um Token-Budget)
    for m in (history or [])[-8:]:
        role = m.get("role")
        content = m.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})

    # Tool-Loop: bis zu MAX_TOOL_ITERATIONEN
    for iteration in range(MAX_TOOL_ITERATIONEN + 1):
        is_last = iteration == MAX_TOOL_ITERATIONEN

        # In der letzten Iteration zwingen wir das LLM zur textuellen Antwort.
        payload: dict = {
            "model": MODEL_NAME,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 1024,
        }
        if not is_last:
            payload["tools"] = TOOL_DEFINITIONS
            payload["tool_choice"] = "auto"

        # === Tool-Decision-Phase: non-streaming Call ===
        try:
            with httpx.Client(timeout=TIMEOUT_SEC) as client:
                r = client.post(LITELLM_URL, json=payload)
                r.raise_for_status()
                data = r.json()
        except httpx.TimeoutException:
            yield _sse("error", content="Zeitüberschreitung beim LLM-Aufruf.")
            yield "data: [DONE]\n\n"
            return
        except Exception as e:
            logger.exception("LiteLLM-Aufruf-Fehler")
            yield _sse("error", content=f"LLM-Fehler: {str(e)[:200]}")
            yield "data: [DONE]\n\n"
            return

        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        tool_calls = msg.get("tool_calls") or []
        content = msg.get("content") or ""

        # Fall A: LLM will Werkzeuge aufrufen
        if tool_calls and not is_last:
            # Frontend ueber geplante Tool-Calls informieren
            yield _sse(
                "meta",
                tool_calls=[
                    {"name": tc.get("function", {}).get("name"), "args": tc.get("function", {}).get("arguments", "")}
                    for tc in tool_calls
                ],
            )

            # Assistant-Message mit tool_calls in History haengen (Pflicht fuer OpenAI-Format)
            messages.append(
                {
                    "role": "assistant",
                    "content": content or None,
                    "tool_calls": tool_calls,
                }
            )

            # Jeden Tool-Call ausfuehren
            tool_results_compact: list[dict] = []
            for tc in tool_calls:
                tc_id = tc.get("id")
                fn = tc.get("function") or {}
                name = fn.get("name", "")
                raw_args = fn.get("arguments", "{}")
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                except json.JSONDecodeError:
                    args = {}

                ergebnis = tool_aufrufen(db, name, args)
                ergebnis_str = json.dumps(ergebnis, ensure_ascii=False)

                # Frontend ueber Ergebnis informieren (kompakt)
                summary = _kompakt_summary(name, ergebnis)
                tool_results_compact.append({"name": name, "summary": summary})

                # Tool-Result als 'tool'-Message in History
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "name": name,
                        "content": ergebnis_str,
                    }
                )

            yield _sse("meta", tool_results=tool_results_compact)
            # Naechste Iteration: LLM bekommt Tool-Ergebnisse, generiert Antwort
            continue

        # Fall B: LLM liefert Text-Antwort. Wir koennen das Ergebnis vom
        # Tool-Call schon haben, ABER wenn vor der finalen Antwort Tools
        # ausgefuehrt wurden, liefert die finale Antwort meist einen
        # vollstaendigen content. Echtes Token-Streaming machen wir
        # idealerweise nur in der letzten Iteration. Wenn 'content' schon
        # vorhanden ist, streamen wir das in Chunks. Sonst: separater
        # Streaming-Call (passiert in der naechsten Iteration mit is_last).
        if content:
            for chunk in _chunks(content, n=8):
                yield _sse("token", content=chunk)
            yield "data: [DONE]\n\n"
            return

        # Kein Content + keine Tool-Calls: separater Streaming-Call zwingt finale Antwort
        try:
            payload_stream = {
                "model": MODEL_NAME,
                "messages": messages,
                "temperature": 0.2,
                "max_tokens": 1024,
                "stream": True,
            }
            with httpx.Client(timeout=TIMEOUT_SEC) as client:
                with client.stream("POST", LITELLM_URL, json=payload_stream) as r:
                    r.raise_for_status()
                    for line in r.iter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        chunk_raw = line[6:].strip()
                        if chunk_raw == "[DONE]":
                            break
                        try:
                            chunk = json.loads(chunk_raw)
                        except json.JSONDecodeError:
                            continue
                        delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
                        tok = delta.get("content")
                        if tok:
                            yield _sse("token", content=tok)
        except Exception as e:
            logger.exception("LiteLLM-Stream-Fehler")
            yield _sse("error", content=f"Stream-Fehler: {str(e)[:200]}")
        yield "data: [DONE]\n\n"
        return

    # Sollte nicht erreicht werden — Sicherheits-Fallback
    yield _sse("error", content="Maximale Werkzeug-Iterationen erreicht.")
    yield "data: [DONE]\n\n"


# -------- Hilfsfunktionen -------------------------------------------------


def _chunks(text: str, n: int = 12) -> Iterator[str]:
    """Schneidet einen String in n-Zeichen-Haeppchen fuer Pseudo-Streaming."""
    for i in range(0, len(text), n):
        yield text[i : i + n]


def _kompakt_summary(tool: str, result: dict) -> str:
    """Kurze textuelle Zusammenfassung eines Tool-Ergebnisses fuer das Frontend."""
    if "fehler" in result:
        return f"Fehler: {result['fehler']}"
    if tool == "vorgaenge_filtern":
        return f"{result.get('treffer', 0)} Vorgänge gefunden"
    if tool == "vorgang_details":
        return f"Details zu {result.get('nummer', '?')}"
    if tool == "kennzahlen":
        n = len(result.get("zeilen", []))
        return f"{n} Gruppen aggregiert ({result.get('gruppe', '')})"
    if tool == "lv_suche":
        return f"{result.get('treffer', 0)} LVs gefunden"
    if tool == "verursacher_top":
        n = len(result.get("verursacher", []))
        return f"Top-{n} nach {result.get('metrik', '')}"
    return "fertig"
