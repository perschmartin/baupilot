# Nacht-Lauf 2026-06-06 — Notizen & Ergebnis

Unbeaufsichtigter Lauf, strikt im erlaubten Rahmen (A/B read-only + Doku; C optionale vorbereitete Commits **ohne Deploy**). Kein Deploy/build/restart, keine Auth-Änderung, kein TOTP-Bypass-Umbau, keine FLI-Daten/-Skripte, kein force-push, keine VS-NfD-Filterung.

## A) Inventur — ERLEDIGT
`docs/AP-2_9-Bestaetigungen.md`:
1. `/api/v1/chat` hinter `get_current_user` (Normal-Token, kein anonym) → **Ja**.
2. SSE eindeutiges Abschluss-Event `data: [DONE]` → **Ja**.
3. Tools filtern **nicht** nach `klassifikation` (Spalte existiert, Default `intern`; offen: B-006/F-209). Nur berichtet.

## B) Code-Doku — ERLEDIGT
- `docs/Architektur-Chatbot.md` — Chat-Modul (Tool-Use statt RAG, SSE, 5 read-only DB-Tools, G1/G7-Leitplanken, Netzwerk).
- `docs/Architektur-Phase2-Module.md` — Nachträge/Behinderungen/Bedenken/Mängel, Verknüpfungsanalyse (B-002), Störungsdaten-Extraktor (E13), Benachrichtigungen (B-012), Tags (B-013), Dokumente/MinIO + übergreifende Muster.
- **Netzwerk-Inventur (G2):** alle ausgehenden Laufzeit-Aufrufe lokal/intern (LiteLLM `baupilot-litellm:4000` → Ollama `host.docker.internal:11434`, MinIO `baupilot-minio:9000`, Qdrant lokal, Docling `spark-docling`, Postgres `baupilot-postgres:5432`). **Kein externer/Cloud-Endpunkt.**

## C) Vorbereitete Fixes (ohne Deploy)

### C2 — nginx-resolver: **COMMITTET** (kein Deploy)
`frontend/nginx.conf`: `resolver 127.0.0.11 valid=10s ipv6=off;` + `set $api_upstream baupilot-api;`; `/api/` → `proxy_pass http://$api_upstream:8000$request_uri;`, `/health` analog. Erzwingt Re-Resolution pro Request → behebt den **Stale-Upstream-502** nach api-Recreate.
⚠️ **Nur vorbereitet** — wirkt erst nach Recreate des `frontend`-Containers; vorher `nginx -t` validieren. In diesem Lauf **nicht** deployt/getestet (502-Lektion: kein build/up/restart).

### C1 — qdrant-Healthcheck: **NICHT durchgeführt (STOPP)**
Der Healthcheck (`curl -sf http://localhost:6333/healthz` via `CMD-SHELL`) schlägt vermutlich fehl, weil das qdrant-Image kein `curl`/`sh` enthält → Container dauerhaft „unhealthy". Den **korrekten** Ersatz kann ich ohne Image-Inspektion nicht verlässlich angeben — und `docker exec baupilot-qdrant …` wurde (richtigerweise) als nicht-freigegebener Infra-Zugriff blockiert. Daher **nicht geraten**.
→ Empfehlung (mit Freigabe): `docker exec baupilot-qdrant sh -lc 'command -v curl wget bash'` prüfen, dann passenden Healthcheck setzen oder den fehlerhaften entfernen. **„unhealthy" ist hier kosmetisch** — qdrant läuft, kein Funktionsausfall.

### C3 — Doppel-Button im Dashboard: **NICHT durchgeführt (STOPP)**
Ohne konkrete Angabe (welcher Tab/Bereich/Button-Text) ist der duplizierte Button in der ~6000-Zeilen-`frontend/index.html` nicht eindeutig identifizierbar; blindes Entfernen wäre zu riskant.
→ Bitte **Tab + Button-Label/Position** nennen, dann gezielter Fix.

## Git
- Zwei saubere Commits: `fix(nginx): …` (nur `frontend/nginx.conf`) und `docs: …` (A/B-Docs + diese Notiz).
- Push: `git push --ff-only origin main` — **nur** bei Fast-Forward; bei Ablehnung stehen gelassen (Status in der Abschlussmeldung).
- **Untracked gelassen** (nicht committet, da nicht aus diesem Lauf): `BauPilot-Bestandsaufnahme-2026-06-05.md`, `BauPilot-Konzept-Delta-v0_4-zu-v0_5-FINAL.md`, `BauPilot-Projektanweisung-v0_5.md`, `BauPilot-Uebergabe-an-Claude-Code-2026-06-05.md`.

## Betriebshinweise
- Bis der nginx-Fix deployt ist: nach jedem `baupilot-api`-Recreate den `baupilot-frontend` **mit**-recreaten, sonst 502 am Login (Stale-Upstream).
- Chatbot braucht Host-Ollama auf GPU (`ollama ps` → 100% GPU; sonst `ollama serve`).

*Nacht-Lauf 06.06.2026 — A/B erledigt, C2 vorbereitet (kein Deploy), C1/C3 bewusst gestoppt mit Notiz.*

---

## Update 2026-06-15 (Folge-Session) — C2 DEPLOYT + gepusht

- **C2 nginx-Resolver-Fix ist live.** Befund vor Deploy: 502 war **nicht aktiv** (Login = HTTP 200). Bug war **latent**: laufendes Frontend-Image vom **03-06** < Fix-Commit vom **06-06**, aber `api`+`frontend` liefen synchron seit **09-06** → die beim nginx-Start gecachte api-IP war noch gültig. Deploy = **preventive Härtung** gegen den nächsten api-Recreate.
- **Wichtige Korrektur zum 06-06-Rezept:** Die `nginx.conf` ist via `COPY` **ins Image gebacken** (kein Volume-Mount) → ein bloßes Recreate übernimmt sie NICHT; es braucht ein **Rebuild**.
- **Durchgeführt (scoped, sicher):**
  1. `docker compose -f docker-compose.services.yaml --env-file .env build frontend`
  2. `docker run --rm spark-baupilot-frontend nginx -t` → *test is successful*
  3. `docker compose … up -d --no-deps --force-recreate frontend` (KEIN `--remove-orphans`; Orphan-Warnung zu postgres/minio/qdrant ist erwartet — die stammen aus `docker-compose.yaml`).
  - **Verifiziert:** Container frisch, `/health` + `POST /api/v1/auth/login` über Frontend-nginx (:8091) = **HTTP 200**.
- **Push:** `430a6b6` + `fe52cf0` als Fast-Forward nach `origin/main` (`ab9a507..fe52cf0`); `origin/main == main`.

*Update 2026-06-15 10:48 — C2 deployt+verifiziert, 2 Commits gepusht (M. Persch / Claude Code).*
