# BauPilot — Übergabe an Claude Code

**Datum:** 05.06.2026
**Repo:** `C:\SPARK\spark-baupilot\` · GitHub perschmartin/baupilot (branch main, privat)
**Zweck dieser Datei:** Startpunkt für die Arbeit in Claude Code. Maßgebliche Quelle bleibt `BauPilot-Projektanweisung-v0.5.md` — dies ist der operative Auszug für den Agenten.

---

## 0. Harte Leitplanken (zuerst lesen, gelten immer)

1. **Keine echten FLI-Daten lesen oder ausgeben (G5).** Arbeite ausschließlich am **Quellcode**. Tabu für Lese-/Ausgabezugriff: `P:\Datenübergabe FLI`, der MinIO-Dokumentenbestand (`baupilot-tlbv`), Live-DB-Dumps und reale Datensatz-**Inhalte** (die 615 realen Vorgänge, NT-Texte, Schriftverkehr). Schemata, Migrationen, Zeilenanzahlen und Strukturen sind erlaubt — der **Inhalt** realer Vorgänge nicht. Wenn du Daten zum Testen brauchst: synthetische/abstrahierte Fixtures erzeugen, keine echten Zeilen dumpen.
2. **Keine externen KI-APIs im Laufzeit-Code (G2).** Inferenz läuft lokal über Ollama/LiteLLM. Keine externen Inferenz- oder Passwort-Prüfdienste einbauen.
3. **Code öffentlich, Geheimnisse nie (G7).** Keine Secrets, keine echten Passwörter, keine temporären Transferwege in Code, Kommentare oder Commits. `.env` und `.gitignore` respektieren.
4. **Faktische Neutralität (G1)** und **Dreiklang Q/Z/K als Pflichtfelder (G8)** gelten für jeden generierten Inhalt und jeden LLM-Prompt.
5. **Vor Architektur-/Datenmodell-/Scope-Entscheidungen: stopp.** Solche Entscheidungen laufen über den AD-Prozess in claude.ai (B-Reihe, BP-V-18), nicht spontan im Agenten.

---

## 1. Wo wir stehen

Phase 2. Phase 0 und Phase 1 vollständig deployed (Auth, Frontend, Aufgaben, Kontakte, Dokumente, Import, LV-Extraktion). AP 2.1 Nachtragsmanagement deployed und live getestet (7-Schritte-Workflow, LV-Abgleich, BKI-Kostenabgleich, lokale Entscheidungsvorlage über Qwen 2.5 32B). AP 2.6 Verknüpfungsanalyse als „E12" deployed (Feinschliff offen). AP 2.2 (Behinderungs-/Bedenkenanzeigen) noch nicht begonnen. AP 2.5 (Protokollgenerierung) in Vorbereitung.

Datenstand: 615 Vorgänge, 322 Prüfschritte, 9 Firmen, 643 Dokumente, 13.155 LV-Positionen, 4.779 BKI-Baupreise. Alembic 007.

---

## 2. Repo-Orientierung

- **API:** `api/` — FastAPI (sync), SQLAlchemy 2.x sync mit `text()`-SQL, Pydantic v2. Service-Pattern: `…Service(db)` als einzige DB-Zugriffsstelle. Router-Funktionen sind `def` (kein async). `requirements.txt` liegt in `api/`, Build-Context `./api`.
- **Nachträge:** `api/nachtraege/` (schemas/service/router/lv_abgleich/kostenabgleich/entscheidungsvorlage).
- **Frontend:** `frontend/index.html` — monolithische React-SPA (React 18 via CDN, Babel Standalone, kein Build-Step). Anker: Tab-Array ~Z. 2846, Tab-Rendering-Switch ~Z. 2914, `DashboardPage()` ~Z. 2985. Zum Lokalisieren `filesystem:edit_file` mit `dryRun: true`.
- **Migrationen:** `alembic/sql/` (z. B. `007_nachtragsmanagement.sql`), Skripte unter `scripts/`.
- **Tests:** `tests/`.
- **Compose:** `docker-compose.yaml` (Infra: Postgres, Qdrant, MinIO) und `docker-compose.services.yaml` (API, LiteLLM, Frontend).

**Deploy-Loop:** `git add -A && git commit` → `docker compose -f docker-compose.services.yaml build <dienst>` → `… up -d`.

**Betriebshinweise:** Ollama manuell starten (`ollama serve`). LiteLLM-Modellname ist `qwen-32b`. Ports: API 8110 extern / 8000 intern, Frontend 8091, Postgres 5436, LiteLLM 4003/4000, Docling 8070, Ollama 11434.

---

## 3. Code-Konventionen (häufige Stolperstellen)

- **PostgreSQL-Enums:** `CAST(:param AS typ)` verwenden, **nicht** `::typ` (kollidiert mit dem Bind-Parameter-Parser). Gleiches für `CAST(:param AS jsonb)`.
- **search_path:** `SET LOCAL search_path` wird nach jedem `commit` zurückgesetzt → nach jedem `self.db.commit()` neu setzen (oder `SET` ohne LOCAL je Transaktionsblock).
- **Python-Dateien:** bei indentation-sensitivem Inhalt komplette, saubere Datei erzeugen — kein in-place sed/regex-Patch.
- **PowerShell 7.6.0:** Here-Strings `@'…'@` per `Set-Content -Encoding utf8NoBOM` (kein Out-File, kein BOM). Achtung `$$`-Escaping in Here-Strings — bei SQL lieber Inline-SQL oder `.sql`-Datei pipen.
- **Spaltenname** ist `passwort_hash` (nicht `password_hash`; die Duplikat-Spalte `password_hash` wird nicht genutzt).

---

## 4. Empfohlene erste Arbeit — Produktions-Härtung (G3/G9)

Klein, hochwirksam, kein neues Feature. In dieser Reihenfolge:

1. **Commits pushen** (zuletzt 24+ ahead of origin) — Stand sichern, bevor Neues dazukommt.
2. **Dev-TOTP-Bypass deaktivieren** (`BAUPILOT_DEV_SKIP_TOTP`) und verifizieren, dass der reguläre TOTP-Pflichtweg greift.
3. **Default-Credentials rotieren:** Admin-Passwort ändern; DB-Passwort vom Platzhalter `CHANGE_ME_IN_PRODUCTION` auf ein lokal gesetztes Geheimnis (über `.env`, nicht in Code/Commit/Doku — G7).
4. **common_passwords.txt auf 10.000 erweitern.**
5. **Alembic-Konsolidierung:** die LV-Extraktions-Hotfixes in eine saubere nächste Migration überführen; Duplikat-Spalte `password_hash` entfernen.
6. **Systemprojekt** in `tenant_tlbv.projekte` sauber anlegen (`kurz='SYS'`).
7. **Kosmetik:** doppelten „Benutzer einladen"-Button im Dashboard entfernen.

(Maximilian Müllers abgelaufene Einladung erneuern — Admin-Aktion, kann begleitend geschehen.)

---

## 5. Danach — Feature-Gabel (Entscheidung trifft Martin)

- **AP 2.2 — Behinderungs-/Bedenkenanzeigen mit VOB-Textbausteinen.** Das einzige genuine Phase-2-Kernmodul, das noch fehlt. Reine VOB-Textbaustein-Arbeit (§4 Bedenken, §6 Behinderung), direkt am FLI-Schmerz (gestörter Bauablauf).
- **E12-Feinschliff (AP 2.6).** Vier fehlende Elemente, damit die Verknüpfungsanalyse für Nachtragsverhandlung/Rechnungshof taugt: `gruende` anzeigen, Q/Z/K am verknüpften Vorgang, durchgehende Kettenansicht (BED → BehA → NT, kumuliert), Σ-Zeile (Σ Kosten / Σ Verzugstage).
- **AP 2.5 — Protokollgenerierung Word/PDF.** Startpunkt Nachtrags-Prüfprotokoll (python-docx mit TLBV-Vorlage). F-201–F-205 zuvor in claude.ai klären. Signatur-Integration hängt an B-011 (FES).

**Empfehlung:** AP 2.2 oder E12-Feinschliff vor AP 2.5 und vor Netzplan — beide zahlen direkt auf den FLI-Nutzen ein, AP 2.5/Netzplan sind nachgelagert.

---

## 6. Nicht in Claude Code (sondern claude.ai)

B-006 (VS-NfD), B-011 (FES), B-014 (Gantt-Library), B-015 (Asta-Import), F-201–F-205 (AP 2.5-Scoping), die Vite-Migration als eigenes AP (B-013) inkl. Rollback-Plan, sowie jede neue Architektur-/Datenmodell-/Scope-Entscheidung. Diese kommen mit AD-Prozess zurück und werden in BP-V-18 protokolliert.

---

**Status:** Startbereit. Erste Aufgabe: Abschnitt 4 (Produktions-Härtung). Bei Entscheidungsbedarf zurück nach claude.ai.
