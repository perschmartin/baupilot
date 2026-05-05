"""
Unit-Tests fuer das Auth-System.

36+ Testfaelle — alle ohne Datenbankabhaengigkeit.
Deckt die vier Kernmodule ab: security, mfa, rate_limit, password_policy.

Ausfuehren:
    pytest tests/test_auth_unit.py -v
"""

from __future__ import annotations

import time

import pytest

from auth.security import (
    braucht_rehash,
    entschluessele_totp_secret,
    erstelle_access_token,
    erstelle_refresh_token,
    hash_passwort,
    hash_token,
    validiere_access_token,
    verschluessele_totp_secret,
    verify_passwort,
)
from auth.mfa import (
    erstelle_totp_uri,
    generiere_backup_codes,
    generiere_qr_data_uri,
    generiere_totp_secret,
    hash_backup_codes,
    verifiziere_backup_code,
    verifiziere_totp,
)
from auth.rate_limit import (
    berechne_sperrdauer,
    erfasse_erfolg,
    erfasse_fehlversuch,
    ist_gesperrt,
    pruefe_rate_limit,
)
from auth.password_policy import pruefe_passwort_staerke


# ===================================================================
# PASSWORT-HASHING (Argon2id)
# ===================================================================

class TestPasswortHashing:
    def test_hash_und_verify(self):
        pw = "SicheresTestPasswort42!"
        hashed = hash_passwort(pw)
        assert hashed != pw
        assert hashed.startswith("$argon2id$")
        assert verify_passwort(pw, hashed)

    def test_falsches_passwort(self):
        hashed = hash_passwort("RichtigesPasswort1!")
        assert not verify_passwort("FalschesPasswort1!", hashed)

    def test_leerer_hash(self):
        """Default-Wert '' in DB darf nie matchen."""
        assert not verify_passwort("irgendwas", "")

    def test_none_hash(self):
        """None-Wert darf nicht crashen."""
        assert not verify_passwort("irgendwas", None)  # type: ignore

    def test_rehash_nicht_noetig(self):
        hashed = hash_passwort("TestPasswort123!")
        assert not braucht_rehash(hashed)

    def test_rehash_leerer_hash(self):
        assert not braucht_rehash("")


# ===================================================================
# JWT
# ===================================================================

class TestJWT:
    SECRET = "test-secret-key-fuer-unit-tests-mindestens-32-zeichen"

    def test_access_token_erzeugen_und_validieren(self):
        payload = {"sub": "user-123", "mandant_id": "m-456", "email": "test@tlbv.de"}
        token = erstelle_access_token(payload, self.SECRET, lebensdauer_minuten=5)
        result = validiere_access_token(token, self.SECRET)
        assert result is not None
        assert result["sub"] == "user-123"
        assert result["mandant_id"] == "m-456"
        assert result["typ"] == "access"

    def test_abgelaufener_token(self):
        payload = {"sub": "user-123"}
        # Negative Lebensdauer -> sofort abgelaufen
        token = erstelle_access_token(payload, self.SECRET, lebensdauer_minuten=-1)
        result = validiere_access_token(token, self.SECRET)
        assert result is None

    def test_falscher_secret(self):
        payload = {"sub": "user-123"}
        token = erstelle_access_token(payload, self.SECRET)
        result = validiere_access_token(token, "falscher-secret")
        assert result is None

    def test_manipulierter_token(self):
        result = validiere_access_token("manipuliert.token.hier", self.SECRET)
        assert result is None

    def test_refresh_token_format(self):
        token = erstelle_refresh_token()
        assert len(token) > 40  # URL-safe Base64, 64 Bytes
        assert " " not in token

    def test_hash_token_deterministisch(self):
        token = "test-token"
        h1 = hash_token(token)
        h2 = hash_token(token)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 Hex

    def test_hash_token_unterschiedlich(self):
        assert hash_token("token-a") != hash_token("token-b")


# ===================================================================
# TOTP-VERSCHLUESSELUNG (AES-256-GCM)
# ===================================================================

class TestTotpVerschluesselung:
    KEY = "a" * 64  # 256 Bit in Hex

    def test_verschluesseln_und_entschluesseln(self):
        secret = generiere_totp_secret()
        verschluesselt = verschluessele_totp_secret(secret, self.KEY)
        assert verschluesselt != secret
        entschluesselt = entschluessele_totp_secret(verschluesselt, self.KEY)
        assert entschluesselt == secret

    def test_falscher_schluessel(self):
        secret = "JBSWY3DPEHPK3PXP"
        verschluesselt = verschluessele_totp_secret(secret, self.KEY)
        anderer_key = "b" * 64
        with pytest.raises(ValueError):
            entschluessele_totp_secret(verschluesselt, anderer_key)

    def test_zu_kurzer_schluessel(self):
        with pytest.raises(ValueError):
            verschluessele_totp_secret("test", "abcd")

    def test_verschiedene_nonces(self):
        """Gleicher Klartext ergibt unterschiedliche Chiffrate (Nonce)."""
        secret = "JBSWY3DPEHPK3PXP"
        v1 = verschluessele_totp_secret(secret, self.KEY)
        v2 = verschluessele_totp_secret(secret, self.KEY)
        assert v1 != v2  # Unterschiedliche Nonces


# ===================================================================
# TOTP / MFA
# ===================================================================

