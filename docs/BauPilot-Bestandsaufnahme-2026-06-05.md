# BauPilot — Bestandsaufnahme 2026-06-05

> Reine Inventur (read-only). Keine Code-/Daten-Änderungen.
> **G5:** keine realen FLI-Daten — nur Code, Konfig, Migrationen, Zählungen, Commit-Messages, Dateinamen.

## 1. Alembic-Migrationen (`alembic/sql/`)

Nummerierte Migrationen (aufsteigend):

| # | Datei |
|---|---|
| 001 | `001_initial_schema.sql` |
| 002 | `002_auth_erweiterung.sql` |
| 003 | `003_einladungen.sql` |
| 004 | `004_aufgabenmanagement.sql` |
| 005 | `005_dokumentenverwaltung.sql` |
| 006 | `006_lv_extraktion.sql` |
| 007 | `007_nachtragsmanagement.sql` |
| 008 | `008_stoerungsmanagement_benachrichtigungen_tags.sql` |

Zusätzliche, nicht nummerierte Fix-Skripte:
- `fix_lv_101_102_cleanup.sql`
- `fix_lv_spaltenlaengen.sql`

**Höchste nummerierte Migration: 008** (Runner: `scripts/run-migration-008.ps1`).
**Live-DB-Version (`alembic_version`): nicht ausgelesen** — `docker exec` ist in dieser Umgebung blockiert, kein Host-DB-Client verfügbar. Datei-Stand 008 dient als Proxy.

## 2. `BAUPILOT_DEV_SKIP_TOTP` — Fundstellen + Wert

| Ort | Vorkommen | Wert |
|---|---|---|
| `.env` | — | nicht vorhanden |
| `docker-compose.services.yaml` | Zeile 33 | `"1"` (Bypass **aktiv**) |
| `docker-compose.yaml` (Infra) | — | nicht vorhanden |

→ Der TOTP-Bypass ist **aktiv** und ausschließlich in `docker-compose.services.yaml` gesetzt.

## 3. `common_passwords.txt`

- Pfad: `api/data/common_passwords.txt` (nicht `api/`)
- **10004 Zeilen**

## 4. Uncommittete Änderungen

`git diff --stat` — unstaged (staged: leer):

| Datei | ± | Grobe Änderung |
|---|---|---|
| `.claude/settings.local.json` | 2 | Nur `$schema`-URL aktualisiert (schemastore statt docs.claude.com); Allowlist inhaltlich unverändert. |
| `api/chat/prompts.py` | 9 | TOOL_ANWEISUNG geschärft (Welle 2/P4): „nutze AUSSCHLIESSLICH bereitgestellte Werkzeuge, keine erfundenen Namen/Parameter" + „höchstens EIN Werkzeug". |
| `api/chat/service.py` | 106 | Chat-Orchestrierung Welle 2: Phantom-Guard, `MAX_TOOL_ITERATIONEN` 3→1, Status-SSE-Events, erzwungene finale Antwort, History-/Timeout-Anpassung. |
| `api/chat/tools.py` | 21 | `vorgaenge_filtern`-Trim (Default-`limit` 20→8, `gegenstand` auf 100 Z. via `_kurz`) + `GUELTIGE_TOOLS`-Whitelist für den Phantom-Guard. |
| `docker-compose.services.yaml` | 1 | Eine Zeile ergänzt: `BP_CHAT_MODEL: ${BP_CHAT_MODEL:-default}` (Welle 2/P1). |
| `frontend/index.html` | 11 | ChatWidget: `status`-Feld + SSE-`status`-Event-Handler; Streaming-Fallback zeigt `m.status` statt „…" (P3). |
| `frontend/nginx.conf` | 5 | Im `/api/`-Block `proxy_buffering off; proxy_cache off;` für SSE (P3). |
| `litellm-config.yaml` | 10 | `extra_body` mit `keep_alive:-1` + `num_ctx:8192` für 14b & 32b (P0); `request_timeout:120` (P6). |

