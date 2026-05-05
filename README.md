# BauPilot Auth-System — Integrations-Paket

**Version:** AP 1.1, integriert mit 2FA-Toolkit
**Datum:** 05. Mai 2026
**Bearbeiter:** Martin Persch, Claude

---

## Herkunft

Dieses Paket integriert bewaehrte Patterns aus dem **2FA-Toolkit** (familienstiftung.software) in die BauPilot-Architektur. Folgende Module wurden uebernommen und angepasst:

| Toolkit-Modul | BauPilot-Ziel | Aenderungen |
|---|---|---|
| passwords.py | security.py | Deutsche Funktionsnamen, Default-Schutz bei leerem Hash |
| mfa.py | mfa.py | TOTP_ISSUER=BauPilot, Backup-Code-Alphabet aus Konstanten |
| rate_limit.py | rate_limit.py | Ergaenzt um DB-basierte Sperrdauer-Berechnung |
| hibp.py (nur check_password_strength) | password_policy.py | HIBP-API ENTFERNT (G2), lokale common_passwords.txt stattdessen |

Nicht uebernommen (architekturinkompatibel): sessions.py (Cookie statt JWT), dependencies.py (Cookie statt Bearer), router.py (Templates statt JSON), reset.py (SMTP statt Admin-Reset), alle Templates.

## Neue Funktionalitaet (nicht im Toolkit)

AES-256-GCM-Verschluesselung fuer TOTP-Secrets (security.py). JWT Access+Refresh mit Reuse Detection (security.py + service.py). Schema-per-Tenant-Aufloesung in Dependencies (dependencies.py). Progressive DB-basierte Sperrung (rate_limit.py + service.py). Admin-Passwort-Reset fuer Air-Gap (service.py, B-009).

---

## Dateistruktur

```
api/auth/
  __init__.py
  constants.py          # Konfigurationskonstanten
  security.py           # Argon2id + JWT + AES-256-GCM
  mfa.py                # TOTP + Backup-Codes
  rate_limit.py         # Sliding Window + DB-Sperrung
  password_policy.py    # Staerke-Pruefung + Common Passwords
  schemas.py            # Pydantic v2 Request/Response
  service.py            # Geschaeftslogik (DB-abhaengig)
  dependencies.py       # FastAPI Dependencies (JWT + Tenant)
  router.py             # API-Endpunkte (JSON)

api/data/
  common_passwords.txt  # 200 Eintraege (auf 10.000 erweitern)

alembic/sql/
  002_auth_erweiterung.sql

scripts/
  run-migration-002.ps1
  seed-admin.ps1
  run-tests-auth.ps1

tests/
  conftest.py
  test_auth_unit.py     # 36+ Unit-Tests
```

---

## Deployment-Schritte

### Voraussetzungen

Migration 001 ausgefuehrt. Stack laeuft (PostgreSQL, API, etc.).

### Schritt 1: Dateien kopieren

```powershell
# Auth-Modul
Copy-Item -Recurse api\auth\ C:\SPARK\spark-baupilot\api\auth\ -Force
Copy-Item -Recurse api\data\ C:\SPARK\spark-baupilot\api\data\ -Force

# Migration + Scripts
Copy-Item alembic\sql\002_auth_erweiterung.sql C:\SPARK\spark-baupilot\alembic\sql\
Copy-Item scripts\*.ps1 C:\SPARK\spark-baupilot\scripts\

# Tests
Copy-Item tests\*.py C:\SPARK\spark-baupilot\tests\
```

### Schritt 2: .env erweitern

```powershell
# Secrets generieren
python -c "import secrets; print('JWT_SECRET=' + secrets.token_hex(32))"
python -c "import secrets; print('TOTP_KEY=' + secrets.token_hex(32))"
```

Neue Variablen in .env:

```
# === Auth (AP 1.1) ===
BAUPILOT_JWT_SECRET=<64 Hex-Zeichen>
BAUPILOT_JWT_ACCESS_MINUTES=15
BAUPILOT_JWT_REFRESH_DAYS=7
BAUPILOT_TOTP_KEY=<64 Hex-Zeichen>
BAUPILOT_PASSWORT_MIN_LAENGE=12

# === Admin-Seed ===
BAUPILOT_ADMIN_EMAIL=admin@tlbv.de
BAUPILOT_ADMIN_VORNAME=Admin
BAUPILOT_ADMIN_NACHNAME=BauPilot
BAUPILOT_ADMIN_INITIAL_PW=<sicheres Einmal-Passwort>
```

### Schritt 3: requirements.txt erweitern

```
argon2-cffi>=23.1.0
PyJWT>=2.8.0
pyotp>=2.9.0
qrcode[pil]>=7.4.0
cryptography>=42.0.0
pydantic[email]>=2.0.0
```

### Schritt 4: Migration 002

```powershell
.\scripts\run-migration-002.ps1
```

### Schritt 5: API-Container neu bauen

```powershell
docker compose -f docker-compose.services.yaml build api
docker compose -f docker-compose.services.yaml up -d
```

### Schritt 6: Admin-Seed

```powershell
.\scripts\seed-admin.ps1
```

### Schritt 7: Tests

```powershell
.\scripts\run-tests-auth.ps1
```

### Schritt 8: Rauchtest

```powershell
# Login
$body = '{"email":"admin@tlbv.de","passwort":"<Initial-PW>"}'
$r = Invoke-RestMethod -Uri http://localhost:8110/api/v1/auth/login -Method Post -ContentType "application/json" -Body $body
$r.access_token

# Profil
$headers = @{Authorization="Bearer $($r.access_token)"}
Invoke-RestMethod -Uri http://localhost:8110/api/v1/auth/me -Headers $headers
```

---

## Integration in main.py

```python
from api.auth import auth_router
from api.auth.dependencies import get_db, get_jwt_secret, get_totp_key
from api.database import get_db as real_get_db
from api.config import get_settings

# Dependencies verdrahten
import api.auth.dependencies as auth_deps
auth_deps.get_db = real_get_db
auth_deps.get_jwt_secret = lambda: get_settings().jwt_secret
auth_deps.get_totp_key = lambda: get_settings().totp_key

# Router registrieren
app.include_router(auth_router)
```

---

## G2-Konformitaet

Keine externen API-Aufrufe zur Laufzeit. HIBP-Check entfernt. Common-Passwords-Liste lokal. TOTP-Secrets verschluesselt (AES-256-GCM). Auth-Log Append-Only. Alle Kryptographie lokal (Argon2id, SHA-256, AES-GCM, HMAC).
