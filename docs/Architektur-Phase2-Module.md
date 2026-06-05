# Architektur — BauPilot Phase-2-Module

> Interne Code-Doku (Nacht-Lauf 06.06.2026, reine Lesung). Keine realen FLI-Daten, keine Secret-Werte.
> Module: Vorgangs-Workflows (Nachträge, Behinderungen, Bedenken, Mängel), Verknüpfungsanalyse, Störungsdaten-Extraktor, Benachrichtigungen, Tags, Dokumente.
> Stack: FastAPI (sync), SQLAlchemy `text()`-SQL (kein ORM), PostgreSQL Schema-per-Tenant (`tenant_tlbv`), MinIO, lokale LLMs via LiteLLM→Ollama.

## 0. Übergreifende Muster
- **Service-Pattern:** Router dünn, Logik in `service.py` (Dependency-Injection `_get_service(db, user)`); eigene Exception-Klasse `XxxError(status_code)`.
- **DB:** ausschließlich `text()`-SQL, sync; `search_path` aus `mandant_slug` (Tenant-Isolation); Audit-Felder `erstellt_am/von`, `geaendert_am/von`, Soft-Delete `geloescht`.
- **Rollencheck:** `SELECT rolle FROM shared.benutzer_projekt_rollen` (Leitungsschritte/Entscheidungen erfordern `projektleiter`/`admin`).
- **Middleware:** jedes Modul-Präfix in `TENANT_EXEMPT_PREFIXES` (sonst HTTP 400 vor dem Router); Identität real über Token-`mandant_slug`.
- **B-002-Gate (KI-Mensch-Trennung):** KI-Ergebnisse werden als Vorschlag gespeichert (`ki_*` bzw. `beziehungstyp='llm_vorschlag'`), erst nach menschlicher Bestätigung wirksam.

---

## 1. Vorgangs-Workflows: Nachträge / Behinderungen / Bedenken / Mängel
Gemeinsames Muster: ein `vorgaenge`-Datensatz (typ-spezifisch) + eine **Prüfschritt-Tabelle** mit sequenziell erzwungenem Schritt-Workflow; bestimmte „Leitungsschritte" nur für PL/Admin; Status wird von Schritten getriggert. Dreiklang **Q/Z/K** (Qualität / Zeit-Arbeitstage / Kosten-EUR).

| Modul | Typ | Schritte | Leitungsschritte | Prüfschritt-Tabelle |
|---|---|---|---|---|
| Nachträge (AP 2.1) | `nachtrag` | 7 | 5–7 | `nachtragspruefung` |
| Behinderungen (AP 2.2a) | `behinderungsanzeige` | 6 | 3, 6 | `behinderungspruefung` |
| Bedenken (AP 2.2b) | `bedenkenanzeige` | 6 | 3, 6 | `bedenkenpruefung` |
| Mängel (AP 2.2c) | `mangelanzeige` | 5 | 2, 5 | `mangelpruefung` |

**Endpunkte (Auszug):**
- Alle: `GET /` (Liste, Filter), `GET /{id}` (Detail + Prüfschritte), `POST /{id}/schritt/{nr}` (Schritt abschließen). BehA/BED/MA zusätzlich `GET /statistik`; BED/MA/NT `PATCH /{id}`.
- **Nachträge** zusätzlich (AP 2.1/2.5): `POST /{id}/lv-abgleich` (Schritt 2, KI), `POST /{id}/kostenabgleich` (Schritt 3, LV-/BKI-Preise), `POST /{id}/entscheidungsvorlage` (Schritt 4, LLM), `POST /{id}/ki-bestaetigung/{nr}` (B-002-Gate), `POST /{id}/entscheidung` (Variante A/B/C, PL/Admin), `POST /vorlagen/{id}/freigeben`, `GET /{id}/vorlagen`, `GET /{id}/protokoll` (Word-DocX, AP 2.5).

**Datenfluss Nachträge (KI-Stufen):**
- `nachtraege/lv_abgleich.py` → LV-Positionen-Suche (Text + Qdrant-Semantik), Doppelbeauftragungs-Prüfung (NT-F-02).
- `nachtraege/kostenabgleich.py` → Vergleich gegen LV-Einheitspreise + BKI-Baupreise (Regionalfaktor Jena).
- `nachtraege/entscheidungsvorlage.py` → **LiteLLM → Ollama → Qwen 2.5 32B** (httpx, interner Docker-Endpunkt), G1-sachlich; Ergebnis als Vorschlag (B-002).
- `nachtraege/protokoll*` → Word-Protokoll (in-Memory-Buffer, Streaming-Response).

