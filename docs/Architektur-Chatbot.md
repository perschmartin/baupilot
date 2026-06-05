# Architektur — BauPilot-Chatbot (Chat-Modul, E16/E18 + Welle 2)

> Interne Code-Doku (Nacht-Lauf 06.06.2026, reine Lesung). Keine realen FLI-Daten.
> Quellen: `api/chat/{router,service,tools,prompts,__init__}.py`, `api/main.py`, `api/middleware/__init__.py`, `litellm-config.yaml`.

## 1. Überblick / Architektur
Der Chatbot beantwortet Fragen zu Projektdaten per **Tool-Use (nicht RAG)**: Ein lokales LLM entscheidet, welches von 5 vordefinierten **read-only DB-Werkzeugen** aufgerufen wird, und formuliert aus deren Ergebnissen die Antwort. Streaming an das Frontend via **SSE**.

```
Browser (ChatWidget)
  │  POST /api/v1/chat/send  (Bearer-Token)
  ▼
FastAPI Router (chat/router.py)  ── Auth: CurrentUser (get_current_user)
  │  ruft stream_chat(db, message, history, kontext)
  ▼
ChatService (chat/service.py)  ── Generator, yield SSE-Events
  ├─ Systemprompt (prompts.py) + History[-6:] + Frage
  ├─ Tool-Decision-Call ──httpx──► LiteLLM (baupilot-litellm:4000) ──► Ollama (host.docker.internal:11434)
  ├─ Tool-Ausführung (tools.py) ──SQL──► PostgreSQL (baupilot-postgres, Schema tenant_tlbv)
  └─ Finale Antwort (Streaming-Call) ──httpx──► LiteLLM ──► Ollama
  ▼
SSE-Stream zurück  (status / meta / token / error / [DONE])
  + Audit: INSERT shared.chat_log
```

**Bewusst NICHT genutzt:** Qdrant/Vektor-RAG, MinIO-Dokumente, Embeddings. Der Chat liest **ausschließlich** strukturierte DB-Daten über die 5 Tools.

## 2. Endpunkt
| Methode | Pfad | Auth | Body | Antwort |
|---|---|---|---|---|
| POST | `/api/v1/chat/send` | `CurrentUser` (Normal-Token) | `ChatMessage{message, history[], kontext?}` | `StreamingResponse` `text/event-stream` |

- Header: `Cache-Control: no-cache`, `Connection: keep-alive`, `X-Accel-Buffering: no` (router.py).
- Audit (G2): nach Stream-Ende `INSERT shared.chat_log (benutzer_id, email, mandant_slug, frage, antwort, tool_calls, fehler, dauer_ms)` — best-effort (kein Crash bei DB-Fehler).
- `/api/v1/chat` ist in `TENANT_EXEMPT_PREFIXES` (nur Tenant-Header-Befreiung, Auth bleibt).

## 3. Ablauf in `stream_chat` (service.py)
1. Systemprompt bauen (`systemprompt_bauen(kontext)`), `messages = [system] + history[-6:] + user`.
2. SSE `status: "Analysiere deine Frage …"`.
3. **Tool-Loop** `range(MAX_TOOL_ITERATIONEN+1)`, `MAX_TOOL_ITERATIONEN = 1` (1 Tool-Runde + 1 erzwungene Antwort):
   - Non-streaming POST an LiteLLM; in der Nicht-letzten Iteration mit `tools=TOOL_DEFINITIONS`, `tool_choice=auto`.
   - **Fall A — Tool-Calls:** Phantom-Guard (nur Namen in `GUELTIGE_TOOLS`; sind alle unbekannt → direkt finale Antwort), SSE `meta.tool_calls`, jedes Tool via `tool_aufrufen(db, …)`, Ergebnisse als `tool`-Messages anhängen, SSE `meta.tool_results` + `status`, `continue`.
   - **Fall B — Text:** vorhandenen `content` in Chunks als `token` streamen; sonst separater Streaming-Call (`_finale_antwort_streamen`).
4. Robustheit: `httpx.TimeoutException` → `error` „Zeitüberschreitung…"; sonstige Exceptions → `error` „LLM-Fehler…". Jeder Pfad endet mit `data: [DONE]`.

