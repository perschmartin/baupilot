"""
LV-Service: Geschaeftslogik fuer Leistungsverzeichnisse und Positionen.

Pattern: LVService(db) — wie AuthService, AufgabenService, DokumenteService.
KORRIGIERT: lv_id statt leistungsverzeichnis_id, nummernkreis als smallint.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger("baupilot.lv_service")

TENANT_SCHEMA = "tenant_tlbv"


class LVService:
    """Service fuer Leistungsverzeichnisse und LV-Positionen."""

    def __init__(self, db: Session):
        self.db = db

    # ================================================================
    # Leistungsverzeichnisse
    # ================================================================

    def lv_liste(self, projekt_kurz: str = "FLI") -> list[dict]:
        """Alle LVs eines Projekts auflisten."""
        self.db.execute(text(f"SET LOCAL search_path TO {TENANT_SCHEMA}, shared, public"))
        result = self.db.execute(text("""
            SELECT l.id, l.projekt_id, l.nummer, l.bezeichnung, l.nummernkreis,
                   l.dateiname, l.positionen_anzahl, l.extraktion_status,
                   l.klassifikation, l.erstellt_am
            FROM leistungsverzeichnisse l
            JOIN projekte p ON l.projekt_id = p.id
            WHERE p.kurz = :projekt AND l.geloescht = FALSE
            ORDER BY l.nummer
        """), {"projekt": projekt_kurz})
        return [dict(row._mapping) for row in result.fetchall()]

    def lv_detail(self, lv_id: str) -> Optional[dict]:
        """Ein LV mit Positionsanzahl laden."""
        self.db.execute(text(f"SET LOCAL search_path TO {TENANT_SCHEMA}, shared, public"))
        result = self.db.execute(text("""
            SELECT l.*, COUNT(p.id) AS positionen_gezaehlt
            FROM leistungsverzeichnisse l
            LEFT JOIN lv_positionen p ON p.lv_id = l.id AND p.geloescht = FALSE
            WHERE l.id = CAST(:id AS UUID) AND l.geloescht = FALSE
            GROUP BY l.id
        """), {"id": lv_id})
        row = result.fetchone()
        return dict(row._mapping) if row else None

    def lv_anlegen(self, projekt_kurz: str, nummer: str, bezeichnung: str,
                   dateiname: str = None, nummernkreis: int = None,
                   klassifikation: str = "intern", benutzer: str = "system") -> str:
        """Neues LV anlegen. Gibt die ID zurueck."""
        self.db.execute(text(f"SET LOCAL search_path TO {TENANT_SCHEMA}, shared, public"))

        # Projekt-ID ermitteln
        proj = self.db.execute(text(
            "SELECT id FROM projekte WHERE kurz = :kurz"
        ), {"kurz": projekt_kurz}).fetchone()
        if not proj:
            raise ValueError(f"Projekt '{projekt_kurz}' nicht gefunden")

        lv_id = str(uuid.uuid4())
        self.db.execute(text("""
            INSERT INTO leistungsverzeichnisse
                (id, projekt_id, nummer, bezeichnung, dateiname, nummernkreis,
                 klassifikation, extraktion_status,
                 erstellt_am, erstellt_von, geaendert_am, geaendert_von, geloescht)
            VALUES
                (CAST(:id AS UUID), CAST(:projekt_id AS UUID), :nummer, :bezeichnung,
                 :dateiname, :nummernkreis, CAST(:klassifikation AS klassifikation),
                 'ausstehend',
                 NOW(), :benutzer, NOW(), :benutzer, FALSE)
        """), {
            "id": lv_id,
            "projekt_id": str(proj.id),
            "nummer": nummer,
            "bezeichnung": bezeichnung,
            "dateiname": dateiname,
            "nummernkreis": nummernkreis,
            "klassifikation": klassifikation,
            "benutzer": benutzer,
        })
        self.db.commit()
        return lv_id

    def lv_status_setzen(self, lv_id: str, status: str, positionen_anzahl: int = None):
        """Extraktionsstatus aktualisieren."""
        self.db.execute(text(f"SET LOCAL search_path TO {TENANT_SCHEMA}, shared, public"))
        params: dict[str, Any] = {"id": lv_id, "status": status}
        sql = "UPDATE leistungsverzeichnisse SET extraktion_status = :status, geaendert_am = NOW()"
        if positionen_anzahl is not None:
            sql += ", positionen_anzahl = :anzahl"
            params["anzahl"] = positionen_anzahl
        sql += " WHERE id = CAST(:id AS UUID)"
        self.db.execute(text(sql), params)
        self.db.commit()

    # ================================================================
    # LV-Positionen
    # ================================================================

    def positionen_liste(self, lv_id: str, suche: str = None,
                         nur_positionen: bool = False) -> list[dict]:
        """Positionen eines LV auflisten."""
        self.db.execute(text(f"SET LOCAL search_path TO {TENANT_SCHEMA}, shared, public"))

        sql = """
            SELECT id, lv_id, oz, kurztext, langtext,
                   menge, einheit, einheitspreis, gesamtpreis,
                   hierarchie_ebene, ist_titel, extrahiert_am, extrahiert_mit
            FROM lv_positionen
            WHERE lv_id = CAST(:lv_id AS UUID)
              AND geloescht = FALSE
        """
        params: dict[str, Any] = {"lv_id": lv_id}

        if nur_positionen:
            sql += " AND ist_titel = FALSE"

        if suche:
            sql += " AND (kurztext ILIKE :suche OR oz ILIKE :suche)"
            params["suche"] = f"%{suche}%"

        sql += " ORDER BY oz NULLS LAST, erstellt_am"

        result = self.db.execute(text(sql), params)
        return [dict(row._mapping) for row in result.fetchall()]

    def positionen_einfuegen(self, lv_id: str, positionen: list[dict],
                              extractor: str = "docling", benutzer: str = "system") -> int:
        """
        Batch-Insert von LV-Positionen.

        Args:
            lv_id: UUID des Leistungsverzeichnisses
            positionen: Liste aus lv_parser.parse_lv_tables()
            extractor: "docling" oder "pdfplumber"
            benutzer: Ersteller

        Returns:
            Anzahl eingefuegter Positionen
        """
        self.db.execute(text(f"SET LOCAL search_path TO {TENANT_SCHEMA}, shared, public"))

        count = 0
        now = datetime.now(timezone.utc).isoformat()

        for pos in positionen:
            pos_id = str(uuid.uuid4())
            self.db.execute(text("""
                INSERT INTO lv_positionen
                    (id, lv_id, oz, kurztext, langtext,
                     menge, einheit, einheitspreis, gesamtpreis,
                     hierarchie_ebene, ist_titel, extrahiert_am, extrahiert_mit, roh_text,
                     erstellt_am, erstellt_von, geaendert_am, geaendert_von, geloescht)
                VALUES
                    (CAST(:id AS UUID), CAST(:lv_id AS UUID), :oz, :kurztext, :langtext,
                     :menge, :einheit, :ep, :gp,
                     :hierarchie, :ist_titel, CAST(:extrahiert_am AS TIMESTAMPTZ), :extrahiert_mit, :roh_text,
                     NOW(), :benutzer, NOW(), :benutzer, FALSE)
                ON CONFLICT (lv_id, oz) DO NOTHING
            """), {
                "id": pos_id,
                "lv_id": lv_id,
                "oz": pos.get("oz") or "",
                "kurztext": pos.get("kurztext") or "",
                "langtext": pos.get("langtext"),
                "menge": float(pos["menge"]) if pos.get("menge") is not None else None,
                "einheit": pos.get("einheit"),
                "ep": float(pos["einheitspreis"]) if pos.get("einheitspreis") is not None else None,
                "gp": float(pos["gesamtpreis"]) if pos.get("gesamtpreis") is not None else None,
                "hierarchie": pos.get("hierarchie_ebene", 0),
                "ist_titel": pos.get("ist_titel", False),
                "extrahiert_am": now,
                "extrahiert_mit": extractor,
                "roh_text": pos.get("roh_text"),
                "benutzer": benutzer,
            })
            count += 1

        self.db.commit()
        logger.info(f"{count} Positionen fuer LV {lv_id} eingefuegt")
        return count

    def statistik(self, projekt_kurz: str = "FLI") -> dict:
        """Gesamtstatistik ueber alle LVs."""
        self.db.execute(text(f"SET LOCAL search_path TO {TENANT_SCHEMA}, shared, public"))
        result = self.db.execute(text("""
            SELECT
                COUNT(DISTINCT l.id) AS lv_gesamt,
                COALESCE(SUM(l.positionen_anzahl), 0) AS positionen_gesamt,
                COUNT(DISTINCT CASE WHEN l.extraktion_status = 'abgeschlossen' THEN l.id END) AS extrahiert,
                COUNT(DISTINCT CASE WHEN l.extraktion_status = 'ausstehend' THEN l.id END) AS ausstehend,
                COUNT(DISTINCT CASE WHEN l.extraktion_status = 'fehler' THEN l.id END) AS fehler
            FROM leistungsverzeichnisse l
            JOIN projekte p ON l.projekt_id = p.id
            WHERE p.kurz = :projekt AND l.geloescht = FALSE
        """), {"projekt": projekt_kurz})
        row = result.fetchone()
        return dict(row._mapping)
