# BauPilot — Projektkontext fuer Claude Code

## Was ist BauPilot?

Mandantenfaehige, vollstaendig lokal betriebene Plattform zur digitalen Steuerung oeffentlicher Hochbauprojekte. Pilotanwendung: FLI Jena (Friedrich-Loeffler-Institut) des TLBV Thueringen. Nachnutzung der SPARK-Module des BMDS.

**Produktiv genutzt. Kein Prototyp.** Jede Aenderung hat operative Konsequenzen.

## Grundregeln (nicht verhandelbar)

- **G1 Sachliche Neutralitaet:** Keine Schuldzuweisungen in Texten/Prompts. Nur Fakten mit Quellenangabe.
- **G2 Digitale Souveraenitaet:** Keine externen KI-APIs zur Laufzeit. Nur lokale LLMs (Ollama via LiteLLM).
- **G3 Revisionssicherheit:** Zeitstempel, Urheber, nicht-loeschbare Historie. Append-Only wo noetig.
- **G6 Mandantenfaehigkeit:** Schema-per-Tenant (B-003). Kein Hardcode auf FLI/TLBV.
- **G7 Code oeffentlich, Daten nie:** GitHub perschmartin/baupilot. Keine Secrets, keine Daten im Repo.
- **G8 Dreiklang:** Qualitaet, Zeit (Arbeitstage), Kosten (EUR) als Pflichtfelder an jedem Vorgang.
- **G9 Secure by Default:** Sicherheit fuer oeffentliches Netz. Lockerungen per .env fuer Landesnetz.

## Stack

- **Backend:** Python 3.12, FastAPI (sync!), SQLAlchemy 2.x (sync, text()-SQL), Alembic, Pydantic v2
- **Frontend:** React 18 als einzelne index.html mit CDN-Imports (kein Build-Step, kein Vite)
- **DB:** PostgreSQL 16 (Schema-per-Tenant)
- **Infrastruktur:** Docker Compose, Qdrant, MinIO, LiteLLM, Ollama
- **Scripting:** PowerShell 7 (kein WSL/bash fuer Deployment)
- **OS:** Windows 11 Pro (Benutzer: Metis)

## Ports

| Dienst         | Port extern | Port intern | Container          |
|----------------|-------------|-------------|--------------------|
| PostgreSQL     | 5436        | 5432        | baupilot-postgres  |
| Qdrant         | 6345/6346   | 6333/6334   | baupilot-qdrant    |
| MinIO          | 9004/9005   | 9000/9001   | baupilot-minio     |
| LiteLLM        | 4003        | 4000        | baupilot-litellm   |
| BauPilot API   | 8110        | 8000        | baupilot-api       |
| Frontend       | 8091        | 80          | baupilot-frontend  |
| Ollama         | 11434       | —           | lokal (kein Docker) |

[BACKUP ORIGINAL — STAND 18.05.2026]
