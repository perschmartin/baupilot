"""
LV-Abgleich — Semantische und exakte Suche gegen LV-Positionen (Schritt 2).

Zwei Methoden:
  1. Exakte Suche: PostgreSQL Volltextsuche (to_tsvector/to_tsquery)
  2. Semantische Suche: Qdrant-Embedding (wenn Embeddings vorhanden)

B-002: LLM-Vorschlaege erfordern menschliche Bestaetigung.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class LVAbgleichService:
    """Vergleicht einen Nachtrag gegen die LV-Positionen."""

    def __init__(self, db: Session, mandant_slug: str = ""):
        self.db = db
        self.mandant_slug = mandant_slug

    def abgleich(
        self,
        vorgang_id: UUID,
        suchbegriff: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """
        LV-Abgleich durchfuehren.
        Wenn kein Suchbegriff angegeben, wird der Gegenstand des Vorgangs verwendet.
        """

        # Vorgang laden
        vorgang = self.db.execute(
            text("""
                SELECT id, gegenstand, beschreibung, lv_id
                FROM vorgaenge WHERE id = :id AND NOT geloescht
            """),
            {"id": str(vorgang_id)},
        ).mappings().first()

        if not vorgang:
            return {"vorgang_id": vorgang_id, "treffer": [], "anzahl_treffer": 0, "suchbegriff": ""}

        such = suchbegriff or vorgang["gegenstand"] or ""

        if not such.strip():
            return {"vorgang_id": vorgang_id, "treffer": [], "anzahl_treffer": 0, "suchbegriff": ""}

        treffer = self._exakte_suche(such, vorgang.get("lv_id"), limit)

        # NT-F-02 Doppelbeauftragungspruefung: pro Treffer alle bereits
        # genehmigten anderen Nachtraege an derselben LV-Position nachladen.
        # Wird als Liste in jedem Treffer-Dict unter 'bereits_genehmigte_nts'
        # zurueckgegeben. Leere Liste = keine Konfliktwarnung im Frontend.
        if treffer:
            self._angereichern_mit_genehmigten_nts(treffer, vorgang_id)

        return {
            "vorgang_id": vorgang_id,
            "treffer": treffer,
            "anzahl_treffer": len(treffer),
            "suchbegriff": such,
        }

    def _angereichern_mit_genehmigten_nts(
        self,
        treffer: list[dict[str, Any]],
        aktueller_vorgang_id: UUID,
    ) -> None:
        """NT-F-02: Pro Treffer ermitteln, ob es bereits genehmigte Nachtraege
        an genau derselben LV-Position gibt.

        Quelle: nachtragspruefung.ki_ergebnis.treffer[].lv_position_id mit
        ki_bestaetigt=TRUE (Bestaetigungs-Gate aus B-002). Der aktuelle Vorgang
        wird ausgeschlossen, damit ein NT sich nicht selbst als „bereits
        genehmigt" meldet.

        Mutiert die uebergebene treffer-Liste in-place. Effizient als
        Batch-Query mit einem CROSS JOIN LATERAL gegen jsonb_array_elements.
        """
        if not treffer:
            return

        # Alle gefundenen LV-Position-IDs sammeln (als Strings, weil JSON
        # die UUIDs als Text-Werte abspeichert).
        pos_ids = [str(t["lv_position_id"]) for t in treffer]

        # Batch-Query: alle Zuordnungen NT -> LV-Position aus dem Pruefschritt 2,
        # die bestaetigt UND fuer einen genehmigten Vorgang sind.
        rows = self.db.execute(
            text("""
                SELECT
                    (t.elem ->> 'lv_position_id')::uuid AS lv_position_id,
                    v.id AS vorgang_id,
                    v.nummer AS nummer,
                    v.betrag_genehmigt AS betrag_genehmigt,
                    v.status::text AS status
                FROM nachtragspruefung np
                JOIN vorgaenge v ON v.id = np.vorgang_id
                CROSS JOIN LATERAL jsonb_array_elements(np.ki_ergebnis -> 'treffer') AS t(elem)
                WHERE np.schritt = 2
                  AND np.ki_bestaetigt = TRUE
                  AND v.status = 'genehmigt'
                  AND v.id <> :aktueller_vorgang_id
                  AND (t.elem ->> 'lv_position_id') = ANY(:pos_ids)
            """),
            {
                "aktueller_vorgang_id": str(aktueller_vorgang_id),
                "pos_ids": pos_ids,
            },
        ).mappings().all()

        # In ein Dict gruppieren: lv_position_id -> list[GenehmigterNT-dict]
        from collections import defaultdict
        per_position: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in rows:
            per_position[str(r["lv_position_id"])].append({
                "vorgang_id": r["vorgang_id"],
                "nummer": r["nummer"],
                "betrag_genehmigt": float(r["betrag_genehmigt"]) if r["betrag_genehmigt"] is not None else None,
                "status": r["status"],
            })

        # An jedes Treffer-Dict anhaengen. Wenn keine Genehmigung gefunden,
        # bleibt es eine leere Liste — das Frontend rendert dann keine Warnung.
        for t in treffer:
            t["bereits_genehmigte_nts"] = per_position.get(str(t["lv_position_id"]), [])

    def _exakte_suche(
        self,
        suchbegriff: str,
        bevorzugtes_lv_id: UUID | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """PostgreSQL-Volltextsuche gegen lv_positionen."""

        # Suchbegriff in tsquery umwandeln
        # Worte mit & verknuepfen fuer AND-Suche
        woerter = [w.strip() for w in suchbegriff.split() if w.strip() and len(w.strip()) > 2]
        if not woerter:
            return []

        # Stoppwoerter filtern (Metadaten aus Nachtragsnamen)
        stoppwoerter = {"ntv", "nachtrag", "alternativ", "zusaetzlich", "aenderung", "mehr", "weniger"}
        woerter = [w for w in woerter if w.lower() not in stoppwoerter and not w.isdigit()]
        if not woerter:
            return []

        # Lange Komposita aufbrechen (>12 Zeichen: Stamm auf 10 kuerzen)
        suchterme = []
        for w in woerter[:5]:
            suchterme.append(f"{w}:*")
            if len(w) > 12:
                suchterme.append(f"{w[:10]}:*")
                if len(w) > 16:
                    suchterme.append(f"{w[:7]}:*")

        # OR-Verknuepfung fuer breitere Treffer, Relevanz sortiert
        ts_query = " | ".join(suchterme)

        rows = self.db.execute(
            text("""
                SELECT p.id AS lv_position_id,
                       p.oz, p.kurztext, p.einheit, p.menge,
                       p.einheitspreis, p.gesamtpreis,
                       l.nummer::text AS lv_nummer,
                       ts_rank(
                           to_tsvector('german', COALESCE(p.kurztext, '') || ' ' || COALESCE(p.langtext, '')),
                           to_tsquery('german', :query)
                       ) AS relevanz
                FROM lv_positionen p
                JOIN leistungsverzeichnisse l ON l.id = p.lv_id
                WHERE to_tsvector('german', COALESCE(p.kurztext, '') || ' ' || COALESCE(p.langtext, ''))
                      @@ to_tsquery('german', :query)
                ORDER BY
                    CASE WHEN p.lv_id = :lv_id THEN 0 ELSE 1 END,
                    relevanz DESC
                LIMIT :limit
            """),
            {
                "query": ts_query,
                "lv_id": str(bevorzugtes_lv_id) if bevorzugtes_lv_id else "00000000-0000-0000-0000-000000000000",
                "limit": limit,
            },
        ).mappings().all()

        return [
            {
                "lv_position_id": r["lv_position_id"],
                "oz": r["oz"],
                "kurztext": r["kurztext"],
                "einheit": r["einheit"],
                "menge": float(r["menge"]) if r["menge"] else None,
                "einheitspreis": float(r["einheitspreis"]) if r["einheitspreis"] else None,
                "gesamtpreis": float(r["gesamtpreis"]) if r["gesamtpreis"] else None,
                "lv_nummer": r["lv_nummer"],
                "relevanz": float(r["relevanz"]),
                "methode": "exakt",
            }
            for r in rows
        ]