Untracked (`??`), neue Doku (nicht geöffnet):
- `docs/BauPilot-Konzept-Delta-v0_4-zu-v0_5-FINAL.md`
- `docs/BauPilot-Projektanweisung-v0_5.md`
- `docs/BauPilot-Uebergabe-an-Claude-Code-2026-06-05.md`

**Befund:** Die komplette Chatbot-**Welle 2** (P0–P6 + Iterations-Cap + Trim) ist funktional/live, aber **noch nicht committet** (8 geänderte Dateien). *(Git-Warnung beim Status: `.pytest_cache/` nicht lesbar — irrelevant, kein Tracking-Eintrag.)*

## 5. AP-/Feature-Status (Code-Module + Commits)

`api/`-Module mit Router (16): `aufgaben`, `auth`, `bedenken`, `behinderungen`, `benachrichtigungen`, `chat`, `dokumente`, `ergebnis`, `extraktion`, `kontakte`, `lv_extraktion`, `maengel`, `nachtraege`, `tags`, `verknuepfungen`, `vorgaenge`.

| AP / Feature | Titel | Status | Beleg |
|---|---|---|---|
| AP 1.1 | Auth (JWT/TOTP/Einladungen) | **fertig** | `auth/`, a36b721 |
| AP 1.2 | LV-Extraktion | **fertig** | `lv_extraktion/`, c438d37 |
| AP 1.5 | Dokumentenverwaltung (MinIO) | **fertig** | `dokumente/`, ee8b4e0 |
| AP 1.6 | MK/NTV-Import | **fertig** | 8f1c434 |
| AP 2.1 | Nachtragsmanagement (7-Schritte, NT-F-02..05) | **fertig** | `nachtraege/`, c438d37/d37a15c/cb98c4b |
| AP 2.2a | Behinderungen-Workflow | **fertig** | `behinderungen/`, 20635a3 (BE+FE+Seed) |
| AP 2.2b | Bedenken-Workflow | **fertig** | `bedenken/`, 14b705f |
| AP 2.2c | Mängel-Workflow | **fertig** | `maengel/`, 670f2a9 |
| AP 2.5 | Protokollgenerierung (Word) | **fertig** | 4dd09d4 |
| AP 2.6 | Verknüpfungsanalyse + LLM-Extraktor | **fertig** | `verknuepfungen/` (E12), `extraktion/` (E13a–f) |
| E10 | In-App-Benachrichtigungen (B-012) | **fertig** | `benachrichtigungen/`, acff8ad |
| E11 | Tag-System (B-013 Schicht 1) | **fertig** | `tags/`, aa84cdf |
| E12 | Verknüpfungsanalyse-Modul **+ Frontend** (B-002) | **fertig** | 392d43c, 178ba31, 8ebfe5f |
| E13 *(Commits)* | LLM-Daten-Extraktor aus Störungs-PDFs (AP 2.6 1. Stufe) | **fertig** | `extraktion/`, cad17a5…2b6d548 (E13a–f) |
| E14 | Sicherheitshärtung | **teilweise** | Secrets ✅ (392d43c); TOTP-Bypass-Entfernung ❌ (DryRun: 3 Bypass-Blöcke + Compose-Zeile vorhanden) |
| E18 | Chatbot Welle 1 (Tool-Use + Streaming) | **fertig** | `chat/` (Basis committet) |
| — | Chatbot Welle 2 (Zuverlässigkeit, P0–P6 + Trim) | **fertig, aber UNCOMMITTET** | siehe §4 |

⚠️ **Doppelte E-Nummerierung:** Die Commit-/CLAUDE.md-E-Nummern weichen von der Roadmap ab.
Beispiel: **Commit-„E13"** = LLM-Extraktor (oben, fertig); **Roadmap-„E13"** = „Phase 3 Termincontrolling (Asta X83)" → **fehlt/blockiert** (kein Modul, X83-Datei fehlt).

## 6. B-Nummern-Konflikt: B-012 / B-013

