"""
Konfigurationskonstanten fuer das Auth-System.

Alle Werte sind Defaults und koennen per .env ueberschrieben werden,
sofern in config.py abgebildet. Aenderungen an Sperrstufen oder
Token-Lebensdauern erfordern keinen AD-Prozess.
"""

# ---------------------------------------------------------------------------
# Passwort
# ---------------------------------------------------------------------------

PASSWORT_MIN_LAENGE = 12  # NIST SP 800-63B: Laenge > Komplexitaet
PASSWORT_MAX_LAENGE = 128

# Triviale Muster, die im Passwort nicht vorkommen duerfen.
# BauPilot-spezifisch ergaenzt gegenueber dem 2FA-Toolkit.
TRIVIALE_MUSTER = [
    "passwort", "password", "12345678", "qwertz", "qwerty",
    "baupilot", "bauherr", "bauherren", "tlbv", "thueringen",
    "thuringia", "erfurt", "jena", "admin", "letmein", "welcome",
]

# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------

JWT_ALGORITHMUS = "HS256"  # B-008: HS256 genuegt fuer Single-Server
JWT_ACCESS_MINUTEN = 15  # F-004: 15min Default, 30 fuer Landesnetz
JWT_REFRESH_TAGE = 7

# ---------------------------------------------------------------------------
# TOTP / 2FA
# ---------------------------------------------------------------------------

TOTP_ISSUER = "BauPilot"
TOTP_DIGITS = 6
TOTP_INTERVAL = 30  # Sekunden
TOTP_VALID_WINDOW = 1  # +/-1 Intervall Toleranz fuer Clock-Drift

BACKUP_CODE_ANZAHL = 8  # F-003: 8 Stueck
BACKUP_CODE_LAENGE = 8

# Zeichen fuer Backup-Codes (ohne verwechselbare: 0/O, 1/I/L)
BACKUP_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

# ---------------------------------------------------------------------------
# Brute-Force-Schutz: In-Memory Sliding Window
# ---------------------------------------------------------------------------

RATE_LIMIT_IP_MAX = 10
RATE_LIMIT_IP_FENSTER = 15 * 60  # 15 Minuten

RATE_LIMIT_ACCOUNT_MAX = 5
RATE_LIMIT_ACCOUNT_FENSTER = 15 * 60

# ---------------------------------------------------------------------------
# Brute-Force-Schutz: DB-basierte progressive Sperrung
# ---------------------------------------------------------------------------

SPERRSTUFEN = {
    3: 60,         # 3 Fehlversuche  ->  1 Minute
    5: 300,        # 5 Fehlversuche  ->  5 Minuten
    10: 3600,      # 10 Fehlversuche -> 1 Stunde
    15: 14400,     # 15 Fehlversuche -> 4 Stunden
}

# ---------------------------------------------------------------------------
# Auth-Ereignisse (muessen mit dem DB-Enum uebereinstimmen)
# ---------------------------------------------------------------------------

class AuthEreignis:
    LOGIN = "login"
    LOGIN_FEHLGESCHLAGEN = "login_fehlgeschlagen"
    TOKEN_REFRESH = "token_refresh"
    TOTP_AKTIVIERT = "totp_aktiviert"
    TOTP_DEAKTIVIERT = "totp_deaktiviert"
    TOTP_VERIFIZIERT = "totp_verifiziert"
    PASSWORT_GEAENDERT = "passwort_geaendert"
    ACCOUNT_GESPERRT = "account_gesperrt"
    ACCOUNT_ENTSPERRT = "account_entsperrt"
    ADMIN_RESET = "admin_reset"
    LOGOUT = "logout"
    LOGOUT_ALLE = "logout_alle"
    BACKUP_CODE_VERWENDET = "backup_code_verwendet"