**SSE-Event-Typen:** `status` (Fortschritt), `meta` (tool_calls / tool_results), `token` (Antwort-Chunk), `error`, sowie das Sentinel `data: [DONE]`.

## 4. Werkzeuge (`tools.py`) — alle read-only, Schema `tenant_tlbv`
`search_path` wird je Aufruf hart auf `tenant_tlbv` gesetzt (`_set_tenant_search_path`). Ausschließlich `SELECT`.

| Tool | Zweck | DB-Quelle (Tabellen) |
|---|---|---|
| `vorgaenge_filtern` | Vorgänge listen/filtern (Typ, Verursacher, Bauteil, LV, Volltext) | `vorgaenge` + JOIN `firmen`, `bauteile`, `leistungsverzeichnisse` |
| `vorgang_details` | Details zu einer Nummer (+ Anzahl verknüpfter Dokumente) | `vorgaenge` + JOINs + COUNT auf `vorgang_dokumente`/`dokumente` |
| `kennzahlen` | Aggregate (Anzahl, Σ Tage, Σ EUR), optional gruppiert | `vorgaenge` (+ `firmen`/`bauteile`/`leistungsverzeichnisse`) |
| `lv_suche` | Leistungsverzeichnisse suchen | `leistungsverzeichnisse` + COUNT `vorgaenge` |
| `verursacher_top` | Top-Verursacher nach Anzahl/Tage/EUR | `vorgaenge` JOIN `firmen` |

- Dispatcher `tool_aufrufen` fängt Fehler ab → `{"fehler": …}`. `GUELTIGE_TOOLS = frozenset(TOOL_FUNCS)` (Phantom-Guard-Whitelist).
- `_kurz()` kürzt `gegenstand`-Freitext (CPU-Latenz-Optimierung Welle 2).
- **Klassifikation:** Tools filtern **nicht** nach `klassifikation` (TODO B-006 / F-209 offen — siehe `docs/AP-2_9-Bestaetigungen.md`).

## 5. Leitplanken (`prompts.py`)
Systemprompt = `IDENTITAET + ABSOLUT_VERBOTEN + PLATTFORM + TOOL_ANWEISUNG` (+ optionaler Kontext).
- **G1 (datengebunden, keine Halluzination):** „Niemals Informationen erfinden"; „Nur sachliche Wiedergabe von Fakten aus der Datenbank"; „Antworte ausschließlich auf Basis der Werkzeug-Ergebnisse"; keine Schuldzuweisungen (Attribution „laut KI-Extraktion").
- **G7 (digitale Souveränität / keine Interna):** „Niemals Programmcode, SQL, DB-Schema, Architektur"; „Niemals Datei-Pfade, Container-Namen, API-Keys, Passwörter, Konfigurationsdetails"; „Keine externen Verweise/Web-Links — arbeitet ausschließlich mit Daten dieses Systems".

## 6. Netzwerk / LLM-Konfiguration
- Einziger ausgehender Code-Aufruf des Chat-Moduls: `http://baupilot-litellm:4000/v1/chat/completions` (service.py, 2 Stellen: Tool-Decision + finaler Stream). Modell-Name aus `BP_CHAT_MODEL` (Default `default`).
- LiteLLM (`litellm-config.yaml`) leitet **nur** an Ollama `http://host.docker.internal:11434` (Modelle `default`=qwen2.5:14b, `qwen-32b`, `llama3`, `embedding`); `telemetry: false`, `master_key: null`, `request_timeout: 120`, `extra_body.keep_alive:-1`, `num_ctx:8192`.
- **G2:** kein externer/Cloud-Endpunkt.

## 7. Bekannte Eigenheiten / offene Punkte
- Latenz CPU-gebunden (Tool-Schema-Prompt-Eval); auf GPU (iGPU) deutlich schneller — siehe Welle-2-Bench-Doku.
- `MAX_TOOL_ITERATIONEN=1` kürzt echte 2-Tool-Drilldowns auf 1 Werkzeug (Antwort dünner, nicht falsch).
- VS-NfD-Filterung (Klassifikation) offen (B-006/F-209) — Tools liefern derzeit alle Vorgänge als wäre `intern`.

*Nacht-Lauf 06.06.2026 — reine Code-Lesung, keine Änderung am Code, keine realen Daten.*
