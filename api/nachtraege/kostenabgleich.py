"""
Kostenabgleich — Preisvergleich gegen LV-Positionen und BKI-Baupreise (Schritt 3).

Vergleicht den geforderten Betrag eines Nachtrags gegen:
  1. Eigene LV-Einheitspreise (exakte Treffer aus Schritt 2)
  2. BKI-Baupreise (regionalisiert mit Faktor fuer Jena: 1,088)

Bewertung:
  - "angemessen": Innerhalb BKI-Bandbreite (von–bis)
  - "ueber_bandbreite": Ueber BKI-bis
  - "unter_bandbreite": Unter BKI-von
  - "kein_vergleich": Keine Referenzpreise gefunden
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Regionalfaktor Standard (wird aus DB geladen)
DEFAULT_REGIONALFAKTOR = 1.088


class KostenabgleichService:
    """Vergleicht Nachtragskosten gegen LV- und BKI-Referenzpreise."""

    def __init__(self, db: Session, mandant_slug: str = ""):
        self.db = db
        self.mandant_slug = mandant_slug

    def abgleich(
        self,
        vorgang_id: UUID,
        lv_treffer: list[dict[str, Any]] | None = None,
        regionalfaktor_landkreis: str = "Jena, Stadt",
    ) -> dict[str, Any]:
        """
        Kostenabgleich durchfuehren.
        Erwartet optional die LV-Treffer aus Schritt 2.
        """

        # Vorgang laden
        vorgang = self.db.execute(
            text("""
                SELECT id, betrag_gefordert, gegenstand, kostengruppe_din276
                FROM vorgaenge WHERE id = :id AND NOT geloescht
            """),
            {"id": str(vorgang_id)},
        ).mappings().first()

        if not vorgang:
            return {
                "vorgang_id": vorgang_id,
                "betrag_gefordert": None,
                "vergleiche": [],
                "bki_regionalfaktor": None,
                "gesamtbewertung": "kein_vergleich",
            }

        betrag = float(vorgang["betrag_gefordert"]) if vorgang["betrag_gefordert"] else None

        # Regionalfaktor aus DB laden
        regionalfaktor = self._lade_regionalfaktor(regionalfaktor_landkreis)

        vergleiche: list[dict[str, Any]] = []

        # 1. LV-Vergleich (aus uebergebenen Treffern)
        if lv_treffer:
            for t in lv_treffer[:5]:
                ep = t.get("einheitspreis")
                if ep and ep > 0:
                    abw = ((betrag / ep) - 1) * 100 if betrag and ep else None
                    vergleiche.append({
                        "quelle": f"LV {t.get('lv_nummer', '?')}",
                        "bezeichnung": t.get("kurztext", ""),
                        "einheit": t.get("einheit"),
                        "referenzpreis_netto": float(ep),
                        "referenzpreis_regionalisiert": None,
                        "abweichung_prozent": round(abw, 1) if abw is not None else None,
                        "bewertung": self._bewerte_abweichung(abw),
                    })

        # 2. BKI-Vergleich
        bki_treffer = self._bki_suche(vorgang["gegenstand"], vorgang.get("kostengruppe_din276"))
        for b in bki_treffer[:5]:
            regionalisiert = float(b["preis_mittel_netto"]) * regionalfaktor
            von_reg = float(b["preis_von_netto"]) * regionalfaktor
            bis_reg = float(b["preis_bis_netto"]) * regionalfaktor

            if betrag:
                abw = ((betrag / regionalisiert) - 1) * 100 if regionalisiert > 0 else None
                # Innerhalb Bandbreite?
                if von_reg <= betrag <= bis_reg:
                    bewertung = "angemessen"
                elif betrag > bis_reg:
                    bewertung = "ueber_bandbreite"
                elif betrag < von_reg:
                    bewertung = "unter_bandbreite"
                else:
                    bewertung = "unbekannt"
            else:
                abw = None
                bewertung = "kein_vergleich"

            vergleiche.append({
                "quelle": f"BKI {b['preis_jahr']} LB {b['leistungsbereich']}",
                "bezeichnung": b["kurztext"],
                "einheit": b.get("einheit"),
                "referenzpreis_netto": float(b["preis_mittel_netto"]),
                "referenzpreis_regionalisiert": round(regionalisiert, 2),
                "abweichung_prozent": round(abw, 1) if abw is not None else None,
                "bewertung": bewertung,
            })

        # Gesamtbewertung
        bewertungen = [v["bewertung"] for v in vergleiche if v["bewertung"] != "kein_vergleich"]
        if not bewertungen:
            gesamt = "kein_vergleich"
        elif all(b == "angemessen" for b in bewertungen):
            gesamt = "angemessen"
        elif any(b == "ueber_bandbreite" for b in bewertungen):
            gesamt = "ueber_bandbreite"
        else:
            gesamt = "gemischt"

        return {
            "vorgang_id": vorgang_id,
            "betrag_gefordert": betrag,
            "vergleiche": vergleiche,
            "bki_regionalfaktor": regionalfaktor,
            "gesamtbewertung": gesamt,
        }

    def _lade_regionalfaktor(self, landkreis: str) -> float:
        """Regionalfaktor aus DB laden, Fallback auf DEFAULT."""
        row = self.db.execute(
            text("""
                SELECT faktor FROM shared.bki_regionalfaktoren
                WHERE landkreis = :lk
                ORDER BY preis_jahr DESC
                LIMIT 1
            """),
            {"lk": landkreis},
        ).mappings().first()

        return float(row["faktor"]) if row else DEFAULT_REGIONALFAKTOR

    def _bki_suche(
        self,
        suchbegriff: str,
        kostengruppe: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """BKI-Positionen per Volltextsuche finden."""

        woerter = [w.strip() for w in suchbegriff.split() if w.strip() and len(w.strip()) > 2]
        if not woerter:
            return []

        ts_query = " & ".join(f"{w}:*" for w in woerter[:5])

        where_parts = [
            "to_tsvector('german', kurztext || ' ' || COALESCE(stichworte, '')) @@ to_tsquery('german', :query)"
        ]
        params: dict[str, Any] = {"query": ts_query, "limit": limit}

        if kostengruppe:
            where_parts.append("kostengruppe = :kg")
            params["kg"] = kostengruppe

        where = " AND ".join(where_parts)

        rows = self.db.execute(
            text(f"""
                SELECT leistungsbereich, position_nr, kurztext, einheit,
                       kostengruppe, preis_mittel_netto, preis_von_netto,
                       preis_bis_netto, preis_min_netto, preis_max_netto,
                       preis_jahr
                FROM shared.bki_baupreise
                WHERE {where}
                ORDER BY preis_jahr DESC,
                    ts_rank(
                        to_tsvector('german', kurztext || ' ' || COALESCE(stichworte, '')),
                        to_tsquery('german', :query)
                    ) DESC
                LIMIT :limit
            """),
            params,
        ).mappings().all()

        return [dict(r) for r in rows]

    @staticmethod
    def _bewerte_abweichung(abweichung_prozent: float | None) -> str:
        """Abweichung bewerten."""
        if abweichung_prozent is None:
            return "kein_vergleich"
        if -10 <= abweichung_prozent <= 10:
            return "angemessen"
        if abweichung_prozent > 10:
            return "ueber_bandbreite"
        return "unter_bandbreite"
