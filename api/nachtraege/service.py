"""
Nachtrags-Service — Geschaeftslogik fuer AP 2.1.

7-Schritte-Workflow:
  1. Erfassung / Import
  2. LV-Abgleich (KI-gestuetzt)
  3. Kostenabgleich (KI-gestuetzt)
  4. Entscheidungsvorlage generieren (KI-gestuetzt)
  5. Pruefung durch Projektleitung
  6. Entscheidung (Variante A/B/C)
  7. Dokumentation / Abschluss

Folgt dem Service-Pattern:
- Einzige Stelle mit DB-Zugriff (text()-SQL)
- Sync-SQLAlchemy
- NachtragsError fuer alle Fehlerfaelle
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class NachtragsError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


# 7-Schritte-Titel (deutsch)
PRUEFSCHRITT_TITEL = {
    1: "Erfassung",
    2: "LV-Abgleich",
    3: "Kostenabgleich",
    4: "Entscheidungsvorlage",
    5: "Pruefung Projektleitung",
    6: "Entscheidung",
    7: "Dokumentation / Abschluss",
}

# Rollen fuer Schritte 5-7
LEITUNGSSCHRITTE = {5, 6, 7}
LEITUNGSROLLEN = {"projektleiter", "admin"}


class NachtragsService:

    def __init__(self, db: Session, mandant_slug: str = ""):
        self.db = db
        self.mandant_slug = mandant_slug

    def _commit(self):
        """Commit mit search_path-Wiederherstellung."""
        self.db.commit()
        if self.mandant_slug:
            self.db.execute(
                text(f"SET search_path TO tenant_{self.mandant_slug}, shared, public")
            )

    def _pruefe_rolle(self, benutzer_id: str, erlaubte_rollen: set[str]) -> bool:
        """Prueft ob der Benutzer eine der erlaubten Rollen hat."""
        result = self.db.execute(
            text("SELECT rolle FROM shared.benutzer_projekt_rollen WHERE benutzer_id = :bid"),
            {"bid": benutzer_id},
        )
        rollen = {r[0] for r in result.all()}
        return bool(rollen.intersection(erlaubte_rollen))

    # ==================================================================
    # NACHTRAEGE AUFLISTEN
    # ==================================================================

    def liste_nachtraege(
        self,
        projekt_kurz: str,
        status: str | None = None,
        lv_id: UUID | None = None,
        kostengruppe: str | None = None,
        suche: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Nachtraege eines Projekts auflisten mit Filtern."""

        projekt = self.db.execute(
            text("SELECT id FROM projekte WHERE kurz = :kurz AND NOT geloescht"),
            {"kurz": projekt_kurz},
        ).mappings().first()

        if not projekt:
            raise NachtragsError(f"Projekt '{projekt_kurz}' nicht gefunden.", 404)

        where_parts = ["v.projekt_id = :pid", "v.typ = 'nachtrag'", "NOT v.geloescht"]
        params: dict[str, Any] = {"pid": projekt["id"]}

        if status:
            where_parts.append("v.status = CAST(:status AS vorgangstatus)")
            params["status"] = status
        if lv_id:
            where_parts.append("v.lv_id = :lv_id")
            params["lv_id"] = str(lv_id)
        if kostengruppe:
            where_parts.append("v.kostengruppe_din276 = :kg")
            params["kg"] = kostengruppe
        if suche:
            where_parts.append("(v.nummer ILIKE :suche OR v.gegenstand ILIKE :suche)")
            params["suche"] = f"%{suche}%"

        where_clause = " AND ".join(where_parts)

        # Zaehlen + Summen
        agg = self.db.execute(
            text(f"""
                SELECT COUNT(*) AS c,
                       COALESCE(SUM(v.betrag_gefordert), 0) AS summe_gefordert,
                       COALESCE(SUM(v.betrag_genehmigt), 0) AS summe_genehmigt
                FROM vorgaenge v
                WHERE {where_clause}
            """),
            params,
        ).mappings().first()

        # Daten
        params["limit"] = limit
        params["offset"] = offset

        rows = self.db.execute(
            text(f"""
                SELECT v.id, v.nummer, v.gegenstand, v.beschreibung,
                       v.status::text, v.prioritaet,
                       v.betrag_gefordert, v.betrag_geprueft, v.betrag_genehmigt,
                       v.zeitauswirkung_tage, v.nachtragsvariante,
                       v.qualitaetsauswirkung, v.lv_id, v.kostengruppe_din276,
                       v.ntv_id, v.verantwortlich_firma_id,
                       v.erstellt_am, v.erstellt_von, v.geaendert_am
                FROM vorgaenge v
                WHERE {where_clause}
                ORDER BY v.nummer ASC
                LIMIT :limit OFFSET :offset
            """),
            params,
        ).mappings().all()

        return {
            "nachtraege": [dict(r) for r in rows],
            "gesamt": agg["c"],
            "summe_gefordert": float(agg["summe_gefordert"]),
            "summe_genehmigt": float(agg["summe_genehmigt"]),
        }

    # ==================================================================
    # NACHTRAG DETAIL (mit Pruefschritten)
    # ==================================================================

    def lade_nachtrag(self, nachtrag_id: UUID) -> dict[str, Any]:
        """Nachtrag mit 7-Schritte-Workflow laden."""

        row = self.db.execute(
            text("""
                SELECT v.id, v.nummer, v.gegenstand, v.beschreibung,
                       v.status::text, v.prioritaet,
                       v.betrag_gefordert, v.betrag_geprueft, v.betrag_genehmigt,
                       v.zeitauswirkung_tage, v.nachtragsvariante,
                       v.qualitaetsauswirkung, v.lv_id, v.kostengruppe_din276,
                       v.ntv_id, v.verantwortlich_firma_id,
                       v.erstellt_am, v.erstellt_von, v.geaendert_am
                FROM vorgaenge v
                WHERE v.id = :id AND v.typ = 'nachtrag' AND NOT v.geloescht
            """),
            {"id": str(nachtrag_id)},
        ).mappings().first()

        if not row:
            raise NachtragsError("Nachtrag nicht gefunden.", 404)

        result = dict(row)

        # Pruefschritte laden
        # NT-F-04: entscheidung_grund/hoehe + begruendungen werden aus Migration 008
        # mitgeladen — relevant ist Schritt 6 (Entscheidung).
        schritte = self.db.execute(
            text("""
                SELECT id, schritt, titel, ergebnis, bearbeiter_id,
                       abgeschlossen, abgeschlossen_am,
                       ki_eingabe, ki_ergebnis, ki_konfidenz,
                       ki_bestaetigt, ki_bestaetigt_von, ki_bestaetigt_am,
                       entscheidung_grund, entscheidung_hoehe,
                       begruendung_grund, begruendung_hoehe,
                       erstellt_am, erstellt_von
                FROM nachtragspruefung
                WHERE vorgang_id = :vid
                ORDER BY schritt ASC
            """),
            {"vid": str(nachtrag_id)},
        ).mappings().all()

        result["pruefschritte"] = [dict(s) for s in schritte]

        # Aktuellen Schritt ermitteln
        aktuell = 0
        for s in schritte:
            if s["abgeschlossen"]:
                aktuell = s["schritt"]
        result["aktueller_schritt"] = aktuell

        return result

    # ==================================================================
    # NACHTRAG ERSTELLEN
    # ==================================================================

    def erstelle_nachtrag(
        self,
        projekt_kurz: str,
        gegenstand: str,
        erstellt_von_id: UUID,
        erstellt_von_name: str,
        **felder,
    ) -> dict[str, Any]:
        """Neuen Nachtrag anlegen mit Schritt-1-Eintrag."""

        projekt = self.db.execute(
            text("SELECT id FROM projekte WHERE kurz = :kurz AND NOT geloescht"),
            {"kurz": projekt_kurz},
        ).mappings().first()

        if not projekt:
            raise NachtragsError(f"Projekt '{projekt_kurz}' nicht gefunden.", 404)

        # Naechste NT-Nummer
        result = self.db.execute(
            text("""
                SELECT COALESCE(MAX(
                    CAST(SUBSTRING(nummer FROM 4) AS INTEGER)
                ), 0) + 1 AS naechste
                FROM vorgaenge
                WHERE projekt_id = :pid AND typ = 'nachtrag' AND NOT geloescht
            """),
            {"pid": projekt["id"]},
        ).mappings().first()

        nummer = f"NT-{result['naechste']:03d}"

        # Einfuegen
        row = self.db.execute(
            text("""
                INSERT INTO vorgaenge (
                    projekt_id, typ, nummer, gegenstand, beschreibung, status,
                    betrag_gefordert, zeitauswirkung_tage, qualitaetsauswirkung,
                    lv_id, kostengruppe_din276, verantwortlich_firma_id,
                    erstellt_von
                ) VALUES (
                    :pid, 'nachtrag', :nummer, :gegenstand, :beschreibung, 'offen',
                    :betrag_gefordert, :zeitauswirkung_tage, :qualitaetsauswirkung,
                    :lv_id, :kostengruppe, :firma_id,
                    :erstellt_von
                )
                RETURNING id, nummer, gegenstand, status::text, erstellt_am
            """),
            {
                "pid": projekt["id"],
                "nummer": nummer,
                "gegenstand": gegenstand,
                "beschreibung": felder.get("beschreibung"),
                "betrag_gefordert": felder.get("betrag_gefordert"),
                "zeitauswirkung_tage": felder.get("zeitauswirkung_tage"),
                "qualitaetsauswirkung": felder.get("qualitaetsauswirkung"),
                "lv_id": str(felder["lv_id"]) if felder.get("lv_id") else None,
                "kostengruppe": felder.get("kostengruppe_din276"),
                "firma_id": str(felder["verantwortlich_firma_id"]) if felder.get("verantwortlich_firma_id") else None,
                "erstellt_von": erstellt_von_name,
            },
        ).mappings().first()

        vorgang_id = row["id"]

        # Schritt 1 automatisch anlegen
        self._erstelle_pruefschritt(vorgang_id, 1, str(erstellt_von_id), "Manuell erfasst")

        self._commit()

        return dict(row)

    # ==================================================================
    # NACHTRAG AKTUALISIEREN
    # ==================================================================

    def aktualisiere_nachtrag(
        self,
        nachtrag_id: UUID,
        benutzer_id: UUID,
        benutzer_name: str,
        **felder,
    ) -> dict[str, Any]:
        """Nachtrags-Felder aktualisieren."""

        current = self.db.execute(
            text("""
                SELECT id, status, typ FROM vorgaenge
                WHERE id = :id AND typ = 'nachtrag' AND NOT geloescht
            """),
            {"id": str(nachtrag_id)},
        ).mappings().first()

        if not current:
            raise NachtragsError("Nachtrag nicht gefunden.", 404)

        set_parts = ["geaendert_am = NOW()", "geaendert_von = :benutzer_name"]
        params: dict[str, Any] = {
            "id": str(nachtrag_id),
            "benutzer_name": benutzer_name,
        }

        feld_mapping = {
            "gegenstand": "gegenstand",
            "beschreibung": "beschreibung",
            "betrag_gefordert": "betrag_gefordert",
            "betrag_geprueft": "betrag_geprueft",
            "betrag_genehmigt": "betrag_genehmigt",
            "zeitauswirkung_tage": "zeitauswirkung_tage",
            "qualitaetsauswirkung": "qualitaetsauswirkung",
            "nachtragsvariante": "nachtragsvariante",
            "kostengruppe_din276": "kostengruppe_din276",
        }

        for key, col in feld_mapping.items():
            if key in felder and felder[key] is not None:
                set_parts.append(f"{col} = :{key}")
                params[key] = felder[key]

        # UUID-Felder separat
        for key in ("lv_id", "verantwortlich_firma_id"):
            if key in felder and felder[key] is not None:
                set_parts.append(f"{key} = :{key}")
                params[key] = str(felder[key])

        set_clause = ", ".join(set_parts)

        self.db.execute(
            text(f"UPDATE vorgaenge SET {set_clause} WHERE id = :id"),
            params,
        )
        self._commit()

        return self.lade_nachtrag(nachtrag_id)

    # ==================================================================
    # PRUEFSCHRITTE
    # ==================================================================

    def _erstelle_pruefschritt(
        self,
        vorgang_id: UUID,
        schritt: int,
        erstellt_von_id: str,
        ergebnis: str | None = None,
    ) -> dict[str, Any]:
        """Einen Pruefschritt anlegen."""

        titel = PRUEFSCHRITT_TITEL.get(schritt, f"Schritt {schritt}")

        row = self.db.execute(
            text("""
                INSERT INTO nachtragspruefung (
                    vorgang_id, schritt, titel, ergebnis,
                    bearbeiter_id, abgeschlossen, abgeschlossen_am,
                    erstellt_von
                ) VALUES (
                    :vid, :schritt, :titel, :ergebnis,
                    :bearbeiter, :abgeschlossen, :abgeschlossen_am,
                    :erstellt_von
                )
                ON CONFLICT (vorgang_id, schritt) DO NOTHING
                RETURNING id, schritt, titel, ergebnis, abgeschlossen, erstellt_am, erstellt_von
            """),
            {
                "vid": str(vorgang_id),
                "schritt": schritt,
                "titel": titel,
                "ergebnis": ergebnis,
                "bearbeiter": erstellt_von_id,
                "abgeschlossen": ergebnis is not None,
                "abgeschlossen_am": datetime.now(timezone.utc) if ergebnis else None,
                "erstellt_von": erstellt_von_id,
            },
        ).mappings().first()

        return dict(row) if row else {}

    def schritt_abschliessen(
        self,
        nachtrag_id: UUID,
        schritt_nr: int,
        benutzer_id: str,
        benutzer_name: str,
        ergebnis: str,
        benutzer_rollen: set[str] | None = None,
    ) -> dict[str, Any]:
        """Einen Pruefschritt manuell abschliessen. Sequentielle Erzwingung."""

        # Pruefen ob Nachtrag existiert
        nachtrag = self.db.execute(
            text("""
                SELECT id FROM vorgaenge
                WHERE id = :id AND typ = 'nachtrag' AND NOT geloescht
            """),
            {"id": str(nachtrag_id)},
        ).mappings().first()

        if not nachtrag:
            raise NachtragsError("Nachtrag nicht gefunden.", 404)

        # Rollencheck fuer Leitungsschritte
        if schritt_nr in LEITUNGSSCHRITTE:
            if benutzer_rollen and not benutzer_rollen.intersection(LEITUNGSROLLEN):
                raise NachtragsError(
                    f"Schritt {schritt_nr} erfordert Rolle 'projektleiter' oder 'admin'.", 403
                )

        # Sequentielle Erzwingung: Alle vorherigen Schritte muessen abgeschlossen sein
        if schritt_nr > 1:
            offene = self.db.execute(
                text("""
                    SELECT schritt FROM nachtragspruefung
                    WHERE vorgang_id = :vid AND schritt < :schritt AND NOT abgeschlossen
                    ORDER BY schritt
                """),
                {"vid": str(nachtrag_id), "schritt": schritt_nr},
            ).mappings().all()

            if offene:
                fehlende = [str(o["schritt"]) for o in offene]
                raise NachtragsError(
                    f"Schritt(e) {', '.join(fehlende)} muessen zuerst abgeschlossen werden.", 409
                )

        # Schritt anlegen falls nicht vorhanden, dann aktualisieren
        self._erstelle_pruefschritt(nachtrag_id, schritt_nr, benutzer_id)

        self.db.execute(
            text("""
                UPDATE nachtragspruefung
                SET ergebnis = :ergebnis,
                    bearbeiter_id = :bearbeiter,
                    abgeschlossen = TRUE,
                    abgeschlossen_am = NOW(),
                    geaendert_am = NOW(),
                    geaendert_von = :bearbeiter
                WHERE vorgang_id = :vid AND schritt = :schritt
            """),
            {
                "vid": str(nachtrag_id),
                "schritt": schritt_nr,
                "ergebnis": ergebnis,
                "bearbeiter": benutzer_id,
            },
        )

        self._commit()

        return self.lade_nachtrag(nachtrag_id)

    def ki_ergebnis_speichern(
        self,
        nachtrag_id: UUID,
        schritt_nr: int,
        benutzer_id: str,
        ki_eingabe: Any,
        ki_ergebnis: Any,
        ki_konfidenz: float | None = None,
    ) -> dict[str, Any]:
        """KI-Ergebnis an einem Pruefschritt speichern (Schritt 2, 3, 4)."""

        if schritt_nr not in (2, 3, 4):
            raise NachtragsError("KI-Ergebnisse nur fuer Schritte 2-4.", 400)

        # Schritt anlegen falls noetig
        self._erstelle_pruefschritt(nachtrag_id, schritt_nr, benutzer_id)

        import json
        self.db.execute(
            text("""
                UPDATE nachtragspruefung
                SET ki_eingabe = CAST(:eingabe AS jsonb),
                    ki_ergebnis = CAST(:ergebnis AS jsonb),
                    ki_konfidenz = :konfidenz,
                    geaendert_am = NOW(),
                    geaendert_von = :bearbeiter
                WHERE vorgang_id = :vid AND schritt = :schritt
            """),
            {
                "vid": str(nachtrag_id),
                "schritt": schritt_nr,
                "eingabe": json.dumps(ki_eingabe, ensure_ascii=False, default=str),
                "ergebnis": json.dumps(ki_ergebnis, ensure_ascii=False, default=str),
                "konfidenz": ki_konfidenz,
                "bearbeiter": benutzer_id,
            },
        )
        self._commit()
        return self.lade_nachtrag(nachtrag_id)

    def ki_bestaetigen(
        self,
        nachtrag_id: UUID,
        schritt_nr: int,
        benutzer_id: str,
        bestaetigt: bool,
        kommentar: str | None = None,
    ) -> dict[str, Any]:
        """KI-Ergebnis bestaetigen oder ablehnen (menschliches Gate, B-002)."""

        if schritt_nr not in (2, 3, 4):
            raise NachtragsError("KI-Bestaetigung nur fuer Schritte 2-4.", 400)

        schritt = self.db.execute(
            text("""
                SELECT ki_ergebnis FROM nachtragspruefung
                WHERE vorgang_id = :vid AND schritt = :schritt
            """),
            {"vid": str(nachtrag_id), "schritt": schritt_nr},
        ).mappings().first()

        if not schritt or not schritt["ki_ergebnis"]:
            raise NachtragsError("Kein KI-Ergebnis zum Bestaetigen vorhanden.", 409)

        # Bestaetigung speichern
        self.db.execute(
            text("""
                UPDATE nachtragspruefung
                SET ki_bestaetigt = :bestaetigt,
                    ki_bestaetigt_von = :von,
                    ki_bestaetigt_am = NOW(),
                    ergebnis = CASE WHEN :bestaetigt THEN
                        COALESCE(ergebnis, '') || CASE WHEN ergebnis IS NOT NULL THEN E'\n' ELSE '' END
                        || 'KI-Ergebnis bestaetigt' || COALESCE(': ' || :kommentar, '')
                    ELSE
                        COALESCE(ergebnis, '') || CASE WHEN ergebnis IS NOT NULL THEN E'\n' ELSE '' END
                        || 'KI-Ergebnis abgelehnt' || COALESCE(': ' || :kommentar, '')
                    END,
                    abgeschlossen = :bestaetigt,
                    abgeschlossen_am = CASE WHEN :bestaetigt THEN NOW() ELSE NULL END,
                    geaendert_am = NOW(),
                    geaendert_von = :von
                WHERE vorgang_id = :vid AND schritt = :schritt
            """),
            {
                "vid": str(nachtrag_id),
                "schritt": schritt_nr,
                "bestaetigt": bestaetigt,
                "von": benutzer_id,
                "kommentar": kommentar,
            },
        )
        self._commit()

        return self.lade_nachtrag(nachtrag_id)

    # ==================================================================
    # VARIANTEN-LOGIK (Schritt 6)
    # ==================================================================

    def entscheidung_treffen(
        self,
        nachtrag_id: UUID,
        variante: str,
        benutzer_id: str,
        benutzer_name: str,
        betrag_genehmigt: float | None = None,
        kommentar: str | None = None,
        begruendung_grund: str | None = None,
        begruendung_hoehe: str | None = None,
    ) -> dict[str, Any]:
        """Entscheidung treffen: Variante A (genehmigt), B (teilweise), C (abgelehnt).

        NT-F-04: Die Variante mappt auf zwei getrennte BOOL-Felder
        entscheidung_grund / entscheidung_hoehe in der nachtragspruefung
        (Migration 008). Die Begruendungen werden vom Bearbeitenden frei
        eingegeben und sind beide optional, aber empfohlen — sie sind die
        Grundlage fuer das Protokoll (AP 2.5) und fuer die Beweisfuehrung.

        VOB/B-Mapping:
          Variante A: grund=TRUE,  hoehe=TRUE  (vollstaendig genehmigt)
          Variante B: grund=TRUE,  hoehe=FALSE (Grund ja, Hoehe strittig)
          Variante C: grund=FALSE, hoehe=NULL  (Anspruch dem Grunde nach abgelehnt)
        """

        if variante not in ("A", "B", "C"):
            raise NachtragsError("Variante muss A, B oder C sein.", 400)

        nachtrag = self.lade_nachtrag(nachtrag_id)

        # Schritte 1-5 muessen abgeschlossen sein
        abgeschlossene = {s["schritt"] for s in nachtrag["pruefschritte"] if s["abgeschlossen"]}
        fehlende = set(range(1, 6)) - abgeschlossene
        if fehlende:
            raise NachtragsError(
                f"Schritte {', '.join(str(s) for s in sorted(fehlende))} muessen zuerst abgeschlossen werden.", 409
            )

        # Variante speichern
        update_params: dict[str, Any] = {
            "id": str(nachtrag_id),
            "variante": variante,
            "benutzer": benutzer_name,
        }

        if variante == "A":
            # Vollstaendig genehmigt → Betrag = gefordert
            genehmigt = betrag_genehmigt or nachtrag.get("betrag_gefordert") or 0
            update_params["betrag"] = genehmigt
            self.db.execute(
                text("""
                    UPDATE vorgaenge SET
                        nachtragsvariante = :variante,
                        betrag_genehmigt = :betrag,
                        status = 'abgeschlossen',
                        geaendert_am = NOW(), geaendert_von = :benutzer
                    WHERE id = :id
                """),
                update_params,
            )

            # NTV-Vorgang automatisch anlegen (F-104)
            self._erstelle_ntv_vorgang(nachtrag_id, benutzer_name)

        elif variante == "B":
            # Teilweise genehmigt
            if betrag_genehmigt is None:
                raise NachtragsError("Variante B erfordert betrag_genehmigt.", 400)
            update_params["betrag"] = betrag_genehmigt
            self.db.execute(
                text("""
                    UPDATE vorgaenge SET
                        nachtragsvariante = :variante,
                        betrag_genehmigt = :betrag,
                        status = 'abgeschlossen',
                        geaendert_am = NOW(), geaendert_von = :benutzer
                    WHERE id = :id
                """),
                update_params,
            )

        elif variante == "C":
            # Abgelehnt
            self.db.execute(
                text("""
                    UPDATE vorgaenge SET
                        nachtragsvariante = :variante,
                        betrag_genehmigt = 0,
                        status = 'storniert',
                        geaendert_am = NOW(), geaendert_von = :benutzer
                    WHERE id = :id
                """),
                update_params,
            )

        # Schritt 6 abschliessen
        ergebnis_text = f"Variante {variante}"
        if kommentar:
            ergebnis_text += f": {kommentar}"
        self.schritt_abschliessen(
            nachtrag_id, 6, benutzer_id, benutzer_name, ergebnis_text,
            benutzer_rollen=LEITUNGSROLLEN,
        )

        # NT-F-04: Getrennte Entscheidung Grund/Hoehe in nachtragspruefung speichern.
        # Variante -> BOOL-Mapping wie im VOB/B-Praxismodell (siehe Docstring oben).
        variante_grund_map = {"A": True,  "B": True,  "C": False}
        variante_hoehe_map = {"A": True,  "B": False, "C": None}
        self.db.execute(
            text("""
                UPDATE nachtragspruefung SET
                    entscheidung_grund = :grund,
                    entscheidung_hoehe = :hoehe,
                    begruendung_grund  = :bg_grund,
                    begruendung_hoehe  = :bg_hoehe,
                    geaendert_am = NOW(),
                    geaendert_von = :benutzer_id
                WHERE vorgang_id = :id AND schritt = 6
            """),
            {
                "id": str(nachtrag_id),
                "grund": variante_grund_map[variante],
                "hoehe": variante_hoehe_map[variante],
                "bg_grund": begruendung_grund,
                "bg_hoehe": begruendung_hoehe,
                "benutzer_id": benutzer_id,
            },
        )
        self.db.commit()

        return self.lade_nachtrag(nachtrag_id)

    def _erstelle_ntv_vorgang(self, nachtrag_id: UUID, erstellt_von: str):
        """Bei Variante A: NTV-Vorgang automatisch anlegen und verknuepfen (F-104)."""

        nachtrag = self.db.execute(
            text("SELECT id, projekt_id, nummer, gegenstand FROM vorgaenge WHERE id = :id"),
            {"id": str(nachtrag_id)},
        ).mappings().first()

        if not nachtrag:
            return

        ntv_nummer = nachtrag["nummer"].replace("NT-", "NTV-")

        ntv = self.db.execute(
            text("""
                INSERT INTO vorgaenge (
                    projekt_id, typ, nummer, gegenstand, status, erstellt_von
                ) VALUES (
                    :pid, 'nachtrag', :nummer,
                    :gegenstand,
                    'offen', :erstellt_von
                )
                RETURNING id
            """),
            {
                "pid": nachtrag["projekt_id"],
                "nummer": ntv_nummer,
                "gegenstand": f"NTV zu {nachtrag['nummer']}: {nachtrag['gegenstand']}",
                "erstellt_von": erstellt_von,
            },
        ).mappings().first()

        if ntv:
            self.db.execute(
                text("UPDATE vorgaenge SET ntv_id = :ntv WHERE id = :id"),
                {"ntv": ntv["id"], "id": str(nachtrag_id)},
            )