**B-012 — konsistent (kein Konflikt):** In-App-Benachrichtigungen / Air-Gap-Benachrichtigungssystem.
Fundstellen u. a.: `CLAUDE.md` (Modul `benachrichtigungen/`, Tabelle `benachrichtigungen`, E1/E10), `docs/BauPilot-Feedback-Analyse-und-Umsetzungsplan.md` (AD-Kandidat B-012 = Benachrichtigungssystem).

**B-013 — KONFLIKT (zwei Bedeutungen).** 14 Dateien enthalten „B-013", in zwei unvereinbaren Bedeutungen:

1. **Dokumentenstruktur / Tag-System** *(die in Code + Migration umgesetzte Bedeutung)*
   - `api/tags/` + `api/tags/__init__.py`, `alembic/sql/008_stoerungsmanagement_benachrichtigungen_tags.sql`, `scripts/run-migration-008.ps1`, `api/ergebnis/router.py`
   - `CLAUDE.md` (`tags/ ← Tag-Hierarchie (B-013)`, `dokument_tags (B-013)`), `docs/Feedback-Analyse` („B-013: Dokumentenstruktur — Ordner vs. Tags vs. Kategoriebaum")
   - Roadmap/Commit: E11 „Tag-System (B-013 Schicht 1)"

2. **Netzplan-Technologie (Vite + React Flow)** *(konkurrierende Bedeutung)*
   - `CLAUDE.md` Zeile 285 (Entscheidungstabelle: „B-013 | Netzplan-Technologie: Vite + React Flow | Votum Martin ausstehend")
   - Roadmap E17 „B-013 Vorgangsknotennetzplan"

→ Dieselbe Kennung **B-013** steht einerseits für *Dokumentenstruktur/Tags* (umgesetzt, E11 / Migration 008), andererseits für *Netzplan-Technologie* (Entscheidungstabelle / E17). Nüchterner Befund: Eine der beiden Bedeutungen sollte umnummeriert werden (hier **nicht** durchgeführt — reine Feststellung).

---
*Erstellt 2026-06-05. Reine Inventur — keine Änderungen an Code oder Daten.*

---

## Befund: e14-sicherheitshaertung.ps1 (Secret-Altlast)

*Reine Untersuchung. Datei unverändert. G7: alle Secret-Werte maskiert.*

**1. Zweck.** `scripts/e14-sicherheitshaertung.ps1` ist das E14-Komplett-Härtungsskript. Es rotiert drei Secrets und schreibt sie in `.env` (Schritt 2), setzt das PostgreSQL-Passwort in der laufenden DB via `docker exec … psql` (Schritt 3), entfernt **optional** mit `-MitTotp` den TOTP-Bypass aus `docker-compose.services.yaml` + `api/auth/service.py` (Schritt 4) und startet danach die Services neu + fährt die Tests (Schritt 5). Parameter: `-NurSecrets`, `-MitTotp`, `-DryRun`. → **Einmal-/Anlass-Skript** (Setup-Härtung), nicht für wiederkehrenden Betrieb. Da die Werte fest im Quelltext stehen, „rotiert" es jedoch immer auf **dieselben** Secrets — faktisch Fix-Werte statt echter Rotation.

**2. Hartkodierte Secrets (maskiert).**

| Zeile | Variable | Art | Wert |
|---|---|---|---|
| 24 | `$pgPw` | PostgreSQL-Passwort (→ `POSTGRES_PASSWORD`) | `"****"` |
| 25 | `$minioPw` | MinIO-Root-Passwort (→ `MINIO_ROOT_PASSWORD`) | `"****"` |
| 26 | `$apiKey` | API-Secret-Key (→ `API_SECRET_KEY`) | `"****"` |

Zeilen 28–30 geben gekürzte Anfangs-Substrings (erste 8–16 Zeichen) auf der Konsole aus — die **Voll-Werte** stehen als Literale in Zeilen 24–26.

**3. Referenzen im Repo.** Suche nach „e14-sicherheitshaertung" im gesamten Repo → **genau eine** Fundstelle:
- `scripts/e14-sicherheitshaertung.ps1:163` — Selbst-Referenz im Footer-Hinweis (`… .\scripts\e14-sicherheitshaertung.ps1 -MitTotp`).

Kein anderer Aufruf / keine Referenz im Repo (kein Skript, kein `docker-compose`, kein Makefile, kein `CLAUDE.md`/README/docs). → Das Skript wird **manuell** aufgerufen, ist nicht in Pipeline/Autostart eingebunden. *(Handover-Dokumente im Obsidian-Vault liegen außerhalb des Repos und sind hier nicht erfasst.)*

**4. Gleiche Werte in `.env`?** (nur Ja/Nein)

| Variable | identischer Wert in `.env`? |
|---|---|
| `POSTGRES_PASSWORD` | Ja |
| `MINIO_ROOT_PASSWORD` | Ja |
| `API_SECRET_KEY` | Ja |

→ Alle drei stehen identisch in der (gitignored) `.env`. Die Literale im Skript sind damit **durch `.env`-Variablen ersetzbar** — die Hartkodierung ist überflüssig und der Grund der Altlast.

**5. Git-Historie.** `git log --oneline -- scripts/e14-sicherheitshaertung.ps1`:
- `392d43c feat: E12 Verknuepfungsanalyse-Modul (B-002), E14 Secrets-Rotation, Sofort-Fixes (.gitattributes, Container-Tests, UUID)`

→ Eingecheckt in **392d43c** (einziger Commit, seither unverändert). Seit diesem Commit liegen die Klartext-Secrets in der Git-Historie.

**Bewertung & Sanierungsvorschlag (hier NICHT ausgeführt).** Echte Secrets im Klartext in einer committeten Datei → dauerhaft in der Historie. Empfehlung als eigener Schritt: (1) die drei Secrets **rotieren** (die exponierten gelten als verbrannt), (2) Literale im Skript durch `.env`-/`$env:`-Variablen ersetzen, (3) Historie bereinigen (`git filter-repo` / BFG) oder mindestens künftig vermeiden. Da `.env` bereits gitignored ist, schließt Variante (2) das Leck, ohne Funktionalität zu ändern.

---
*Ergänzt 2026-06-05 — reine Untersuchung, keine Datei außer dieser geändert.*

---

## Befund: TOTP-Bypass (E14, Entfernung)

*Reine Untersuchung. Datei unverändert. G7: keine Secret-Werte (der Bypass-Code enthält keine; `admin@baupilot.de` ist ein Konto-Identifier, kein Secret).*

### 1. Fundstellen
**Code — `api/auth/service.py`** (3 identische DEV-BYPASS-Blöcke, je 6 Zeilen):
- **Z. 122–127** in `login()`
- **Z. 186–191** in `verifiziere_totp_login()`
- **Z. 379–384** im Refresh-/Token-Rotations-Pfad

Jeder Block (Werte-frei):
```python
# --- DEV-BYPASS: TOTP ueberspringen wenn BAUPILOT_DEV_SKIP_TOTP=1 ---
import os as _os
if _os.environ.get("BAUPILOT_DEV_SKIP_TOTP") == "1" and row["email"] == "admin@baupilot.de":
    self.db.execute(text("UPDATE shared.benutzer SET fehlversuche = 0, gesperrt_bis = NULL ..."))
    self.db.commit()
    return self._login_erfolg(row, mandant_slug, ip_adresse, user_agent)
```

**Config — `docker-compose.services.yaml` Z. 32:** `BAUPILOT_DEV_SKIP_TOTP: "1"`
**Doku-Hinweis — `CLAUDE.md` Z. 315:** „TOTP-Bypass aktiv … vor Produktivbetrieb entfernen!"
**NICHT vorhanden in:** `.env`, `docker-compose.yaml` (Infra). Keine weiteren Muster (SKIP_TOTP/DEV_SKIP/totp.*skip|bypass) außer den obigen + Doku-Mentions.

### 2. Wie der Bypass wirkt
Er greift an der **Token-Ausgabe** (Login + TOTP-Verify + Refresh), **nicht** in `get_current_user`. Ist `BAUPILOT_DEV_SKIP_TOTP=="1"` **und** die E-Mail `admin@baupilot.de`, springt der Code vor den TOTP-Zweigen direkt zu `_login_erfolg(...)` → es wird sofort ein **Voll-Token** (ohne `totp_setup_required`/`totp_pending`) ausgegeben. Damit entfällt in `login()` der Setup-/Pending-Zweig, in `verifiziere_totp_login()` die eigentliche Code-Prüfung und im Refresh die TOTP-Pflicht. `get_current_user` ist unverändert und akzeptiert das Voll-Token nur deshalb, weil keine TOTP-Flags gesetzt sind → **Login/Verify/Refresh direkt, `get_current_user` nur als Folge**.

### 3. Was zum sauberen Entfernen geändert werden muss
- **Code (`api/auth/service.py`):** die **3 Blöcke** entfernen — Z. 122–127, 186–191, 379–384. Danach fällt `login()` in die normalen Zweige (totp_setup_required / totp_pending), `verifiziere_totp_login()` prüft den echten Code, Refresh verlangt TOTP.
- **Compose:** `docker-compose.services.yaml` **Z. 32** (`BAUPILOT_DEV_SKIP_TOTP: "1"`) entfernen.
- **.env / docker-compose.yaml:** nichts — die Variable steht dort nicht.
- **Doku:** `CLAUDE.md` Z. 315 aktualisieren/entfernen.
- **Deploy:** api ist ins Image gebacken → nach der Code-Änderung `build api` + recreate, damit es greift.
- **Voraussetzung (kein Lockout):** das echte Admin-Konto (`admin@tlbv.de`) muss vorher TOTP eingerichtet haben.

### 4. Nebenwirkungen
- **Tests:** keine Test-Datei referenziert den Bypass oder `admin@baupilot.de` → Repo-Tests brechen **nicht**.
- **Nur Account-Existenz (NICHT Bypass-abhängig → bleiben heil):** `api/extraktion/service.py` (Z. 280–289, SQL-Lookup als `erstellt_von`) und die `seed-*-pruefschritte.ps1` (SQL via `docker exec`) nutzen `admin@baupilot.de` nur in SQL — sie brauchen nur, dass der Account existiert (Bypass-Entfernung löscht ihn nicht).
- **⚠️ Brechen nach Entfernung — headless API-Login als `admin@baupilot.de`:** Diese **5 Skripte** melden sich per `POST /auth/login` an und verwenden `access_token`:
  - `extraktion-nachtlauf.ps1` (nächtlicher Extraktionslauf)
  - `import-fli-dokumente.ps1`, `import-fli-stoerungen.ps1` (FLI-Importe)
  - `ntv-nachverknuepfung.ps1`
  - `einladung-max-erneuern.ps1`

  Nach Bypass-Entfernung liefert der Login für `admin@baupilot.de` ein **eingeschränktes** Token (`erfordert_totp_setup`) → kein nutzbarer `access_token` → diese Automatisierungen **schlagen fehl**. Sie brauchen eine TOTP-freie Alternative (dediziertes Service-Konto/Service-Token) oder Ausführung, solange der Bypass noch aktiv ist.
- **Extern (Sandbox, nicht im Repo):** die Bench-Skripte `bench_fullpath.py`/`bench_p50.py` loggen sich ebenfalls als `admin@baupilot.de` mit Dev-Skip ein → brechen nach Entfernung (reine Test-Hilfen, unkritisch).

**Kernpunkt:** Der Bypass ist **nicht nur** menschliche Dev-Bequemlichkeit, sondern **trägt die headless-Automatisierung** (v. a. nächtlicher Extraktionslauf + FLI-Importe). Sauberes Entfernen erfordert daher zusätzlich eine Headless-Auth-Lösung für `admin@baupilot.de`, sonst stoppen diese Jobs.

---
*Ergänzt 2026-06-05 — reine Untersuchung des TOTP-Bypass, keine Datei außer dieser geändert.*