class TestMFA:
    def test_generiere_secret(self):
        secret = generiere_totp_secret()
        assert len(secret) > 0
        assert all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567=" for c in secret)

    def test_totp_uri(self):
        secret = generiere_totp_secret()
        uri = erstelle_totp_uri(secret, "test@tlbv.de")
        assert uri.startswith("otpauth://totp/")
        assert "BauPilot" in uri

    def test_qr_data_uri(self):
        secret = generiere_totp_secret()
        uri = erstelle_totp_uri(secret, "test@tlbv.de")
        qr = generiere_qr_data_uri(uri)
        assert qr.startswith("data:image/png;base64,")

    def test_verify_totp_gueltig(self):
        import pyotp
        secret = generiere_totp_secret()
        totp = pyotp.TOTP(secret, digits=6, interval=30)
        current_code = totp.now()
        assert verifiziere_totp(secret, current_code)

    def test_verify_totp_ungueltig(self):
        secret = generiere_totp_secret()
        assert not verifiziere_totp(secret, "000000")

    def test_verify_totp_falsches_format(self):
        secret = generiere_totp_secret()
        assert not verifiziere_totp(secret, "")
        assert not verifiziere_totp(secret, "abc")
        assert not verifiziere_totp(secret, "12345")
        assert not verifiziere_totp(secret, "1234567")


# ===================================================================
# BACKUP-CODES
# ===================================================================

class TestBackupCodes:
    def test_generiere_codes(self):
        codes = generiere_backup_codes()
        assert len(codes) == 8
        for code in codes:
            assert len(code) == 8
            for verboten in "0O1IL":
                assert verboten not in code

    def test_hash_und_verify(self):
        codes = generiere_backup_codes()
        hashed = hash_backup_codes(codes)
        assert len(hashed) == 8
        idx = verifiziere_backup_code(codes[0], hashed)
        assert idx == 0

    def test_falscher_code(self):
        codes = generiere_backup_codes()
        hashed = hash_backup_codes(codes)
        idx = verifiziere_backup_code("XXXXXXXX", hashed)
        assert idx is None

    def test_case_insensitive(self):
        codes = generiere_backup_codes()
        hashed = hash_backup_codes(codes)
        idx = verifiziere_backup_code(codes[0].lower(), hashed)
        assert idx == 0


# ===================================================================
# RATE-LIMITING (In-Memory)
# ===================================================================

class TestRateLimit:
    def test_initial_erlaubt(self):
        result = pruefe_rate_limit("192.168.99.1", "frisch@example.com")
        assert result is None

    def test_ip_blocking(self):
        ip = "10.99.99.1"
        email = "ip-test-unique@example.com"
        for _ in range(10):
            erfasse_fehlversuch(ip, email)
        result = pruefe_rate_limit(ip, "anderer@example.com")
        assert result == "ip"

    def test_account_blocking(self):
        email = "account-block-unique@example.com"
        for i in range(5):
            erfasse_fehlversuch(f"172.16.99.{i}", email)
        result = pruefe_rate_limit("172.16.99.200", email)
        assert result == "account"

    def test_erfolg_setzt_account_zurueck(self):
        ip = "10.99.1.1"
        email = "reset-unique@example.com"
        for _ in range(4):
            erfasse_fehlversuch(ip, email)
        erfasse_erfolg(ip, email)
        result = pruefe_rate_limit("10.99.1.2", email)
        assert result is None


# ===================================================================
# DB-BASIERTE SPERRUNG (Hilfsfunktionen)
# ===================================================================

class TestSperrung:
    def test_keine_sperre_unter_schwelle(self):
        assert berechne_sperrdauer(2) is None

    def test_sperre_bei_3(self):
        dauer = berechne_sperrdauer(3)
        assert dauer is not None
        assert dauer.total_seconds() == 60

    def test_sperre_bei_5(self):
        dauer = berechne_sperrdauer(5)
        assert dauer is not None
        assert dauer.total_seconds() == 300

    def test_sperre_bei_15(self):
        dauer = berechne_sperrdauer(15)
        assert dauer is not None
        assert dauer.total_seconds() == 14400

    def test_ist_gesperrt_none(self):
        assert not ist_gesperrt(None)

    def test_ist_gesperrt_vergangenheit(self):
        from datetime import datetime, timezone
        vergangen = datetime(2020, 1, 1, tzinfo=timezone.utc)
        assert not ist_gesperrt(vergangen)

    def test_ist_gesperrt_zukunft(self):
        from datetime import datetime, timedelta, timezone
        zukunft = datetime.now(timezone.utc) + timedelta(hours=1)
        assert ist_gesperrt(zukunft)


# ===================================================================
# PASSWORT-STAERKE
# ===================================================================

class TestPasswortStaerke:
    def test_starkes_passwort(self):
        fehler = pruefe_passwort_staerke("Sicheres-Kennwort-42!")
        assert fehler == []

    def test_zu_kurz(self):
        fehler = pruefe_passwort_staerke("Kurz1!")
        assert any("12 Zeichen" in f for f in fehler)

    def test_nur_ziffern(self):
        fehler = pruefe_passwort_staerke("12345678901234")
        assert any("Ziffern" in f for f in fehler)

    def test_nur_buchstaben(self):
        fehler = pruefe_passwort_staerke("nurkleinebuchstaben")
        assert any("Buchstaben" in f for f in fehler)

    def test_triviales_muster_baupilot(self):
        fehler = pruefe_passwort_staerke("meinbaupilot123")
        assert any("Muster" in f for f in fehler)

    def test_triviales_muster_tlbv(self):
        fehler = pruefe_passwort_staerke("tlbv-sicher-2026")
        assert any("Muster" in f for f in fehler)

    def test_triviales_muster_passwort(self):
        fehler = pruefe_passwort_staerke("meinpasswort123")
        assert any("Muster" in f for f in fehler)

    def test_common_password(self):
        fehler = pruefe_passwort_staerke("password123")
        # Sollte mindestens als Muster oder Common-Password erkannt werden
        assert len(fehler) > 0
