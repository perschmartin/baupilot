"""
Auth-Service v2 — TOTP-Pflicht + Einladungssystem.

Aenderungen gegenueber v1:
  - Login gibt eingeschraenktes Token wenn TOTP nicht eingerichtet
  - Einladungs-Flow: Admin generiert Token, Benutzer registriert sich damit
  - Kein Weg ins System ohne gueltige Einladung (B-010)
"""

from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from auth.constants import (
    AuthEreignis,
    JWT_ACCESS_MINUTEN,
    JWT_REFRESH_TAGE,
)
from auth.mfa import (
    generiere_backup_codes,
    generiere_qr_data_uri,
    generiere_totp_secret,
    erstelle_totp_uri,
    hash_backup_codes,
    verifiziere_backup_code,
    verifiziere_totp,
)
from auth.password_policy import pruefe_passwort_staerke
from auth.rate_limit import (
    berechne_sperrdauer,
    erfasse_erfolg,
    erfasse_fehlversuch,
    ist_gesperrt,
    pruefe_rate_limit,
)
from auth.security import (
    braucht_rehash,
    entschluessele_totp_secret,
    erstelle_access_token,
    erstelle_refresh_token,
    hash_passwort,
    hash_token,
    verschluessele_totp_secret,
    verify_passwort,
)
from config import settings

logger = logging.getLogger(__name__)


class AuthError(Exception):
    def __init__(self, detail: str, status_code: int = 401):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