**Schreibziele:** `vorgaenge` (Betrag-Dreiklang `betrag_gefordert/geprueft/genehmigt`, `zeitauswirkung_tage`/`zeit_arbeitstage`, Qualität, Variante/Status), jeweilige `*pruefung` (`ki_eingabe/ki_ergebnis/ki_konfidenz/ki_bestaetigt[_von/_am]`). Variante A legt optional NTV-Vorgang an.

---

## 2. Verknüpfungsanalyse (E12, B-002) — `api/verknuepfungen`
**Zweck:** Kausalketten BK→BA→NT; Vorschläge deterministisch + LLM, Freigabe per B-002-Gate.

**Endpunkte:** `GET /{vorgang_id}/vorschlaege`; `POST /{vorgang_id}/analysieren` (deterministisch + optional LLM, speichert `llm_vorschlag`); `POST /{vorgang_id}/bestaetigen` (→ `beziehungstyp='ursache'`, `konfidenz_bestaetigt=TRUE`); `POST /{vorgang_id}/ablehnen` (Verknüpfung lösen).

**Scoring (deterministisch):** Gewichte `LV 0.4`, `Bauteil 0.2 (+Gewerk 0.2)`, `Zeitnähe 0.2` (linear bis 90 Tage), Schwelle `0.3`, max. 5 Vorschläge. **LLM-Schritt:** Top-20 andere Vorgänge → Qwen bewertet semantische Ähnlichkeit (JSON `[{nr,score,grund}]`), Merge mit deterministischem Score (`+ llm*0.5`, Cap 1.0).

**Datenfluss:** liest/schreibt `tenant_tlbv.vorgaenge` (`vorgaenger_id`, `beziehungstyp`, `konfidenz`, `konfidenz_bestaetigt[_von/_am]`); LLM via `http://baupilot-litellm:4000/v1/chat/completions` (Modell `qwen-32b`). **Kein MinIO.**

---

## 3. Störungsdaten-Extraktor (E13, AP 2.6 Stufe 1) — `api/extraktion`
**Zweck:** Strukturierte Feld-Extraktion aus Störungs-PDFs via LLM; Audit-Trail in Prüfschritt 1, optionale Übernahme ins Vorgangs-Feld. **Nur Code dokumentiert — keine PDF-/FLI-Inhalte gelesen.**

**Endpunkte:** `POST /{vorgang_id}/vorschlag` (PDF→Text→LLM→`ki_ergebnis` in Prüfschritt 1); `POST /{vorgang_id}/uebernehmen` (liest `ki_ergebnis`, schreibt COALESCE-geschützt in `vorgaenge`).

**Pipeline (Code-Ebene):**
1. PDF lokalisieren: `dokumente` JOIN `vorgang_dokumente` (erstes verknüpftes PDF) → `minio_bucket/minio_pfad`.
2. **MinIO-Download:** `Minio({minio_host}:{minio_api_port}, …).get_object(...)` (lokal `baupilot-minio:9000`); Text via `pdfplumber`.
3. **LLM:** `http://{litellm_host}:{litellm_port}/v1/chat/completions` (Modell `qwen-32b`, temp 0.1, max_tokens 800, Input gekappt ~8000 Zeichen); System-Prompt fordert striktes JSON (12 Felder, null-safe, keine Halluzination).
4. **Speichern (Audit/G2):** `*pruefung` Schritt 1 `ki_eingabe`/`ki_ergebnis`/`ki_konfidenz`, `ki_bestaetigt=NULL`.
5. **Übernahme:** `UPDATE vorgaenge SET feld = COALESCE(feld, :wert)` (typ-spezifisches Mapping NT vs. BA/BK/BM); `ki_bestaetigt=TRUE`.

> Hinweis Betriebs-Abhängigkeit: Die headless-Skripte (`extraktion-nachtlauf.ps1` etc.) loggen sich als `admin@baupilot.de` ein (TOTP-Bypass). **Nicht** Teil der Laufzeit-API; hier nur erwähnt, nicht ausgeführt.

---

## 4. Benachrichtigungen (E10, B-012) — `api/benachrichtigungen`
**Zweck:** In-App-Benachrichtigungen (Air-Gap, kein SMTP). Andere Module rufen `BenachrichtigungsService.erstelle()` (best-effort, wirft nicht).

**Endpunkte:** `GET /` (Liste, optional nur ungelesen), `GET /ungelesen-anzahl` (Badge-Polling), `POST /{id}/gelesen`, `POST /alle-gelesen`.

