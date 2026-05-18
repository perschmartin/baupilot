"""
Aufgaben-Service — Geschaeftslogik fuer AP 1.3.

Folgt dem Auth-Service-Pattern:
- Einzige Stelle mit DB-Zugriff (text()-SQL)
- Sync-SQLAlchemy
- AufgabenError fuer alle Fehlerfaelle
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class AufgabenError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


# Gueltige Statusuebergaenge
GUELTIGE_UEBERGAENGE = {
    "offen": {"in_bearbeitung", "storniert"},
    "in_bearbeitung": {"geprueft", "storniert"},
    "geprueft": {"abgeschlossen", "offen", "storniert"},
    "abgeschlossen": set(),
    "storniert": set(),
}


class AufgabenService:

    def __init__(self, db: Session, mandant_slug: str = ""):
        self.db = db
        self.mandant_slug = mandant_slug

    def _commit(self):
        """Commit mit search_path-Wiederherstellung.
        SET LOCAL gilt nur innerhalb einer Transaktion.
        Nach commit() startet eine neue Transaktion ohne search_path.
        """
        self.db.commit()
        if self.mandant_slug:
            self.db.execute(
                text(f"SET LOCAL search_path TO tenant_{self.mandant_slug}, shared, public")
            )

    # ==================================================================
    # AUFGABE ERSTELLEN
    # ==================================================================

    def erstelle_aufgabe(
        self,
        projekt_kurz: str,
        gegenstand: str,
        erstellt_von_id: UUID,
        erstellt_von_name: str,
        beschreibung: str | None = None,
        prioritaet: str = "mittel",
        zustaendig_benutzer_id: UUID | None = None,
        frist: str | None = None,
        bauteil_id: UUID | None = None,
        lv_id: UUID | None = None,
        verantwortlich_firma_id: UUID | None = None,
        kosten_eur: float | None = None,
        zeit_arbeitstage: int | None = None,
        qualitaet_bewertung: str | None = None,
    ) -> dict[str, Any]:
        """Neue Aufgabe anlegen mit automatischer Nummernvergabe."""

        # Projekt-ID ermitteln
        projekt = self.db.execute(
            text("SELECT id FROM projekte WHERE kurz = :kurz AND NOT geloescht"),
            {"kurz": projekt_kurz},
        ).mappings().first()

        if not projekt:
            raise AufgabenError(f"Projekt '{projekt_kurz}' nicht gefunden.", 404)

        # Naechste Aufgabennummer
        result = self.db.execute(
            text("""
                SELECT COALESCE(MAX(
                    CAST(SUBSTRING(nummer FROM 4) AS INTEGER)
                ), 0) + 1 AS naechste
                FROM vorgaenge
                WHERE projekt_id = :pid AND typ = 'aufgabe' AND NOT geloescht
            """),
            {"pid": projekt["id"]},
        ).mappings().first()

        nummer = f"AF-{result['naechste']:03d}"

        # Einfuegen
        row = self.db.execute(
            text("""
                INSERT INTO vorgaenge (
                    projekt_id, typ, nummer, gegenstand, beschreibung, status,
                    prioritaet, zustaendig_benutzer_id, delegiert_von_benutzer_id,
                    frist, bauteil_id, lv_id, verantwortlich_firma_id,
                    kosten_eur, zeit_arbeitstage, qualitaet_bewertung,
                    erstellt_von
                ) VALUES (
                    :pid, 'aufgabe', :nummer, :gegenstand, :beschreibung, 'offen',
                    :prioritaet, :zustaendig, :delegiert_von,
                    :frist, :bauteil_id, :lv_id, :firma_id,
                    :kosten, :zeit, :qualitaet,
                    :erstellt_von
                )
                RETURNING id, nummer, gegenstand, beschreibung, prioritaet, status,
                          frist, zustaendig_benutzer_id, delegiert_von_benutzer_id,
                          kosten_eur, zeit_arbeitstage, qualitaet_bewertung,
                          erstellt_am, erstellt_von
            """),
            {
                "pid": projekt["id"],
                "nummer": nummer,
                "gegenstand": gegenstand,
                "beschreibung": beschreibung,
                "prioritaet": prioritaet,
                "zustaendig": str(zustaendig_benutzer_id) if zustaendig_benutzer_id else None,
                "delegiert_von": str(erstellt_von_id),
                "frist": frist,
                "bauteil_id": str(bauteil_id) if bauteil_id else None,
                "lv_id": str(lv_id) if lv_id else None,
                "firma_id": str(verantwortlich_firma_id) if verantwortlich_firma_id else None,
                "kosten": kosten_eur,
                "zeit": zeit_arbeitstage,
                "qualitaet": qualitaet_bewertung,
                "erstellt_von": erstellt_von_name,
            },
        ).mappings().first()

        self._commit()

        aufgabe = dict(row)

        # E10/B-012: Wenn ein anderer Benutzer als Zustaendiger eingetragen
        # wurde, bekommt dieser eine In-App-Benachrichtigung. Selbst-Zuweisung
        # (Ersteller = Zustaendiger) loest keine Benachrichtigung aus — der
        # Anwender weiss ohnehin, was er gerade angelegt hat.
        try:
            if zustaendig_benutzer_id and str(zustaendig_benutzer_id) != str(erstellt_von_id):
                # Lokaler Import, um Zirkel-Imports zu vermeiden
                from benachrichtigungen.service import BenachrichtigungsService

                BenachrichtigungsService(self.db).erstelle(
                    benutzer_id=zustaendig_benutzer_id,
                    typ="neuer_vorgang",
                    prioritaet="hinweis" if prioritaet in ("hoch", "kritisch") else "info",
                    titel=f"Neue Aufgabe {nummer}: {gegenstand[:80]}",
                    inhalt=(
                        f"{erstellt_von_name} hat dir die Aufgabe {nummer} zugewiesen."
                        + (f" Frist: {frist}" if frist else "")
                    ),
                    vorgang_id=aufgabe["id"],
                )
        except Exception as e:
            # Trigger-Fehler duerfen die Aufgaben-Erstellung NIE blockieren.
            # service.erstelle() faengt eigentlich selbst, dies hier ist Doppelnetz.
            import logging
            logging.getLogger(__name__).warning("Benachrichtigungs-Trigger fehlgeschlagen: %s", e)

        return aufgabe

    # ==================================================================
    # AUFGABEN AUFLISTEN
    # ==================================================================

    def liste_aufgaben(
        self,
        projekt_kurz: str,
        status: str | None = None,
        zustaendig_benutzer_id: UUID | None = None,
        prioritaet: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Aufgaben eines Projekts auflisten mit optionalen Filtern."""

        projekt = self.db.execute(
            text("SELECT id FROM projekte WHERE kurz = :kurz AND NOT geloescht"),
            {"kurz": projekt_kurz},
        ).mappings().first()

        if not projekt:
            raise AufgabenError(f"Projekt '{projekt_kurz}' nicht gefunden.", 404)

        # Query dynamisch zusammenbauen
        where_parts = ["v.projekt_id = :pid", "v.typ = 'aufgabe'", "NOT v.geloescht"]
        params: dict[str, Any] = {"pid": projekt["id"]}

        if status:
            where_parts.append("v.status = :status")
            params["status"] = status
        if zustaendig_benutzer_id:
            where_parts.append("v.zustaendig_benutzer_id = :zustaendig")
            params["zustaendig"] = str(zustaendig_benutzer_id)
        if prioritaet:
            where_parts.append("v.prioritaet = :prioritaet")
            params["prioritaet"] = prioritaet

        where_clause = " AND ".join(where_parts)

        # Zaehlen
        count_row = self.db.execute(
            text(f"SELECT COUNT(*) AS c FROM vorgaenge v WHERE {where_clause}"),
            params,
        ).mappings().first()

        # Daten mit Benutzer-Joins
        params["limit"] = limit
        params["offset"] = offset

        rows = self.db.execute(
            text(f"""
                SELECT v.id, v.nummer, v.gegenstand, v.beschreibung, v.prioritaet,
                       v.status, v.frist, v.zustaendig_benutzer_id,
                       v.delegiert_von_benutzer_id, v.verantwortlich_firma_id,
                       v.kosten_eur, v.zeit_arbeitstage, v.qualitaet_bewertung,
                       v.erstellt_am, v.geaendert_am, v.erstellt_von,
                       bz.vorname || ' ' || bz.nachname AS zustaendig_name,
                       bd.vorname || ' ' || bd.nachname AS delegiert_von_name
                FROM vorgaenge v
                LEFT JOIN shared.benutzer bz ON bz.id = v.zustaendig_benutzer_id
                LEFT JOIN shared.benutzer bd ON bd.id = v.delegiert_von_benutzer_id
                WHERE {where_clause}
                ORDER BY
                    CASE v.prioritaet
                        WHEN 'kritisch' THEN 1
                        WHEN 'hoch' THEN 2
                        WHEN 'mittel' THEN 3
                        WHEN 'niedrig' THEN 4
                    END,
                    v.frist ASC NULLS LAST,
                    v.erstellt_am DESC
                LIMIT :limit OFFSET :offset
            """),
            params,
        ).mappings().all()

        return {
            "aufgaben": [dict(r) for r in rows],
            "gesamt": count_row["c"],
        }

    # ==================================================================
    # AUFGABE DETAIL
    # ==================================================================

    def lade_aufgabe(self, aufgabe_id: UUID) -> dict[str, Any]:
        """Aufgabe mit Kommentaren laden."""

        row = self.db.execute(
            text("""
                SELECT v.id, v.nummer, v.gegenstand, v.beschreibung, v.prioritaet,
                       v.status, v.frist, v.zustaendig_benutzer_id,
                       v.delegiert_von_benutzer_id, v.verantwortlich_firma_id,
                       v.kosten_eur, v.zeit_arbeitstage, v.qualitaet_bewertung,
                       v.erstellt_am, v.geaendert_am, v.erstellt_von,
                       bz.vorname || ' ' || bz.nachname AS zustaendig_name,
                       bd.vorname || ' ' || bd.nachname AS delegiert_von_name
                FROM vorgaenge v
                LEFT JOIN shared.benutzer bz ON bz.id = v.zustaendig_benutzer_id
                LEFT JOIN shared.benutzer bd ON bd.id = v.delegiert_von_benutzer_id
                WHERE v.id = :id AND v.typ = 'aufgabe' AND NOT v.geloescht
            """),
            {"id": str(aufgabe_id)},
        ).mappings().first()

        if not row:
            raise AufgabenError("Aufgabe nicht gefunden.", 404)

        # Kommentare laden
        kommentare = self.db.execute(
            text("""
                SELECT id, autor_id, autor_name, inhalt, erstellt_am
                FROM aufgaben_kommentare
                WHERE vorgang_id = :vid
                ORDER BY erstellt_am ASC
            """),
            {"vid": str(aufgabe_id)},
        ).mappings().all()

        result = dict(row)
        result["kommentare"] = [dict(k) for k in kommentare]
        return result

    # ==================================================================
    # AUFGABE AKTUALISIEREN
    # ==================================================================

    def aktualisiere_aufgabe(
        self,
        aufgabe_id: UUID,
        benutzer_id: UUID,
        benutzer_name: str,
        **felder,
    ) -> dict[str, Any]:
        """Aufgabe aktualisieren. Statuswechsel wird validiert."""

        # Aktuelle Aufgabe laden
        current = self.db.execute(
            text("""
                SELECT id, status, typ FROM vorgaenge
                WHERE id = :id AND typ = 'aufgabe' AND NOT geloescht
            """),
            {"id": str(aufgabe_id)},
        ).mappings().first()

        if not current:
            raise AufgabenError("Aufgabe nicht gefunden.", 404)

        # Statuswechsel validieren
        neuer_status = felder.get("status")
        aktueller_status = str(current["status"])
        if neuer_status and neuer_status != aktueller_status:
            erlaubt = GUELTIGE_UEBERGAENGE.get(aktueller_status, set())
            if neuer_status not in erlaubt:
                raise AufgabenError(
                    f"Statuswechsel von '{aktueller_status}' nach '{neuer_status}' "
                    f"ist nicht erlaubt. Erlaubt: {', '.join(erlaubt) or 'keine'}.",
                    409,
                )

        # Nur gesetzte Felder aktualisieren
        set_parts = ["geaendert_am = NOW()", "geaendert_von = :benutzer_name"]
        params: dict[str, Any] = {
            "id": str(aufgabe_id),
            "benutzer_name": benutzer_name,
        }

        feld_mapping = {
            "gegenstand": "gegenstand",
            "beschreibung": "beschreibung",
            "prioritaet": "prioritaet",
            "status": "status",
            "frist": "frist",
            "kosten_eur": "kosten_eur",
            "zeit_arbeitstage": "zeit_arbeitstage",
            "qualitaet_bewertung": "qualitaet_bewertung",
        }

        for key, col in feld_mapping.items():
            if key in felder and felder[key] is not None:
                set_parts.append(f"{col} = :{key}")
                params[key] = felder[key]

        # UUID-Felder separat
        for key in ("zustaendig_benutzer_id", "bauteil_id", "lv_id", "verantwortlich_firma_id"):
            if key in felder and felder[key] is not None:
                set_parts.append(f"{key} = :{key}")
                params[key] = str(felder[key])

        set_clause = ", ".join(set_parts)

        self.db.execute(
            text(f"UPDATE vorgaenge SET {set_clause} WHERE id = :id"),
            params,
        )
        self._commit()

        return self.lade_aufgabe(aufgabe_id)

    # ==================================================================
    # KOMMENTAR HINZUFUEGEN
    # ==================================================================

    def erstelle_kommentar(
        self,
        aufgabe_id: UUID,
        autor_id: UUID,
        autor_name: str,
        inhalt: str,
    ) -> dict[str, Any]:
        """Kommentar an Aufgabe anfuegen (nicht loeschbar, G2)."""

        # Pruefen ob Aufgabe existiert
        exists = self.db.execute(
            text("""
                SELECT 1 FROM vorgaenge
                WHERE id = :id AND typ = 'aufgabe' AND NOT geloescht
            """),
            {"id": str(aufgabe_id)},
        ).first()

        if not exists:
            raise AufgabenError("Aufgabe nicht gefunden.", 404)

        row = self.db.execute(
            text("""
                INSERT INTO aufgaben_kommentare (vorgang_id, autor_id, autor_name, inhalt)
                VALUES (:vid, :aid, :aname, :inhalt)
                RETURNING id, autor_id, autor_name, inhalt, erstellt_am
            """),
            {
                "vid": str(aufgabe_id),
                "aid": str(autor_id),
                "aname": autor_name,
                "inhalt": inhalt,
            },
        ).mappings().first()

        self._commit()

        return dict(row)
