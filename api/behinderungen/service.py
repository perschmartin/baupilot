"""Behinderungen-Service (AP 2.2a).

Analog zu NachtragsService aufgebaut: lade_liste, lade_detail,
schritt_abschliessen, statistik. Operiert auf vorgaenge (typ='behinderungsanzeige')
und behinderungspruefung (Migration 008).
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Schritt-Titel aus dem Konzept (Migration 008 Doku-Vermerk)
SCHRITT_TITEL = {
    1: "Erfassung",
    2: "Pruefung",
    3: "Anerkennung / Rueckweisung",
    4: "Schriftverkehr",
    5: "Erneute Pruefung",
    6: "Abmeldung GU",
}

# Welche Schritte erfordern PL/Admin-Rolle (Entscheidungs-Schritte)
LEITUNGSSCHRITTE = {3, 6}
LEITUNGSROLLEN = {"projektleiter", "admin"}


class BehinderungError(Exception):
    """Domaenenfehler mit HTTP-Status."""
    def __init__(self, detail: str, status_code: int = 400):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


class BehinderungService:
    """Workflow-Logik fuer Behinderungsanzeigen."""

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
        suche: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Paginierte Liste aller Behinderungsanzeigen eines Projekts."""

        projekt = self.db.execute(
            text("SELECT id FROM projekte WHERE kurz = :k AND NOT geloescht"),
            {"k": projekt_kurz},
        ).mappings().first()
        if not projekt:
            raise BehinderungError(f"Projekt '{projekt_kurz}' nicht gefunden.", 404)

        # Where-Clause dynamisch aufbauen (Status-Filter, Such-Filter)
        where_parts = ["v.projekt_id = :pid", "v.typ = 'behinderungsanzeige'", "NOT v.geloescht"]
        params: dict[str, Any] = {"pid": projekt["id"]}
        if status:
            where_parts.append("v.status = CAST(:status AS vorgangstatus)")
            params["status"] = status
        if suche:
            where_parts.append("(v.nummer ILIKE :suche OR v.gegenstand ILIKE :suche)")
            params["suche"] = f"%{suche}%"
        where_clause = " AND ".join(where_parts)

        # Anzahl
        gesamt = self.db.execute(
            text(f"SELECT COUNT(*) AS c FROM vorgaenge v WHERE {where_clause}"),
            params,
        ).scalar() or 0

        # Daten
        params["limit"] = limit
        params["offset"] = offset
        rows = self.db.execute(
            text(f"""
                SELECT v.id, v.nummer, v.gegenstand, v.beschreibung,
                       v.status::text, v.prioritaet,
                       v.kosten_eur, v.zeit_arbeitstage, v.qualitaet_bewertung,
                       v.verantwortlich_firma_id, v.bauteil_id, v.frist,
                       v.erstellt_am, v.erstellt_von, v.geaendert_am
                FROM vorgaenge v
                WHERE {where_clause}
                ORDER BY v.nummer ASC
                LIMIT :limit OFFSET :offset
            """),
            params,
        ).mappings().all()

        return {"behinderungen": [dict(r) for r in rows], "gesamt": gesamt}

    # =======================================================================
    # DETAIL
    # =======================================================================

    def lade_detail(self, behinderung_id: UUID) -> dict[str, Any]:
        """Behinderungsanzeige mit allen Pruefschritten."""

        row = self.db.execute(
            text("""
                SELECT v.id, v.nummer, v.gegenstand, v.beschreibung,
                       v.status::text, v.prioritaet,
                       v.kosten_eur, v.zeit_arbeitstage, v.qualitaet_bewertung,
                       v.verantwortlich_firma_id, v.bauteil_id, v.frist,
                       v.erstellt_am, v.erstellt_von, v.geaendert_am
                FROM vorgaenge v
                WHERE v.id = :id AND v.typ = 'behinderungsanzeige' AND NOT v.geloescht
            """),
            {"id": str(behinderung_id)},
        ).mappings().first()

        if not row:
            raise BehinderungError("Behinderungsanzeige nicht gefunden.", 404)

        result = dict(row)

        # Pruefschritte laden
        schritte = self.db.execute(
            text("""
                SELECT id, schritt, titel, ergebnis, bearbeiter_id,
                       abgeschlossen, abgeschlossen_am,
                       ki_eingabe, ki_ergebnis, ki_konfidenz,
                       ki_bestaetigt, ki_bestaetigt_von, ki_bestaetigt_am,
                       erstellt_am, erstellt_von
                FROM behinderungspruefung
                WHERE vorgang_id = :vid
                ORDER BY schritt ASC
            """),
            {"vid": str(behinderung_id)},
        ).mappings().all()

        result["pruefschritte"] = [dict(s) for s in schritte]
        # Aktueller Schritt = hoechster abgeschlossener Schritt
        result["aktueller_schritt"] = max((s["schritt"] for s in schritte if s["abgeschlossen"]), default=0)
        return result

    # =======================================================================
    # SCHRITT ABSCHLIESSEN
    # =======================================================================

    def schritt_abschliessen(
        self,
        behinderung_id: UUID,
        schritt_nr: int,
        benutzer_id: str,
        benutzer_name: str,
        ergebnis: str,
        benutzer_rollen: set[str] | None = None,
    ) -> dict[str, Any]:
        """Einen Pruefschritt abschliessen. Sequentielle Erzwingung wie bei Nachtraegen."""

        if not 1 <= schritt_nr <= 6:
            raise BehinderungError("Schritt muss zwischen 1 und 6 liegen.", 400)

        # Existenz pruefen
        beh = self.db.execute(
            text("SELECT id FROM vorgaenge WHERE id = :id AND typ = 'behinderungsanzeige' AND NOT geloescht"),
            {"id": str(behinderung_id)},
        ).mappings().first()
        if not beh:
            raise BehinderungError("Behinderungsanzeige nicht gefunden.", 404)

        # Rollencheck fuer Leitungsschritte (Anerkennung/Rueckweisung, Abmeldung)
        if schritt_nr in LEITUNGSSCHRITTE:
            if benutzer_rollen is not None and not benutzer_rollen.intersection(LEITUNGSROLLEN):
                raise BehinderungError(
                    f"Schritt {schritt_nr} erfordert Rolle 'projektleiter' oder 'admin'.", 403
                )

        # Sequentielle Erzwingung
        if schritt_nr > 1:
            offene = self.db.execute(
                text("""
                    SELECT schritt FROM behinderungspruefung
                    WHERE vorgang_id = :vid AND schritt < :schritt AND NOT abgeschlossen
                    ORDER BY schritt
                """),
                {"vid": str(behinderung_id), "schritt": schritt_nr},
            ).mappings().all()
            if offene:
                fehlende = [str(o["schritt"]) for o in offene]
                raise BehinderungError(
                    f"Schritt(e) {', '.join(fehlende)} muessen zuerst abgeschlossen werden.", 409
                )

        # Schritt anlegen falls nicht vorhanden
        self._erstelle_schritt_falls_fehlt(behinderung_id, schritt_nr, benutzer_id)

        # Aktualisieren
        self.db.execute(
            text("""
                UPDATE behinderungspruefung
                SET ergebnis = :ergebnis,
                    bearbeiter_id = :bearbeiter,
                    abgeschlossen = TRUE,
                    abgeschlossen_am = NOW(),
                    geaendert_am = NOW(),
                    geaendert_von = :bearbeiter
                WHERE vorgang_id = :vid AND schritt = :schritt
            """),
            {
                "vid": str(behinderung_id),
                "schritt": schritt_nr,
                "ergebnis": ergebnis,
                "bearbeiter": benutzer_id,
            },
        )

        # Bei Schritt 3 (Anerkennung/Rueckweisung) und 6 (Abmeldung) Status-Wechsel
        if schritt_nr == 3:
            # Anerkennung → status='in_bearbeitung'; Rueckweisung tragen wir
            # nicht automatisch ein, weil das Ergebnis-Freitext ist. Der Status
            # bleibt damit aussagekraeftig auf 'in_bearbeitung' fuer beide Varianten.
            self.db.execute(
                text("UPDATE vorgaenge SET status = 'in_bearbeitung', geaendert_am = NOW(), geaendert_von = :ben WHERE id = :id"),
                {"id": str(behinderung_id), "ben": benutzer_name},
            )
        elif schritt_nr == 6:
            # Abmeldung GU → status='abgeschlossen'
            self.db.execute(
                text("UPDATE vorgaenge SET status = 'abgeschlossen', geaendert_am = NOW(), geaendert_von = :ben WHERE id = :id"),
                {"id": str(behinderung_id), "ben": benutzer_name},
            )

        self.db.commit()
        return self.lade_detail(behinderung_id)

    # =======================================================================
    # AGGREGATION
    # =======================================================================

    def statistik(self, projekt_kurz: str = "FLI") -> dict[str, Any]:
        """Aggregationsdaten fuer das BehA-Dashboard."""

        projekt = self.db.execute(
            text("SELECT id FROM projekte WHERE kurz = :k AND NOT geloescht"),
            {"k": projekt_kurz},
        ).mappings().first()
        if not projekt:
            raise BehinderungError(f"Projekt '{projekt_kurz}' nicht gefunden.", 404)

        # Gesamtsummen
        sum_row = self.db.execute(
            text("""
                SELECT COUNT(*) AS c,
                       COALESCE(SUM(kosten_eur), 0) AS sk,
                       COALESCE(SUM(zeit_arbeitstage), 0) AS sz
                FROM vorgaenge
                WHERE projekt_id = :pid AND typ = 'behinderungsanzeige' AND NOT geloescht
            """),
            {"pid": projekt["id"]},
        ).mappings().first()

        # Gruppierung nach Status
        nach_status = self.db.execute(
            text("""
                SELECT status::text AS s, COUNT(*) AS c,
                       COALESCE(SUM(kosten_eur), 0) AS sk,
                       COALESCE(SUM(zeit_arbeitstage), 0) AS sz
                FROM vorgaenge
                WHERE projekt_id = :pid AND typ = 'behinderungsanzeige' AND NOT geloescht
                GROUP BY status
                ORDER BY c DESC
            """),
            {"pid": projekt["id"]},
        ).mappings().all()

        # Gruppierung nach verantwortlicher Firma (Top 10)
        nach_firma = self.db.execute(
            text("""
                SELECT COALESCE(f.kurz, f.name, 'Unbekannt') AS s,
                       COUNT(*) AS c,
                       COALESCE(SUM(v.kosten_eur), 0) AS sk,
                       COALESCE(SUM(v.zeit_arbeitstage), 0) AS sz
                FROM vorgaenge v
                LEFT JOIN firmen f ON f.id = v.verantwortlich_firma_id
                WHERE v.projekt_id = :pid AND v.typ = 'behinderungsanzeige' AND NOT v.geloescht
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

    def _erstelle_schritt_falls_fehlt(self, behinderung_id: UUID, schritt_nr: int, benutzer_id: str) -> None:
        """Legt einen Pruefschritt an, falls noch nicht vorhanden (idempotent)."""
        self.db.execute(
            text("""
                INSERT INTO behinderungspruefung (vorgang_id, schritt, titel, erstellt_von)
                VALUES (:vid, :schritt, :titel, :ben)
                ON CONFLICT (vorgang_id, schritt) DO NOTHING
            """),
            {
                "vid": str(behinderung_id),
                "schritt": schritt_nr,
                "titel": SCHRITT_TITEL.get(schritt_nr, f"Schritt {schritt_nr}"),
                "ben": benutzer_id,
            },
        )