**Datenfluss:** `tenant_tlbv.benachrichtigungen` (R/W), `benachrichtigungs_regeln` (mandantenspezifische Trigger: Name, Intervall, Empfänger-Rolle, aktiv). Enums (Migration 008): `benachrichtigungstyp` (6 Werte), `benachrichtigungs_prioritaet` (info/hinweis/warnung). Index `(benutzer_id, gelesen, erstellt_am DESC)`. **Keine** externen Aufrufe.

---

## 5. Tags / Dokumentenstruktur (E11, B-013) — `api/tags`
**Zweck:** Tag-Baum zur Klassifikation; m:n-Zuordnung zu Dokumenten.

**Endpunkte:** `GET /tags` (flach, mit `parent_id` für Frontend-Baum); `POST /dokumente/{id}/tags` (idempotent, ON CONFLICT DO NOTHING); `DELETE /dokumente/{id}/tags/{tag_id}`; `GET /dokumente/{id}/tags`.

**Datenfluss:** `tags` (`parent_id` self-reference, `ist_kategorie_wurzel`), `dokument_tags` (m:n, ON DELETE RESTRICT), `dokumente` (Existenz-Check). Seed (Migration 008): 3 Wurzeln (Bauphase/Bauteil/Dokumenttyp) + Kinder. **Keine** externen Aufrufe.

---

## 6. Dokumentenverwaltung — `api/dokumente` (+ `storage/minio_service.py`)
**Zweck:** Upload/Download/Versionierung/Klassifikation/Vorgangs-Verknüpfung mit MinIO-Objektspeicher.

**Endpunkte (11):** `GET /`, `GET /statistik`, `GET /{id}`, `GET /{id}/versionen`, `POST /upload`, `POST /{id}/version`, `GET /{id}/download`, `POST /{id}/verknuepfen`, `GET /vorgang/{vorgang_id}`, `PATCH /{id}`, `DELETE /{id}` (Soft-Delete).

**Datenfluss / MinIO:**
- DB: `dokumente` (R/W), `vorgang_dokumente` (m:n, `verknuepfungstyp` Default `anlage`), `projekte` (Lookup).
- MinIO via `storage/minio_service.py`: Client aus `MINIO_HOST:MINIO_API_PORT` (lokal `baupilot-minio:9000`); **Bucket** `baupilot-{mandant_slug}`; **Objekt-Pfad** `{projekt}/{dokument_id}/{version}/{dateiname}`; MIME-Allowlist + blockierte Endungen (`.exe/.bat/.ps1` …); Größenlimit `BAUPILOT_MAX_UPLOAD_MB`.
- **Versionierung:** `version_nummer`, `vorgaenger_version_id`. **Klassifikation:** Enums `dokumentkategorie`, `signaturstatus`, `klassifikation` (Default `intern`). Signierte Dokumente sind gegen Überschreiben/Löschen gesperrt. SHA-256-Duplikat-Hinweis beim Upload.

---

## 7. Netzwerk-/Datenfluss-Inventur (modulübergreifend) — G2-Bestätigung
| Aufrufer (Datei) | Ziel | Zweck |
|---|---|---|
| `chat/service.py` | `baupilot-litellm:4000` → Ollama `host.docker.internal:11434` | Chat Tool-Use + Antwort |
| `verknuepfungen/service.py` | `baupilot-litellm:4000` (qwen-32b) | semantisches Matching |
| `extraktion/service.py` | `baupilot-minio:9000` + `baupilot-litellm:4000` (qwen-32b) | PDF-Download + Feld-Extraktion |
| `nachtraege/entscheidungsvorlage.py` | `baupilot-litellm:4000` (qwen-32b) | Entscheidungsvorlage |
| `nachtraege/lv_abgleich.py` | Qdrant (lokal, `baupilot-qdrant:6333`) | semantische LV-Suche |
| `dokumente/service.py` (+ `storage/minio_service.py`) | `baupilot-minio:9000` | Upload/Download |
| `lv_extraktion/docling_client.py` | `spark-docling` (lokaler Container) | PDF→strukturiert (LV-Extraktion) |
| alle Module | `baupilot-postgres:5432` (Schema `tenant_tlbv`) | DB |

**Ergebnis:** Es gibt **keinen** externen/Cloud-Endpunkt im Laufzeit-Code. Sämtliche KI-/Speicher-/DB-Aufrufe bleiben auf lokalen Docker-Diensten bzw. dem Host-Ollama → **G2 (digitale Souveränität)** erfüllt. (`config.py` enthält Dev-Default-Platzhalter für Hosts/Credentials, die im Container per Env überschrieben werden — keine echten Secrets im Code reproduziert.)

*Nacht-Lauf 06.06.2026 — reine Code-Lesung; Modul-Mapping teils via read-only Explore-Agenten erstellt; keine Änderung am Code, keine realen Daten.*
