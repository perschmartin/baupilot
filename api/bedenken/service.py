"""Bedenken-Service (AP 2.2b).

Sehr ähnlich zu BehinderungService — gleicher Workflow, gleiche
Tabellenstruktur (bedenkenpruefung). Zusätzlich: lv_id-Filterung in
der Liste, PATCH fuer gewaehrleistung_bis.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

SCHRITT_TITEL = {
    1: "Erfassung",
    2: "Pruefung",
    3: "Anerkennung / Rueckweisung",
    4: "Schriftverkehr",
    5: "Erneute Pruefung",
    6: "Abmeldung GU",
}

LEITUNGSSCHRITTE = {3, 6}
LEITUNGSROLLEN = {"projektleiter", "admin"}


class BedenkenError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


class BedenkenService:
    """Workflow-Logik fuer Bedenkenanzeigen (VOB/B §4 Abs. 3)."""

    def __init__(self, db: Session, mandant_slug: str = ""):
        self.db = db
        self.mandant_slug = mandant_slug

    # =======================================================================
    # LISTE
    # =======================================================================

    def lade_liste(
        self,
        projekt_kurz: str = "FLI",
        status: str | None = None,
        lv_id: UUID | None = None,
        suche: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> dict[str, Any]:
        projekt = self.db.execute(
            text("SELECT id FROM projekte WHERE kurz = :k AND NOT geloescht"),
            {"k": projekt_kurz},
        ).mappings().first()
        if not projekt:
            raise BedenkenError(f"Projekt '{projekt_kurz}' nicht gefunden.", 404)

        where_parts = ["v.projekt_id = :pid", "v.typ = 'bedenkenanzeige'", "NOT v.geloescht"]
        params: dict[str, Any] = {"pid": projekt["id"]}
        if status:
            where_parts.append("v.status = CAST(:status AS vorgangstatus)")
            params["status"] = status
        if lv_id:
            where_parts.append("v.lv_id = :lv_id")
            params["lv_id"] = str(lv_id)
        if suche:
            where_parts.append("(v.nummer ILIKE :suche OR v.gegenstand ILIKE :suche)")
            params["suche"] = f"%{suche}%"
        where_clause = " AND ".join(where_parts)

        gesamt = self.db.execute(
            text(f"SELECT COUNT(*) AS c FROM vorgaenge v WHERE {where_clause}"),
            params,
        ).scalar() or 0

        params["limit"] = limit
        params["offset"] = offset
        rows = self.db.execute(
            text(f"""
                SELECT v.id, v.nummer, v.gegenstand, v.beschreibung,
                       v.status::text, v.prioritaet,
                       v.kosten_eur, v.zeit_arbeitstage, v.qualitaet_bewertung,
                       v.verantwortlich_firma_id, v.bauteil_id, v.frist,
                       v.lv_id, v.gewaehrleistung_bis,
                       v.erstellt_am, v.erstellt_von, v.geaendert_am
                FROM vorgaenge v
                WHERE {where_clause}
                ORDER BY v.nummer ASC
                LIMIT :limit OFFSET :offset
            """),
            params,
        ).mappings().all()

        return {"bedenken": [dict(r) for r in rows], "gesamt": gesamt}

    # =======================================================================
    # DETAIL
    # =======================================================================

    def lade_detail(self, bedenken_id: UUID) -> dict[str, Any]:
        row = self.db.execute(
            text("""
                SELECT v.id, v.nummer, v.gegenstand, v.beschreibung,
                       v.status::text, v.prioritaet,
                       v.kosten_eur, v.zeit_arbeitstage, v.qualitaet_bewertung,
                       v.verantwortlich_firma_id, v.bauteil_id, v.frist,
                       v.lv_id, v.gewaehrleistung_bis,
                       v.erstellt_am, v.erstellt_von, v.geaendert_am
                FROM vorgaenge v
                WHERE v.id = :id AND v.typ = 'bedenkenanzeige' AND NOT v.geloescht
            """),
            {"id": str(bedenken_id)},
        ).mappings().first()

        if not row:
            raise BedenkenError("Bedenkenanzeige nicht gefunden.", 404)

        result = dict(row)

        schritte = self.db.execute(
            text("""
                SELECT id, schritt, titel, ergebnis, bearbeiter_id,
                       abgeschlossen, abgeschlossen_am,
                       ki_eingabe, ki_ergebnis, ki_konfidenz,
                       ki_bestaetigt, ki_bestaetigt_von, ki_bestaetigt_am,
                       erstellt_am, erstellt_von
                FROM bedenkenpruefung
                WHERE vorgang_id = :vid
                ORDER BY schritt ASC
            """),
            {"vid": str(bedenken_id)},
        ).mappings().all()

        result["pruefschritte"] = [dict(s) for s in schritte]
        result["aktueller_schritt"] = max((s["schritt"] for s in schritte if s["abgeschlossen"]), default=0)
        return result

    # =======================================================================
    # SCHRITT ABSCHLIESSEN
    # =======================================================================

    def schritt_abschliessen(
        self,
        bedenken_id: UUID,
        schritt_nr: int,
        benutzer_id: str,
        benutzer_name: str,
        ergebnis: str,
        benutzer_rollen: set[str] | None = None,
    ) -> dict[str, Any]:
        if not 1 <= schritt_nr <= 6:
            raise BedenkenError("Schritt muss zwischen 1 und 6 liegen.", 400)

        bed = self.db.execute(
            text("SELECT id FROM vorgaenge WHERE id = :id AND typ = 'bedenkenanzeige' AND NOT geloescht"),
            {"id": str(bedenken_id)},
        ).mappings().first()
        if not bed:
            raise BedenkenError("Bedenkenanzeige nicht gefunden.", 404)

        if schritt_nr in LEITUNGSSCHRITTE:
            if benutzer_rollen is not None and not benutzer_rollen.intersection(LEITUNGSROLLEN):
                raise BedenkenError(
                    f"Schritt {schritt_nr} erfordert Rolle 'projektleiter' oder 'admin'.", 403
                )

        if schritt_nr > 1:
            offene = self.db.execute(
                text("""
                    SELECT schritt FROM bedenkenpruefung
                    WHERE vorgang_id = :vid AND schritt < :schritt AND NOT abgeschlossen
                    ORDER BY schritt
                """),
                {"vid": str(bedenken_id), "schritt": schritt_nr},
            ).mappings().all()
            if offene:
                fehlende = [str(o["schritt"]) for o in offene]
                raise BedenkenError(
                    f"Schritt(e) {', '.join(fehlende)} muessen zuerst abgeschlossen werden.", 409
                )

        self._erstelle_schritt_falls_fehlt(bedenken_id, schritt_nr, benutzer_id)

        self.db.execute(
            text("""
                UPDATE bedenkenpruefung
                SET ergebnis = :ergebnis,
                    bearbeiter_id = :bearbeiter,
                    abgeschlossen = TRUE,
                    abgeschlossen_am = NOW(),
                    geaendert_am = NOW(),
                    geaendert_von = :bearbeiter
                WHERE vorgang_id = :vid AND schritt = :schritt
            """),
            {
                "vid": str(bedenken_id),
                "schritt": schritt_nr,
                "ergebnis": ergebnis,
                "bearbeiter": benutzer_id,
            },
        )

        # Statuswechsel: gleiche Logik wie Behinderungen
        if schritt_nr == 3:
            self.db.execute(
                text("UPDATE vorgaenge SET status = 'in_bearbeitung', geaendert_am = NOW(), geaendert_von = :ben WHERE id = :id"),
                {"id": str(bedenken_id), "ben": benutzer_name},
            )
        elif schritt_nr == 6:
            self.db.execute(
                text("UPDATE vorgaenge SET status = 'abgeschlossen', geaendert_am = NOW(), geaendert_von = :ben WHERE id = :id"),
                {"id": str(bedenken_id), "ben": benutzer_name},
            )

        self.db.commit()
        return self.lade_detail(bedenken_id)

    # =======================================================================
    # UPDATE — derzeit nur gewaehrleistung_bis
    # =======================================================================

    def update(self, bedenken_id: UUID, benutzer_name: str, gewaehrleistung_bis: date | None) -> dict[str, Any]:
        bed = self.db.execute(
            text("SELECT id FROM vorgaenge WHERE id = :id AND typ = 'bedenkenanzeige' AND NOT geloescht"),
            {"id": str(bedenken_id)},
        ).mappings().first()
        if not bed:
            raise BedenkenError("Bedenkenanzeige nicht gefunden.", 404)
        self.db.execute(
            text("""
                UPDATE vorgaenge
                SET gewaehrleistung_bis = :gw, geaendert_am = NOW(), geaendert_von = :ben
                WHERE id = :id
            """),
            {"id": str(bedenken_id), "gw": gewaehrleistung_bis, "ben": benutzer_name},
        )
        self.db.commit()
        return self.lade_detail(bedenken_id)

    # =======================================================================
    # STATISTIK
    # =======================================================================

    def statistik(self, projekt_kurz: str = "FLI") -> dict[str, Any]:
        projekt = self.db.execute(
            text("SELECT id FROM projekte WHERE kurz = :k AND NOT geloescht"),
            {"k": projekt_kurz},
        ).mappings().first()
        if not projekt:
            raise BedenkenError(f"Projekt '{projekt_kurz}' nicht gefunden.", 404)

        sum_row = self.db.execute(
            text("""
                SELECT COUNT(*) AS c,
                       COALESCE(SUM(kosten_eur), 0) AS sk,
                       COALESCE(SUM(zeit_arbeitstage), 0) AS sz
                FROM vorgaenge
                WHERE projekt_id = :pid AND typ = 'bedenkenanzeige' AND NOT geloescht
            """),
            {"pid": projekt["id"]},
        ).mappings().first()

        nach_status = self.db.execute(
            text("""
                SELECT status::text AS s, COUNT(*) AS c,
                       COALESCE(SUM(kosten_eur), 0) AS sk,
                       COALESCE(SUM(zeit_arbeitstage), 0) AS sz
                FROM vorgaenge
                WHERE projekt_id = :pid AND typ = 'bedenkenanzeige' AND NOT geloescht
                GROUP BY status
                ORDER BY c DESC
            """),
            {"pid": projekt["id"]},
        ).mappings().all()

        nach_firma = self.db.execute(
            text("""
                SELECT COALESCE(f.kurz, f.name, 'Unbekannt') AS s,
                       COUNT(*) AS c,
                       COALESCE(SUM(v.kosten_eur), 0) AS sk,
                       COALESCE(SUM(v.zeit_arbeitstage), 0) AS sz
                FROM vorgaenge v
                LEFT JOIN firmen f ON f.id = v.verantwortlich_firma_id
                WHERE v.projekt_id = :pid AND v.typ = 'bedenkenanzeige' AND NOT v.geloescht
                GROUP BY f.id, f.kurz, f.name
                ORDER BY c DESC
                LIMIT 10
            """),
            {"pid": projekt["id"]},
        ).mappings().all()

        return {
            "gesamt": sum_row["c"],
            "summe_kosten_eur": float(sum_row["sk"]),
            "summe_zeit_arbeitstage": int(sum_row["sz"] or 0),
            "nach_status": [
                {"schluessel": r["s"], "anzahl": r["c"], "summe_kosten_eur": float(r["sk"]), "summe_zeit_arbeitstage": int(r["sz"] or 0)}
                for r in nach_status
            ],
            "nach_firma": [
                {"schluessel": r["s"], "anzahl": r["c"], "summe_kosten_eur": float(r["sk"]), "summe_zeit_arbeitstage": int(r["sz"] or 0)}
                for r in nach_firma
            ],
        }

    # =======================================================================
    # INTERN
    # =======================================================================

    def _erstelle_schritt_falls_fehlt(self, bedenken_id: UUID, schritt_nr: int, benutzer_id: str) -> None:
        self.db.execute(
            text("""
                INSERT INTO bedenkenpruefung (vorgang_id, schritt, titel, erstellt_von)
                VALUES (:vid, :schritt, :titel, :ben)
                ON CONFLICT (vorgang_id, schritt) DO NOTHING
            """),
            {
                "vid": str(bedenken_id),
                "schritt": schritt_nr,
                "titel": SCHRITT_TITEL.get(schritt_nr, f"Schritt {schritt_nr}"),
                "ben": benutzer_id,
            },
        )
