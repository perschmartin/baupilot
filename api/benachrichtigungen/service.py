"""Benachrichtigungs-Service.

Der Service hat zwei Aufgaben:
  1. CRUD-Schicht fuer die Liste/Lesen-Endpoints (von Anwendern via API genutzt).
  2. Trigger-API: `erstelle()`-Helper, der von anderen Service-Modulen
     (aufgaben, behinderungen, bedenken, maengel, nachtraege) aufgerufen
     wird, um eine Benachrichtigung an einen Benutzer anzulegen.

Die `erstelle()`-Funktion ist absichtlich tolerant: Wenn das Anlegen aus
irgendeinem Grund fehlschlaegt (z.B. unbekannter Typ), wird das im Log
vermerkt, aber kein Fehler an den Aufrufer weitergereicht — Benachrichtigungen
sind sekundaer und sollen niemals den Hauptvorgang (z.B. Aufgabe erstellen)
abbrechen lassen.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class BenachrichtigungError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


class BenachrichtigungsService:

    def __init__(self, db: Session, mandant_slug: str = ""):
        self.db = db
        self.mandant_slug = mandant_slug

    # =======================================================================
    # CRUD (von API-Endpoints aufgerufen)
    # =======================================================================

    def liste(
        self,
        benutzer_id: UUID,
        nur_ungelesen: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Eigene Benachrichtigungen des Benutzers laden."""
        where = ["benutzer_id = :bid"]
        params: dict[str, Any] = {"bid": str(benutzer_id)}
        if nur_ungelesen:
            where.append("gelesen = FALSE")
        where_clause = " AND ".join(where)

        gesamt = self.db.execute(
            text(f"SELECT COUNT(*) FROM benachrichtigungen WHERE {where_clause}"),
            params,
        ).scalar() or 0

        ungelesen = self.db.execute(
            text("SELECT COUNT(*) FROM benachrichtigungen WHERE benutzer_id = :bid AND gelesen = FALSE"),
            {"bid": str(benutzer_id)},
        ).scalar() or 0

        params["limit"] = limit
        params["offset"] = offset
        rows = self.db.execute(
            text(f"""
                SELECT id, benutzer_id, vorgang_id, typ::text AS typ,
                       prioritaet::text AS prioritaet,
                       titel, inhalt, gelesen, gelesen_am, erstellt_am
                FROM benachrichtigungen
                WHERE {where_clause}
                ORDER BY erstellt_am DESC
                LIMIT :limit OFFSET :offset
            """),
            params,
        ).mappings().all()

        return {
            "benachrichtigungen": [dict(r) for r in rows],
            "gesamt": gesamt,
            "ungelesen": ungelesen,
        }

    def ungelesen_anzahl(self, benutzer_id: UUID) -> int:
        """Leichtgewichtiges Polling fuer das Bell-Badge."""
        return self.db.execute(
            text("SELECT COUNT(*) FROM benachrichtigungen WHERE benutzer_id = :bid AND gelesen = FALSE"),
            {"bid": str(benutzer_id)},
        ).scalar() or 0

    def markiere_gelesen(self, benutzer_id: UUID, benachrichtigung_id: UUID) -> None:
        """Einzelne Benachrichtigung als gelesen markieren.

        Wir aktualisieren nur, wenn die Benachrichtigung dem Benutzer gehoert —
        verhindert Cross-User-Markieren ueber API-Manipulation.
        """
        result = self.db.execute(
            text("""
                UPDATE benachrichtigungen
                SET gelesen = TRUE, gelesen_am = NOW()
                WHERE id = :id AND benutzer_id = :bid AND gelesen = FALSE
            """),
            {"id": str(benachrichtigung_id), "bid": str(benutzer_id)},
        )
        if result.rowcount == 0:
            # Entweder schon gelesen oder gehoert nicht dem Benutzer — beides ist
            # keine Fehlersituation aus Anwendersicht. Kein Exception.
            pass
        self.db.commit()

    def markiere_alle_gelesen(self, benutzer_id: UUID) -> int:
        """Alle ungelesenen Benachrichtigungen eines Benutzers als gelesen markieren."""
        result = self.db.execute(
            text("""
                UPDATE benachrichtigungen
                SET gelesen = TRUE, gelesen_am = NOW()
                WHERE benutzer_id = :bid AND gelesen = FALSE
            """),
            {"bid": str(benutzer_id)},
        )
        self.db.commit()
        return result.rowcount

    # =======================================================================
    # TRIGGER (von anderen Service-Modulen aufgerufen)
    # =======================================================================

    def erstelle(
        self,
        benutzer_id: UUID | str,
        typ: str,
        titel: str,
        inhalt: str,
        prioritaet: str = "info",
        vorgang_id: UUID | str | None = None,
    ) -> UUID | None:
        """Eine Benachrichtigung anlegen.

        Fehler werden geloggt, aber nicht weitergeworfen — siehe Modul-Docstring.
        Rueckgabewert: ID der neuen Benachrichtigung oder None bei Fehler.
        """
        try:
            row = self.db.execute(
                text("""
                    INSERT INTO benachrichtigungen
                        (benutzer_id, vorgang_id, typ, prioritaet, titel, inhalt)
                    VALUES
                        (:bid,
                         :vid,
                         CAST(:typ AS public.benachrichtigungstyp),
                         CAST(:prio AS public.benachrichtigungs_prioritaet),
                         :titel, :inhalt)
                    RETURNING id
                """),
                {
                    "bid": str(benutzer_id),
                    "vid": str(vorgang_id) if vorgang_id else None,
                    "typ": typ,
                    "prio": prioritaet,
                    "titel": titel,
                    "inhalt": inhalt,
                },
            ).mappings().first()
            self.db.commit()
            return row["id"] if row else None
        except Exception as e:
            logger.warning("Benachrichtigung konnte nicht erstellt werden: %s", e)
            try:
                self.db.rollback()
            except Exception:
                pass
            return None
