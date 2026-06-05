# AP 2.9 — Bestätigungen (Chatbot-Spezifikation)

> Read-only-Inventur (Nacht-Lauf 06.06.2026). Keine Code-Änderung, keine realen FLI-Daten.
> Quellen: `api/chat/{router,service,tools,prompts}.py`, `api/main.py`, `api/middleware/__init__.py`, `api/auth/dependencies.py`, `alembic/sql/001_initial_schema.sql`.

## (1) Auth: liegt `/api/v1/chat` hinter `get_current_user` mit Normal-Token (kein anonymer Zugriff)?

**JA.**

- `api/chat/router.py`: `@router.post("/send")` hat den Parameter `user: CurrentUser`. `CurrentUser = Annotated[dict, Depends(get_current_user)]` (auth/dependencies.py:154). Router-Prefix `/api/v1/chat` → Endpunkt `POST /api/v1/chat/send`.
- `get_current_user` (auth/dependencies.py:52–78): ohne gültigen Bearer-Token → **401**; Token mit `totp_setup_required` → **403**; mit `totp_pending` → **401**. Es passiert also **nur** ein vollwertiges Normal-Token. Kein anonymer / eingeschränkter Zugriff.
- `api/main.py:130`: `app.include_router(chat_router)` — **ohne** entkräftende `dependencies=[]`-Override.
- Hinweis: `/api/v1/chat` steht in `TENANT_EXEMPT_PREFIXES` (middleware/__init__.py:36). Das betrifft **ausschließlich** den `X-Tenant-Slug`-Header-Zwang der `TenantMiddleware`, **nicht** die Authentifizierung. Die Mandanten-Identität stammt aus dem Token (`mandant_slug`); die DB-Tools setzen `search_path` zusätzlich hart auf `tenant_tlbv`.

## (2) SSE: gibt es ein eindeutiges Abschluss-/done-Event?

**JA — `data: [DONE]`.**

- `api/chat/service.py` beendet **jeden** Ausgangspfad mit `yield "data: [DONE]\n\n"`:
  - Timeout beim LLM-Aufruf (Z.104)
  - allgemeiner LLM-Fehler (Z.109)
  - Content-Antwort fertig gestreamt (Z.198)
  - Streaming-Helper `_finale_antwort_streamen` inkl. Fehlerzweig (Z.247)
  - Sicherheits-Fallback (Z.207)
- Format ist im Service-Docstring dokumentiert (Z.17): `data: [DONE]  -> Stream-Ende`.
- `api/chat/router.py` reicht die Events 1:1 als `text/event-stream` durch (Header u.a. `X-Accel-Buffering: no`).
- → Der Client hat ein eindeutiges Sentinel für das Stream-Ende; Fehler kommen zusätzlich als `data: {"type":"error",...}` davor.

## (3) Filtern die 5 Tools nach Spalte `klassifikation`?

**NEIN — keine der 5 Tool-Funktionen filtert nach `klassifikation`.** *(Nur Befund — nichts geändert. VS-NfD-Filterung ist offene Entscheidung F-209/B-006 und wird hier bewusst nicht implementiert.)*

- `api/chat/tools.py`: Die WHERE-Bedingungen aller Tools (`vorgaenge_filtern`, `vorgang_details`, `kennzahlen`, `lv_suche`, `verursacher_top`) nutzen nur `typ`, `NOT geloescht` und optionale Such-/Filter-Argumente. **Kein** Vorkommen von `klassifikation`.
- Explizit als offen markiert (tools.py:10): „Klassifikations-VS-NfD ausblenden (TODO B-006, vorerst alle)."
- Die Spalte **existiert** im Schema: `alembic/sql/001_initial_schema.sql` — `CREATE TYPE klassifikation AS ENUM (…)` (Z.31); Spalte `klassifikation NOT NULL DEFAULT 'intern'` (Z.203 und Z.347, u.a. Tabelle `dokumente`); Index auf `dokumente.klassifikation` (Z.356).
- **Konsequenz für die Spezifikation:** Der Chatbot liefert derzeit Vorgänge **unabhängig** von ihrer Klassifikation (alle als wäre `intern`). Eine VS-NfD-Ausblendung müsste in den Tool-SQLs ergänzt werden — gehört aber zur offenen Klassifikations-Entscheidung (B-006 / F-209).

## Zusammenfassung

| Frage | Antwort | Beleg |
|---|---|---|
| (1) Auth: Normal-Token, kein anonymer Zugriff | **Ja** | router.py (`CurrentUser`); dependencies.py:52–78,154; main.py:130 |
| (2) Eindeutiges SSE-Abschluss-Event | **Ja** (`data: [DONE]`) | service.py:104/109/198/207/247; Docstring Z.17 |
| (3) Tools filtern nach `klassifikation` | **Nein** (offen: B-006/F-209) | tools.py (kein Vorkommen) + Z.10; Schema 001 Z.31/203/347/356 |

*Erstellt im Nacht-Lauf 06.06.2026 — reine Inventur, keine Änderung am Code.*
