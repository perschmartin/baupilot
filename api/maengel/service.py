"""Maengel-Service (AP 2.2c)."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# 5-Schritte-Workflow fuer Maengel
SCHRITT_TITEL = {
    1: "Erfassung",
    2: "Mangelschreiben",
    3: "Schriftverkehr",
    4: "Abmeldung GU/GP",
    5: "Bestaetigung Bauherr",
}

# Leitungsschritte: Mangelschreiben (Schritt 2, formaler Akt nach VOB/B §13)
# und Bestaetigung Bauherr (Schritt 5, finale Annahme)
LEITUNGSSCHRITTE = {2, 5}
LEITUNGSROLLEN = {"projektleiter", "admin"}


class MangelError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


class MangelService:
    """Workflow-Logik fuer Mangelanzeigen (VOB/B §13)."""

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
        mangelart: str | None = None,
        suche: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> dict[str, Any]:
        projekt = self.db.execute(
            text("SELECT id FROM projekte WHERE kurz = :k AND NOT geloescht"),
            {"k": projekt_kurz},
        ).mappings().first()
        if not projekt:
            raise MangelError(f"Projekt '{projekt_kurz}' nicht gefunden.", 404)

        where_parts = ["v.projekt_id = :pid", "v.typ = 'mangelanzeige'", "NOT v.geloescht"]
        params: dict[str, Any] = {"pid": projekt["id"]}
        if status:
            where_parts.append("v.status = CAST(:status AS vorgangstatus)")
            params["status"] = status
        if mangelart:
            where_parts.append("v.mangelart = CAST(:ma AS public.mangelart)")
            params["ma"] = mangelart
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
                       v.mangelart::text AS mangelart, v.verlaengerung_monate,
                       v.nachtragsfolge_eur, v.folgekosten_betrieb_eur, v.minderkosten_eur,
                       v.erstellt_am, v.erstellt_von, v.geaendert_am
                FROM vorgaenge v
                WHERE {where_clause}
                ORDER BY v.nummer ASC
                LIMIT :limit OFFSET :offset
            """),
            params,
        ).mappings().all()

        return {"maengel": [dict(r) for r in rows], "gesamt": gesamt}

    # =======================================================================
    # DETAIL
    # =======================================================================

    def lade_detail(self, mangel_id: UUID) -> dict[str, Any]:
        row = self.db.execute(
            text("""
                SELECT v.id, v.nummer, v.gegenstand, v.beschreibung,
                       v.status::text, v.prioritaet,
                       v.kosten_eur, v.zeit_arbeitstage, v.qualitaet_bewertung,
                       v.verantwortlich_firma_id, v.bauteil_id, v.frist,
                       v.mangelart::text AS mangelart, v.verlaengerung_monate,
                       v.nachtragsfolge_eur, v.folgekosten_betrieb_eur, v.minderkosten_eur,
                       v.erstellt_am, v.erstellt_von, v.geaendert_am
                FROM vorgaenge v
                WHERE v.id = :id AND v.typ = 'mangelanzeige' AND NOT v.geloescht
            """),
            {"id": str(mangel_id)},
        ).mappings().first()

        if not row:
            raise MangelError("Mangelanzeige nicht gefunden.", 404)

        result = dict(row)

        schritte = self.db.execute(
            text("""
                SELECT id, schritt, titel, ergebnis, bearbeiter_id,
                       abgeschlossen, abgeschlossen_am,
                       ki_eingabe, ki_ergebnis, ki_konfidenz,
                       ki_bestaetigt, ki_bestaetigt_von, ki_bestaetigt_am,
                       erstellt_am, erstellt_von
                FROM mangelpruefung
                WHERE vorgang_id = :vid
                ORDER BY schritt ASC
            """),
            {"vid": str(mangel_id)},
        ).mappings().all()

        result["pruefschritte"] = [dict(s) for s in schritte]
        result["aktueller_schritt"] = max((s["schritt"] for s in schritte if s["abgeschlossen"]), default=0)
        return result

    # =======================================================================
    # SCHRITT ABSCHLIESSEN
    # =======================================================================

    def schritt_abschliessen(
        self,
        mangel_id: UUID,
        schritt_nr: int,
        benutzer_id: str,
        benutzer_name: str,
        ergebnis: str,
        benutzer_rollen: set[str] | None = None,
    ) -> dict[str, Any]:
        if not 1 <= schritt_nr <= 5:
            raise MangelError("Schritt muss zwischen 1 und 5 liegen.", 400)

        m = self.db.execute(
            text("SELECT id FROM vorgaenge WHERE id = :id AND typ = 'mangelanzeige' AND NOT geloescht"),
            {"id": str(mangel_id)},
        ).mappings().first()
        if not m:
            raise MangelError("Mangelanzeige nicht gefunden.", 404)

        if schritt_nr in LEITUNGSSCHRITTE:
            if benutzer_rollen is not None and not benutzer_rollen.intersection(LEITUNGSROLLEN):
                raise MangelError(
                    f"Schritt {schritt_nr} erfordert Rolle 'projektleiter' oder 'admin'.", 403
                )

        if schritt_nr > 1:
            offene = self.db.execute(
                text("""
                    SELECT schritt FROM mangelpruefung
                    WHERE vorgang_id = :vid AND schritt < :schritt AND NOT abgeschlossen
                    ORDER BY schritt
                """),
                {"vid": str(mangel_id), "schritt": schritt_nr},
            ).mappings().all()
            if offene:
                fehlende = [str(o["schritt"]) for o in offene]
                raise MangelError(
                    f"Schritt(e) {', '.join(fehlende)} muessen zuerst abgeschlossen werden.", 409
                )

        self._erstelle_schritt_falls_fehlt(mangel_id, schritt_nr, benutzer_id)

        self.db.execute(
            text("""
                UPDATE mangelpruefung
                SET ergebnis = :ergebnis, bearbeiter_id = :bearbeiter,
                    abgeschlossen = TRUE, abgeschlossen_am = NOW(),
                    geaendert_am = NOW(), geaendert_von = :bearbeiter
                WHERE vorgang_id = :vid AND schritt = :schritt
            """),
            {"vid": str(mangel_id), "schritt": schritt_nr, "ergebnis": ergebnis, "bearbeiter": benutzer_id},
        )

        # Statuswechsel: Schritt 2 (Mangelschreiben) -> in_bearbeitung, Schritt 5
        # (Bestaetigung Bauherr) -> abgeschlossen
        if schritt_nr == 2:
            self.db.execute(
                text("UPDATE vorgaenge SET status = 'in_bearbeitung', geaendert_am = NOW(), geaendert_von = :ben WHERE id = :id"),
                {"id": str(mangel_id), "ben": benutzer_name},
            )
        elif schritt_nr == 5:
            self.db.execute(
                text("UPDATE vorgaenge SET status = 'abgeschlossen', geaendert_am = NOW(), geaendert_von = :ben WHERE id = :id"),
                {"id": str(mangel_id), "ben": benutzer_name},
            )

        self.db.commit()
        return self.lade_detail(mangel_id)

    # =======================================================================
    # UPDATE — mangelart + Kostenuntergliederung + verlaengerung_monate
    # =======================================================================

    def update(
        self,
        mangel_id: UUID,
        benutzer_name: str,
        mangelart: str | None = None,
        verlaengerung_monate: int | None = None,
        nachtragsfolge_eur: float | None = None,
        folgekosten_betrieb_eur: float | None = None,
        minderkosten_eur: float | None = None,
    ) -> dict[str, Any]:
        m = self.db.execute(
            text("SELECT id FROM vorgaenge WHERE id = :id AND typ = 'mangelanzeige' AND NOT geloescht"),
            {"id": str(mangel_id)},
        ).mappings().first()
        if not m:
            raise MangelError("Mangelanzeige nicht gefunden.", 404)

        # Dynamisches UPDATE: nur uebergebene Felder werden geschrieben.
        # COALESCE waere falsch, weil wir auch explizit auf NULL setzen koennen wollen.
        # Stattdessen: separate SET-Klauseln pro Feld, das im Aufruf gesetzt wurde.
        set_parts: list[str] = []
        params: dict[str, Any] = {"id": str(mangel_id), "ben": benutzer_name}
        if mangelart is not None:
            set_parts.append("mangelart = CAST(:ma AS public.mangelart)")
            params["ma"] = mangelart
        if verlaengerung_monate is not None:
            set_parts.append("verlaengerung_monate = :vm")
            params["vm"] = verlaengerung_monate
        if nachtragsfolge_eur is not None:
            set_parts.append("nachtragsfolge_eur = :nf")
            params["nf"] = nachtragsfolge_eur
        if folgekosten_betrieb_eur is not None:
            set_parts.append("folgekosten_betrieb_eur = :fk")
            params["fk"] = folgekosten_betrieb_eur
        if minderkosten_eur is not None:
            set_parts.append("minderkosten_eur = :mk")
            params["mk"] = minderkosten_eur

        if not set_parts:
            # Nichts zu aendern — direkt Detail zurueck
            return self.lade_detail(mangel_id)

        set_parts.extend(["geaendert_am = NOW()", "geaendert_von = :ben"])
        sql = f"UPDATE vorgaenge SET {', '.join(set_parts)} WHERE id = :id"
        self.db.execute(text(sql), params)
        self.db.commit()
        return self.lade_detail(mangel_id)

    # =======================================================================
    # STATISTIK
    # =======================================================================

    def statistik(self, projekt_kurz: str = "FLI") -> dict[str, Any]:
        projekt = self.db.execute(
            text("SELECT id FROM projekte WHERE kurz = :k AND NOT geloescht"),
            {"k": projekt_kurz},
        ).mappings().first()
        if not projekt:
            raise MangelError(f"Projekt '{projekt_kurz}' nicht gefunden.", 404)

        sum_row = self.db.execute(
            text("""
                SELECT COUNT(*) AS c,
                       COALESCE(SUM(kosten_eur), 0) AS sk,
                       COALESCE(SUM(zeit_arbeitstage), 0) AS sz,
                       COALESCE(SUM(nachtragsfolge_eur), 0) AS snf,
                       COALESCE(SUM(folgekosten_betrieb_eur), 0) AS sfk,
                       COALESCE(SUM(minderkosten_eur), 0) AS smk
                FROM vorgaenge
                WHERE projekt_id = :pid AND typ = 'mangelanzeige' AND NOT geloescht
            """),
            {"pid": projekt["id"]},
        ).mappings().first()

        nach_status = self.db.execute(
            text("""
                SELECT status::text AS s, COUNT(*) AS c,
                       COALESCE(SUM(kosten_eur), 0) AS sk,
                       COALESCE(SUM(zeit_arbeitstage), 0) AS sz
                FROM vorgaenge
                WHERE projekt_id = :pid AND typ = 'mangelanzeige' AND NOT geloescht
                GROUP BY status ORDER BY c DESC
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
                WHERE v.projekt_id = :pid AND v.typ = 'mangelanzeige' AND NOT v.geloescht
                GROUP BY f.id, f.kurz, f.name
                ORDER BY c DESC LIMIT 10
            """),
            {"pid": projekt["id"]},
        ).mappings().all()

        # Mangel-spezifisch: nach mangelart
        nach_mangelart = self.db.execute(
            text("""
                SELECT COALESCE(mangelart::text, 'nicht_zugeordnet') AS s, COUNT(*) AS c,
                       COALESCE(SUM(kosten_eur), 0) AS sk,
                       COALESCE(SUM(zeit_arbeitstage), 0) AS sz
                FROM vorgaenge
                WHERE projekt_id = :pid AND typ = 'mangelanzeige' AND NOT geloescht
                GROUP BY mangelart ORDER BY c DESC
            """),
            {"pid": projekt["id"]},
        ).mappings().all()

        def g(rows):
            return [
                {"schluessel": r["s"], "anzahl": r["c"], "summe_kosten_eur": float(r["sk"]), "summe_zeit_arbeitstage": int(r["sz"] or 0)}
                for r in rows
            ]

        return {
            "gesamt": sum_row["c"],
            "summe_kosten_eur": float(sum_row["sk"]),
            "summe_zeit_arbeitstage": int(sum_row["sz"] or 0),
            "summe_nachtragsfolge_eur": float(sum_row["snf"]),
            "summe_folgekosten_betrieb_eur": float(sum_row["sfk"]),
            "summe_minderkosten_eur": float(sum_row["smk"]),
            "nach_status": g(nach_status),
            "nach_firma": g(nach_firma),
            "nach_mangelart": g(nach_mangelart),
        }

    # =======================================================================
    # INTERN
    # =======================================================================

    def _erstelle_schritt_falls_fehlt(self, mangel_id: UUID, schritt_nr: int, benutzer_id: str) -> None:
        self.db.execute(
            text("""
                INSERT INTO mangelpruefung (vorgang_id, schritt, titel, erstellt_von)
                VALUES (:vid, :schritt, :titel, :ben)
                ON CONFLICT (vorgang_id, schritt) DO NOTHING
            """),
            {
                "vid": str(mangel_id),
                "schritt": schritt_nr,
                "titel": SCHRITT_TITEL.get(schritt_nr, f"Schritt {schritt_nr}"),
                "ben": benutzer_id,
            },
        )