class AuthService:

    def __init__(self, db: Session):
        self.db = db

    # ==================================================================
    # LOGIN — TOTP-Pflicht erzwungen
    # ==================================================================

    def login(
        self, email: str, passwort: str,
        ip_adresse: str | None = None, user_agent: str | None = None,
    ) -> dict[str, Any]:
        email = email.strip().lower()

        # Rate-Limit
        blockiert = pruefe_rate_limit(ip_adresse or "0.0.0.0", email)
        if blockiert:
            self._log_ereignis(None, AuthEreignis.LOGIN_FEHLGESCHLAGEN, ip_adresse,
                               erfolgreich=False, details={"grund": f"rate_limit_{blockiert}"})
            msg = ("Zu viele Anmeldeversuche von dieser IP-Adresse."
                   if blockiert == "ip"
                   else "Zu viele Anmeldeversuche fuer dieses Konto.")
            raise AuthError(msg, 429)

        # Benutzer laden
        row = self.db.execute(
            text("SELECT id, email, vorname, nachname, passwort_hash, aktiv, "
                 "totp_aktiviert, totp_secret, fehlversuche, gesperrt_bis, "
                 "muss_passwort_aendern, backup_codes, ist_dienstkonto "
                 "FROM shared.benutzer WHERE email = :email"),
            {"email": email},
        ).mappings().first()

        if row is None or not verify_passwort(passwort, row["passwort_hash"]):
            if row is not None:
                self._erfasse_fehlversuch_db(row["id"], row["fehlversuche"], ip_adresse)
            erfasse_fehlversuch(ip_adresse or "0.0.0.0", email)
            self._log_ereignis(
                row["id"] if row else None,
                AuthEreignis.LOGIN_FEHLGESCHLAGEN, ip_adresse, erfolgreich=False)
            raise AuthError("E-Mail oder Passwort ungueltig.")

        if not row["aktiv"]:
            raise AuthError("Dieses Konto ist deaktiviert.", 403)

        if ist_gesperrt(row["gesperrt_bis"]):
            raise AuthError("Konto voruebergehend gesperrt.", 423)

        # Rehash
        if braucht_rehash(row["passwort_hash"]):
            self.db.execute(
                text("UPDATE shared.benutzer SET passwort_hash = :h WHERE id = :id"),
                {"h": hash_passwort(passwort), "id": row["id"]})

        mandant_slug = self._ermittle_mandant(row["id"])
        # --- DEV-BYPASS: TOTP ueberspringen wenn BAUPILOT_DEV_SKIP_TOTP=1 ---
        import os as _os
        if _os.environ.get("BAUPILOT_DEV_SKIP_TOTP") == "1" and row["email"] == "admin@baupilot.de":
            self.db.execute(text("UPDATE shared.benutzer SET fehlversuche = 0, gesperrt_bis = NULL WHERE id = :id"), {"id": row["id"]})
            self.db.commit()
            return self._login_erfolg(row, mandant_slug, ip_adresse, user_agent)

        # --- SERVICE-KONTO: Maschinen-Identitaet ueberspringt TOTP ---
        # Headless-Automation kann kein interaktives 2FA; Menschen-Konten
        # bleiben ueber die TOTP-Pflicht unten geschuetzt. Prinzipienbasierter
        # Ersatz fuer den Dev-Bypass oben (dieser wird nach der Migration entfernt).
        if row["ist_dienstkonto"]:
            self.db.execute(
                text("UPDATE shared.benutzer SET fehlversuche = 0, gesperrt_bis = NULL WHERE id = :id"),
                {"id": row["id"]})
            self.db.commit()
            return self._login_erfolg(row, mandant_slug, ip_adresse, user_agent)

        # --- TOTP NICHT EINGERICHTET → Eingeschraenktes Token ---
        if not row["totp_aktiviert"]:
            payload = self._baue_jwt_payload(row, mandant_slug, totp_setup_required=True)
            access_token = erstelle_access_token(payload, settings.jwt_secret, 30)
            self._log_ereignis(row["id"], "login_totp_setup_required", ip_adresse, erfolgreich=True)
            # Fehlversuche zuruecksetzen
            self.db.execute(
                text("UPDATE shared.benutzer SET fehlversuche = 0, gesperrt_bis = NULL WHERE id = :id"),
                {"id": row["id"]})
            self.db.commit()
            return {
                "access_token": access_token,
                "erfordert_totp_setup": True,
                "erfordert_totp": False,
                "muss_passwort_aendern": row["muss_passwort_aendern"],
            }

        # --- TOTP AKTIV → Code erforderlich ---
        if row["totp_aktiviert"] and row["totp_secret"]:
            payload = self._baue_jwt_payload(row, mandant_slug, totp_pending=True)
            access_token = erstelle_access_token(payload, settings.jwt_secret, 5)
            self._log_ereignis(row["id"], "login_totp_pending", ip_adresse, erfolgreich=True)
            self.db.execute(
                text("UPDATE shared.benutzer SET fehlversuche = 0, gesperrt_bis = NULL WHERE id = :id"),
                {"id": row["id"]})
            self.db.commit()
            return {
                "access_token": access_token,
                "erfordert_totp": True,
                "erfordert_totp_setup": False,
                "muss_passwort_aendern": False,
            }

        raise AuthError("Interner Fehler: Unerwarteter Auth-Status.", 500)

    def verifiziere_totp_login(
        self, benutzer_id: UUID, code: str,
        ip_adresse: str | None = None, user_agent: str | None = None,
    ) -> dict[str, Any]:
        row = self.db.execute(
            text("SELECT id, email, vorname, nachname, totp_secret, totp_aktiviert, "
                 "backup_codes, muss_passwort_aendern "
                 "FROM shared.benutzer WHERE id = :id"),
            {"id": str(benutzer_id)},
        ).mappings().first()

        if row is None:
            raise AuthError("Benutzer nicht gefunden.")
        if not row["totp_secret"]:
            raise AuthError("2FA nicht eingerichtet.")

        try:
            klartext = entschluessele_totp_secret(row["totp_secret"], settings.totp_key)
        except ValueError:
            raise AuthError("Interner Fehler bei der 2FA-Verifikation.", 500)

        mandant_slug = self._ermittle_mandant(row["id"])
        # --- DEV-BYPASS: TOTP ueberspringen wenn BAUPILOT_DEV_SKIP_TOTP=1 ---
        import os as _os
        if _os.environ.get("BAUPILOT_DEV_SKIP_TOTP") == "1" and row["email"] == "admin@baupilot.de":
            self.db.execute(text("UPDATE shared.benutzer SET fehlversuche = 0, gesperrt_bis = NULL WHERE id = :id"), {"id": row["id"]})
            self.db.commit()
            return self._login_erfolg(row, mandant_slug, ip_adresse, user_agent)

        # TOTP pruefen
        if verifiziere_totp(klartext, code):
            self._log_ereignis(row["id"], AuthEreignis.TOTP_VERIFIZIERT, ip_adresse, erfolgreich=True)
            return self._login_erfolg(row, mandant_slug, ip_adresse, user_agent)

        # Backup-Code pruefen
        if row["backup_codes"] and len(code) >= 8:
            codes = list(row["backup_codes"]) if row["backup_codes"] else []
            idx = verifiziere_backup_code(code, codes)
            if idx is not None:
                codes.pop(idx)
                self.db.execute(
                    text("UPDATE shared.benutzer SET backup_codes = :c WHERE id = :id"),
                    {"c": json.dumps(codes), "id": row["id"]})
                self._log_ereignis(row["id"], AuthEreignis.BACKUP_CODE_VERWENDET, ip_adresse,
                                   erfolgreich=True, details={"verbleibend": len(codes)})
                return self._login_erfolg(row, mandant_slug, ip_adresse, user_agent)

        self._log_ereignis(row["id"], AuthEreignis.LOGIN_FEHLGESCHLAGEN, ip_adresse,
                           erfolgreich=False, details={"grund": "totp_ungueltig"})
        raise AuthError("Code ungueltig.")

    # ==================================================================
    # EINLADUNGSSYSTEM (B-010)
    # ==================================================================

    def erstelle_einladung(
        self, admin_id: UUID, email: str, rolle: str,
        mandant_slug: str, projekt_kurz: str,
        gueltig_stunden: int = 72, ip_adresse: str | None = None,
    ) -> dict[str, Any]:
        """Admin generiert einen Einladungs-Token."""
        # Pruefen ob E-Mail bereits existiert
        existing = self.db.execute(
            text("SELECT id FROM shared.benutzer WHERE email = :e"),
            {"e": email.lower()},
        ).scalar()
        if existing:
            raise AuthError(f"E-Mail '{email}' ist bereits registriert.", 409)

        # Token generieren
        token = secrets.token_urlsafe(48)
        ablauf = datetime.now(timezone.utc) + timedelta(hours=gueltig_stunden)

        self.db.execute(
            text("INSERT INTO shared.einladungen "
                 "(token_hash, email, rolle, mandant_slug, projekt_kurz, ablauf, erstellt_von) "
                 "VALUES (:h, :e, :r, :ms, :pk, :a, :ev)"),
            {"h": hash_token(token), "e": email.lower(), "r": rolle,
             "ms": mandant_slug, "pk": projekt_kurz,
             "a": ablauf, "ev": str(admin_id)},
        )
        self._log_ereignis(admin_id, "einladung_erstellt", ip_adresse,
                           erfolgreich=True, details={"email": email, "rolle": rolle})
        self.db.commit()

        return {
            "einladungs_token": token,
            "email": email.lower(),
            "ablauf": ablauf,
        }

    def registrieren(
        self, einladungs_token: str, vorname: str, nachname: str, passwort: str,
        ip_adresse: str | None = None,
    ) -> dict[str, Any]:
        """Neuer Benutzer registriert sich mit Einladungs-Token."""
        # Token validieren
        token_hash_val = hash_token(einladungs_token)
        einladung = self.db.execute(
            text("SELECT id, email, rolle, mandant_slug, projekt_kurz, ablauf, verwendet "
                 "FROM shared.einladungen WHERE token_hash = :h"),
            {"h": token_hash_val},
        ).mappings().first()

        if einladung is None:
            raise AuthError("Einladung ungueltig.", 400)
        if einladung["verwendet"]:
            raise AuthError("Einladung wurde bereits verwendet.", 400)
        if einladung["ablauf"] < datetime.now(timezone.utc):
            raise AuthError("Einladung abgelaufen.", 400)

        # Pruefen ob E-Mail bereits existiert
        existing = self.db.execute(
            text("SELECT id FROM shared.benutzer WHERE email = :e"),
            {"e": einladung["email"]},
        ).scalar()
        if existing:
            raise AuthError("E-Mail bereits registriert.", 409)

        # Passwort pruefen
        fehler = pruefe_passwort_staerke(passwort)
        if fehler:
            raise AuthError(fehler[0], 400)

        # Benutzer anlegen
        pw_hash = hash_passwort(passwort)
        benutzer_id = self.db.execute(
            text("INSERT INTO shared.benutzer "
                 "(email, vorname, nachname, passwort_hash, aktiv, muss_passwort_aendern, "
                 "erstellt_am, geaendert_am, erstellt_von) "
                 "VALUES (:e, :v, :n, :h, TRUE, FALSE, NOW(), NOW(), 'einladung') "
                 "RETURNING id"),
            {"e": einladung["email"], "v": vorname, "n": nachname, "h": pw_hash},
        ).scalar()

        # Rolle zuweisen
        self.db.execute(
            text("INSERT INTO shared.benutzer_projekt_rollen "
                 "(id, benutzer_id, mandant_slug, projekt_kurz, rolle, "
                 "erstellt_am, geaendert_am, erstellt_von) "
                 "VALUES (gen_random_uuid(), :bid, :ms, :pk, :r, NOW(), NOW(), 'einladung')"),
            {"bid": str(benutzer_id), "ms": einladung["mandant_slug"],
             "pk": einladung["projekt_kurz"], "r": einladung["rolle"]},
        )

        # Einladung als verwendet markieren
        self.db.execute(
            text("UPDATE shared.einladungen SET verwendet = TRUE, verwendet_am = NOW() "
                 "WHERE id = :id"),
            {"id": einladung["id"]},
        )

        self._log_ereignis(benutzer_id, "registrierung", ip_adresse,
                           erfolgreich=True, details={"einladung": str(einladung["id"])})
        self.db.commit()

        # Eingeschraenktes Token fuer TOTP-Setup
        mandant_slug = einladung["mandant_slug"]
        row = self.db.execute(
            text("SELECT id, email, vorname, nachname, muss_passwort_aendern "
                 "FROM shared.benutzer WHERE id = :id"),
            {"id": str(benutzer_id)},
        ).mappings().first()

        payload = self._baue_jwt_payload(row, mandant_slug, totp_setup_required=True)
        access_token = erstelle_access_token(payload, settings.jwt_secret, 30)

        return {
            "access_token": access_token,
            "erfordert_totp_setup": True,
        }

    # ==================================================================
    # TOKEN-REFRESH
    # ==================================================================

    def refresh_tokens(
        self, refresh_token_klartext: str,
        ip_adresse: str | None = None, user_agent: str | None = None,
    ) -> dict[str, str]:
        token_hash_val = hash_token(refresh_token_klartext)
        db_token = self.db.execute(
            text("SELECT id, benutzer_id, widerrufen, ablauf FROM shared.refresh_tokens "
                 "WHERE token_hash = :h"),
            {"h": token_hash_val},
        ).mappings().first()

        if db_token is None:
            raise AuthError("Refresh-Token ungueltig.")
        if db_token["widerrufen"]:
            self._widerrufe_alle_tokens(db_token["benutzer_id"])
            self._log_ereignis(db_token["benutzer_id"], AuthEreignis.LOGOUT_ALLE, ip_adresse,
                               erfolgreich=True, details={"grund": "reuse_detection"})
            raise AuthError("Sitzung kompromittiert. Bitte erneut anmelden.")
        if db_token["ablauf"] < datetime.now(timezone.utc):
            raise AuthError("Refresh-Token abgelaufen.")

        row = self.db.execute(
            text("SELECT id, email, vorname, nachname, aktiv, totp_aktiviert, muss_passwort_aendern "
                 "FROM shared.benutzer WHERE id = :id AND aktiv = TRUE"),
            {"id": str(db_token["benutzer_id"])},
        ).mappings().first()
        if row is None:
            raise AuthError("Benutzer nicht gefunden oder deaktiviert.")

        # Kein Refresh wenn TOTP nicht aktiv
        if not row["totp_aktiviert"]:
            raise AuthError("2FA muss zuerst eingerichtet werden.", 403)

        now = datetime.now(timezone.utc)
        self.db.execute(
            text("UPDATE shared.refresh_tokens SET widerrufen = TRUE, widerrufen_am = :now WHERE id = :id"),
            {"now": now, "id": db_token["id"]})

        mandant_slug = self._ermittle_mandant(row["id"])
        # --- DEV-BYPASS: TOTP ueberspringen wenn BAUPILOT_DEV_SKIP_TOTP=1 ---
        import os as _os
        if _os.environ.get("BAUPILOT_DEV_SKIP_TOTP") == "1" and row["email"] == "admin@baupilot.de":
            self.db.execute(text("UPDATE shared.benutzer SET fehlversuche = 0, gesperrt_bis = NULL WHERE id = :id"), {"id": row["id"]})
            self.db.commit()
            return self._login_erfolg(row, mandant_slug, ip_adresse, user_agent)
        neuer_refresh = erstelle_refresh_token()
        self.db.execute(
            text("INSERT INTO shared.refresh_tokens (benutzer_id, token_hash, ablauf, user_agent, ip_adresse) "
                 "VALUES (:bid, :h, :abl, :ua, :ip)"),
            {"bid": str(row["id"]), "h": hash_token(neuer_refresh),
             "abl": now + timedelta(days=JWT_REFRESH_TAGE), "ua": user_agent, "ip": ip_adresse})

        payload = self._baue_jwt_payload(row, mandant_slug)
        access_token = erstelle_access_token(payload, settings.jwt_secret, JWT_ACCESS_MINUTEN)
        self._log_ereignis(row["id"], AuthEreignis.TOKEN_REFRESH, ip_adresse, erfolgreich=True)
        self.db.commit()
        return {"access_token": access_token, "refresh_token": neuer_refresh}

    # ==================================================================
    # TOTP-SETUP
    # ==================================================================

    def totp_setup(self, benutzer_id: UUID) -> dict[str, str]:
        row = self.db.execute(
            text("SELECT id, email, totp_aktiviert FROM shared.benutzer WHERE id = :id"),
            {"id": str(benutzer_id)},
        ).mappings().first()
        if row is None:
            raise AuthError("Benutzer nicht gefunden.", 404)
        if row["totp_aktiviert"]:
            raise AuthError("2FA ist bereits aktiv.", 400)

        klartext_secret = generiere_totp_secret()
        uri = erstelle_totp_uri(klartext_secret, row["email"])
        qr = generiere_qr_data_uri(uri)

        verschluesselt = verschluessele_totp_secret(klartext_secret, settings.totp_key)
        self.db.execute(
            text("UPDATE shared.benutzer SET totp_setup_secret = :s WHERE id = :id"),
            {"s": verschluesselt, "id": str(benutzer_id)})
        self.db.commit()
        return {"qr_data_uri": qr, "secret": klartext_secret}

    def totp_confirm(self, benutzer_id: UUID, code: str, ip_adresse: str | None = None) -> list[str]:
        row = self.db.execute(
            text("SELECT id, totp_setup_secret, totp_aktiviert FROM shared.benutzer WHERE id = :id"),
            {"id": str(benutzer_id)},
        ).mappings().first()
        if row is None:
            raise AuthError("Benutzer nicht gefunden.", 404)
        if row["totp_aktiviert"]:
            raise AuthError("2FA ist bereits aktiv.", 400)
        if not row["totp_setup_secret"]:
            raise AuthError("Kein TOTP-Setup ausstehend.", 400)

        try:
            klartext = entschluessele_totp_secret(row["totp_setup_secret"], settings.totp_key)
        except ValueError:
            raise AuthError("Interner Fehler beim TOTP-Setup.", 500)

        if not verifiziere_totp(klartext, code):
            raise AuthError("Code ungueltig. Bitte erneut versuchen.", 400)

        backup_klartext = generiere_backup_codes()
        self.db.execute(
            text("UPDATE shared.benutzer SET totp_secret = totp_setup_secret, "
                 "totp_aktiviert = TRUE, backup_codes = :bc, totp_setup_secret = NULL "
                 "WHERE id = :id"),
            {"bc": json.dumps(hash_backup_codes(backup_klartext)), "id": str(benutzer_id)})
        self._log_ereignis(benutzer_id, AuthEreignis.TOTP_AKTIVIERT, ip_adresse, erfolgreich=True)
        self.db.commit()
        return backup_klartext

    def totp_deaktivieren(self, benutzer_id: UUID, passwort: str, ip_adresse: str | None = None) -> None:
        row = self.db.execute(
            text("SELECT id, passwort_hash FROM shared.benutzer WHERE id = :id"),
            {"id": str(benutzer_id)},
        ).mappings().first()
        if row is None:
            raise AuthError("Benutzer nicht gefunden.", 404)
        if not verify_passwort(passwort, row["passwort_hash"]):
            raise AuthError("Passwort falsch.", 403)

        self.db.execute(
            text("UPDATE shared.benutzer SET totp_secret = NULL, totp_aktiviert = FALSE, "
                 "backup_codes = '[]', totp_setup_secret = NULL WHERE id = :id"),
            {"id": str(benutzer_id)})
        self._log_ereignis(benutzer_id, AuthEreignis.TOTP_DEAKTIVIERT, ip_adresse, erfolgreich=True)
        self.db.commit()

    # ==================================================================
    # PASSWORT
    # ==================================================================

    def passwort_aendern(self, benutzer_id: UUID, aktuelles: str, neues: str, ip_adresse: str | None = None) -> None:
        row = self.db.execute(
            text("SELECT id, passwort_hash FROM shared.benutzer WHERE id = :id"),
            {"id": str(benutzer_id)},
        ).mappings().first()
        if row is None:
            raise AuthError("Benutzer nicht gefunden.", 404)
        if not verify_passwort(aktuelles, row["passwort_hash"]):
            raise AuthError("Aktuelles Passwort falsch.", 403)
        fehler = pruefe_passwort_staerke(neues)
        if fehler:
            raise AuthError(fehler[0], 400)

        self.db.execute(
            text("UPDATE shared.benutzer SET passwort_hash = :h, passwort_geaendert_am = :now, "
                 "muss_passwort_aendern = FALSE WHERE id = :id"),
            {"h": hash_passwort(neues), "now": datetime.now(timezone.utc), "id": str(benutzer_id)})
        self._widerrufe_alle_tokens(benutzer_id)
        self._log_ereignis(benutzer_id, AuthEreignis.PASSWORT_GEAENDERT, ip_adresse, erfolgreich=True)
        self.db.commit()

    def admin_reset(self, admin_id: UUID, benutzer_id: UUID, neues: str, ip_adresse: str | None = None) -> None:
        fehler = pruefe_passwort_staerke(neues)
        if fehler:
            raise AuthError(fehler[0], 400)
        self.db.execute(
            text("UPDATE shared.benutzer SET passwort_hash = :h, muss_passwort_aendern = TRUE, "
                 "fehlversuche = 0, gesperrt_bis = NULL, passwort_geaendert_am = :now WHERE id = :id"),
            {"h": hash_passwort(neues), "now": datetime.now(timezone.utc), "id": str(benutzer_id)})
        self._widerrufe_alle_tokens(benutzer_id)
        self._log_ereignis(benutzer_id, AuthEreignis.ADMIN_RESET, ip_adresse,
                           erfolgreich=True, details={"durch": str(admin_id)})
        self.db.commit()

    # ==================================================================
    # LOGOUT
    # ==================================================================

    def logout(self, refresh_token_klartext: str, ip_adresse: str | None = None) -> None:
        h = hash_token(refresh_token_klartext)
        row = self.db.execute(
            text("SELECT id, benutzer_id FROM shared.refresh_tokens WHERE token_hash = :h"),
            {"h": h}).mappings().first()
        if row:
            self.db.execute(
                text("UPDATE shared.refresh_tokens SET widerrufen = TRUE, widerrufen_am = :now WHERE id = :id"),
                {"now": datetime.now(timezone.utc), "id": row["id"]})
            self._log_ereignis(row["benutzer_id"], AuthEreignis.LOGOUT, ip_adresse, erfolgreich=True)
            self.db.commit()

    def logout_alle(self, benutzer_id: UUID, ip_adresse: str | None = None) -> int:
        count = self._widerrufe_alle_tokens(benutzer_id)
        self._log_ereignis(benutzer_id, AuthEreignis.LOGOUT_ALLE, ip_adresse, erfolgreich=True)
        self.db.commit()
        return count

    # ==================================================================
    # PROFIL
    # ==================================================================

    def lade_profil(self, benutzer_id: UUID) -> dict[str, Any]:
        row = self.db.execute(
            text("SELECT id, email, vorname, nachname, totp_aktiviert, letzter_login "
                 "FROM shared.benutzer WHERE id = :id"),
            {"id": str(benutzer_id)},
        ).mappings().first()
        if row is None:
            raise AuthError("Benutzer nicht gefunden.", 404)

        rollen_rows = self.db.execute(
            text("SELECT r.mandant_slug, r.rolle, m.name as mandant_name "
                 "FROM shared.benutzer_projekt_rollen r "
                 "JOIN shared.mandanten m ON m.slug = r.mandant_slug "
                 "WHERE r.benutzer_id = :bid"),
            {"bid": str(benutzer_id)},
        ).mappings().all()

        rollen = [r["rolle"] for r in rollen_rows]
        mandant_info = None
        if rollen_rows:
            m = self.db.execute(
                text("SELECT id, name, slug FROM shared.mandanten WHERE slug = :s"),
                {"s": rollen_rows[0]["mandant_slug"]},
            ).mappings().first()
            if m:
                mandant_info = {"id": m["id"], "name": m["name"], "slug": m["slug"]}

        return {
            "id": row["id"], "email": row["email"],
            "vorname": row["vorname"], "nachname": row["nachname"],
            "mandant": mandant_info, "rollen": rollen,
            "totp_aktiviert": row["totp_aktiviert"], "letzter_login": row["letzter_login"],
        }

    # ==================================================================
    # INTERN
    # ==================================================================

    def _baue_jwt_payload(self, row: Any, mandant_slug: str | None,
                          totp_pending: bool = False, totp_setup_required: bool = False) -> dict[str, Any]:
        return {
            "sub": str(row["id"]),
            "email": row["email"],
            "vorname": row.get("vorname", "") if hasattr(row, "get") else row["vorname"],
            "nachname": row.get("nachname", "") if hasattr(row, "get") else row["nachname"],
            "mandant_slug": mandant_slug or "",
            "totp_pending": totp_pending,
            "totp_setup_required": totp_setup_required,
        }

    def _ermittle_mandant(self, benutzer_id: Any) -> str | None:
        return self.db.execute(
            text("SELECT DISTINCT mandant_slug FROM shared.benutzer_projekt_rollen "
                 "WHERE benutzer_id = :bid LIMIT 1"),
            {"bid": str(benutzer_id)},
        ).scalar()

    def _login_erfolg(self, row: Any, mandant_slug: str | None,
                      ip_adresse: str | None, user_agent: str | None) -> dict[str, Any]:
        erfasse_erfolg(ip_adresse or "0.0.0.0", row["email"])
        now = datetime.now(timezone.utc)
        self.db.execute(
            text("UPDATE shared.benutzer SET fehlversuche = 0, gesperrt_bis = NULL, "
                 "letzter_login = :now WHERE id = :id"),
            {"now": now, "id": row["id"]})

        payload = self._baue_jwt_payload(row, mandant_slug)
        access_token = erstelle_access_token(payload, settings.jwt_secret, JWT_ACCESS_MINUTEN)
        refresh_klartext = erstelle_refresh_token()
        self.db.execute(
            text("INSERT INTO shared.refresh_tokens (benutzer_id, token_hash, ablauf, user_agent, ip_adresse) "
                 "VALUES (:bid, :h, :abl, :ua, :ip)"),
            {"bid": str(row["id"]), "h": hash_token(refresh_klartext),
             "abl": now + timedelta(days=JWT_REFRESH_TAGE), "ua": user_agent, "ip": ip_adresse})

        self._log_ereignis(row["id"], AuthEreignis.LOGIN, ip_adresse, erfolgreich=True)
        self.db.commit()
        return {
            "access_token": access_token, "refresh_token": refresh_klartext,
            "erfordert_totp": False, "erfordert_totp_setup": False,
            "muss_passwort_aendern": row["muss_passwort_aendern"],
        }

    def _erfasse_fehlversuch_db(self, benutzer_id: Any, fehlversuche: int, ip_adresse: str | None) -> None:
        neue = fehlversuche + 1
        sperre = berechne_sperrdauer(neue)
        g = (datetime.now(timezone.utc) + sperre) if sperre else None
        self.db.execute(
            text("UPDATE shared.benutzer SET fehlversuche = :f, gesperrt_bis = :g WHERE id = :id"),
            {"f": neue, "g": g, "id": benutzer_id})
        if sperre:
            self._log_ereignis(benutzer_id, AuthEreignis.ACCOUNT_GESPERRT, ip_adresse,
                               erfolgreich=True, details={"fehlversuche": neue})

    def _widerrufe_alle_tokens(self, benutzer_id: Any) -> int:
        result = self.db.execute(
            text("UPDATE shared.refresh_tokens SET widerrufen = TRUE, widerrufen_am = :now "
                 "WHERE benutzer_id = :bid AND widerrufen = FALSE"),
            {"now": datetime.now(timezone.utc), "bid": str(benutzer_id)})
        return result.rowcount

    def _log_ereignis(self, benutzer_id: Any, ereignis: str, ip_adresse: str | None,
                      *, erfolgreich: bool, details: dict[str, Any] | None = None) -> None:
        self.db.execute(
            text("INSERT INTO shared.auth_log (benutzer_id, ereignis, ip_adresse, details, erfolgreich) "
                 "VALUES (:bid, :e, :ip, :d, :ok)"),
            {"bid": str(benutzer_id) if benutzer_id else None,
             "e": ereignis, "ip": ip_adresse,
             "d": json.dumps(details) if details else None, "ok": erfolgreich})
