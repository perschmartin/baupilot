"""Tool-Definitionen + -Implementierungen fuer den Chatbot.

Read-only DB-Zugriffe ueber SQLAlchemy text()-SQL. Jedes Tool hat:
  1. Eine OpenAI-style JSON-Schema-Definition (fuer LiteLLM tool_calls)
  2. Eine Python-Implementierung, die ein dict zurueckgibt

Sicherheit:
  - Ausschliesslich SELECTs.
  - Tenant-Isolation: search_path wird vor jedem Aufruf gesetzt.
  - Klassifikations-VS-NfD ausblenden (TODO B-006, vorerst alle).
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

TENANT_SCHEMA = "tenant_tlbv"


# -------- Tool-Definitionen (OpenAI-style) -------------------------------

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "vorgaenge_filtern",
            "description": (
                "Sucht und listet Vorgaenge (Behinderungs-, Bedenken-, Maengelanzeigen, "
                "Nachtraege) nach Filterkriterien. Liefert eine Liste mit Nummer, Typ, "
                "Gegenstand, Verursacher, Bauteil, Z (Tage Verzug) und K (Schaden in EUR)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "typ": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["behinderungsanzeige", "bedenkenanzeige", "mangelanzeige", "nachtrag"]},
                        "description": "Vorgangstypen (mehrfach moeglich, leer = alle)",
                    },
                    "verursacher_name": {
                        "type": "string",
                        "description": "Teil des Firmennamens (z.B. 'BWP', 'TLBV', 'ROM'). Optional.",
                    },
                    "bauteil": {
                        "type": "string",
                        "description": "Bauteil-Kennung: GEB30, GEB31, GEB32, GEB33, GEB34, AUSS. Optional.",
                    },
                    "lv_nummer": {
                        "type": "string",
                        "description": "Leistungsverzeichnis-Nummer als Text (z.B. '208', '124'). Optional.",
                    },
                    "suche": {
                        "type": "string",
                        "description": "Volltextsuche in Gegenstand und Beschreibung. Optional.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximale Anzahl Treffer (default 20, max 100).",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "vorgang_details",
            "description": (
                "Holt alle Details zu einem konkreten Vorgang anhand der Nummer "
                "(z.B. 'BehA-018', 'NT-026'). Liefert Gegenstand, Beschreibung, "
                "Verursacher, Bauteil, LV, Vorfalls-Datum, Status, Q/Z/K, "
                "Konfidenz und Anzahl verlinkter Dokumente."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "nummer": {
                        "type": "string",
                        "description": "Vorgangs-Nummer wie 'BehA-018', 'BED-003', 'MA-A-008', 'NT-026'.",
                    },
                },
                "required": ["nummer"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kennzahlen",
            "description": (
                "Aggregiert Vorgaenge: Anzahl, Summe Tage Verzug, Summe Schaden in EUR. "
                "Optional gruppiert nach Verursacher, Bauteil oder Vorgangstyp."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "gruppieren_nach": {
                        "type": "string",
                        "enum": ["typ", "verursacher", "bauteil", "lv", "(keine)"],
                        "description": "Gruppierung. '(keine)' liefert ein Gesamtaggregat.",
                    },
                    "typ_filter": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["behinderungsanzeige", "bedenkenanzeige", "mangelanzeige", "nachtrag"]},
                        "description": "Optional: nur diese Vorgangstypen.",
                    },
                    "bauteil_filter": {
                        "type": "string",
                        "description": "Optional: nur dieses Bauteil (GEB30..GEB34, AUSS).",
                    },
                },
                "required": ["gruppieren_nach"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lv_suche",
            "description": (
                "Sucht Leistungsverzeichnisse anhand von Nummer oder Bezeichnung. "
                "Liefert LV-Nummer, Bezeichnung, Auftragnehmer und Anzahl der "
                "zugeordneten Vorgaenge."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "suche": {
                        "type": "string",
                        "description": "LV-Nummer (z.B. '208') oder Text-Suche in der Bezeichnung (z.B. 'Brandschutz').",
                    },
                },
                "required": ["suche"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "verursacher_top",
            "description": (
                "Liefert die Top-Verursacher nach gewaehlter Metrik: nach Anzahl "
                "Vorgaenge ('anzahl'), Summe Tage Verzug ('tage') oder Summe "
                "Schaden in EUR ('eur'). Sortiert absteigend."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "metrik": {
                        "type": "string",
                        "enum": ["anzahl", "tage", "eur"],
                        "description": "Sortier-Metrik.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Anzahl Top-Eintraege (default 5, max 20).",
                    },
                },
                "required": ["metrik"],
            },
        },
    },
]


# -------- Tool-Implementierungen -----------------------------------------


def _set_tenant_search_path(db: Session) -> None:
    db.execute(text(f"SET search_path = {TENANT_SCHEMA}, public"))


def tool_vorgaenge_filtern(db: Session, args: dict) -> dict:
    _set_tenant_search_path(db)
    where = [
        "v.typ IN ('behinderungsanzeige','bedenkenanzeige','mangelanzeige','nachtrag')",
        "NOT v.geloescht",
    ]
    params: dict[str, Any] = {}
    if args.get("typ"):
        where.append("v.typ::text = ANY(:typen)")
        params["typen"] = list(args["typ"])
    if args.get("verursacher_name"):
        where.append("f.name ILIKE :verurs_name")
        params["verurs_name"] = f"%{args['verursacher_name']}%"
    if args.get("bauteil"):
        where.append("b.kennung = :bauteil")
        params["bauteil"] = args["bauteil"]
    if args.get("lv_nummer"):
        where.append("lv.nummer = :lv_nummer")
        params["lv_nummer"] = args["lv_nummer"]
    if args.get("suche"):
        where.append("(v.gegenstand ILIKE :suche OR v.beschreibung ILIKE :suche)")
        params["suche"] = f"%{args['suche']}%"

    limit = min(int(args.get("limit") or 20), 100)
    params["limit"] = limit

    sql = f"""
        SELECT v.nummer, v.typ::text AS typ, v.gegenstand, v.status::text AS status,
               f.name AS verursacher, b.kennung AS bauteil, lv.nummer AS lv_nummer,
               COALESCE(v.zeitauswirkung_tage, v.zeit_arbeitstage) AS z_tage,
               COALESCE(v.kosten_eur, v.betrag_genehmigt, v.betrag_geprueft, v.betrag_gefordert) AS k_eur
        FROM {TENANT_SCHEMA}.vorgaenge v
        LEFT JOIN {TENANT_SCHEMA}.firmen f ON f.id = v.verantwortlich_firma_id
        LEFT JOIN {TENANT_SCHEMA}.bauteile b ON b.id = v.bauteil_id
        LEFT JOIN {TENANT_SCHEMA}.leistungsverzeichnisse lv ON lv.id = v.lv_id
        WHERE {' AND '.join(where)}
        ORDER BY v.typ::text, v.nummer
        LIMIT :limit
    """
    rows = db.execute(text(sql), params).mappings().all()
    # Cast Decimal -> float fuer JSON
    return {
        "treffer": len(rows),
        "vorgaenge": [
            {
                "nummer": r["nummer"],
                "typ": r["typ"],
                "gegenstand": r["gegenstand"],
                "status": r["status"],
                "verursacher": r["verursacher"],
                "bauteil": r["bauteil"],
                "lv_nummer": r["lv_nummer"],
                "z_tage": int(r["z_tage"]) if r["z_tage"] is not None else None,
                "k_eur": float(r["k_eur"]) if r["k_eur"] is not None else None,
            }
            for r in rows
        ],
    }


def tool_vorgang_details(db: Session, args: dict) -> dict:
    _set_tenant_search_path(db)
    nummer = (args.get("nummer") or "").strip()
    if not nummer:
        return {"fehler": "Parameter 'nummer' fehlt"}

    sql = f"""
        SELECT v.nummer, v.typ::text AS typ, v.gegenstand, v.beschreibung,
               v.status::text AS status, v.konfidenz, v.konfidenz_bestaetigt,
               f.name AS verursacher, f.rolle AS verursacher_rolle,
               b.kennung AS bauteil, b.name AS bauteil_name,
               lv.nummer AS lv_nummer, lv.bezeichnung AS lv_bezeichnung,
               COALESCE(v.zeitauswirkung_tage, v.zeit_arbeitstage) AS z_tage,
               COALESCE(v.kosten_eur, v.betrag_genehmigt, v.betrag_geprueft, v.betrag_gefordert) AS k_eur,
               v.betrag_gefordert, v.betrag_geprueft, v.betrag_genehmigt,
               (SELECT COUNT(*) FROM {TENANT_SCHEMA}.vorgang_dokumente vd
                JOIN {TENANT_SCHEMA}.dokumente d ON d.id = vd.dokument_id
                WHERE vd.vorgang_id = v.id AND NOT d.geloescht) AS anzahl_dokumente
        FROM {TENANT_SCHEMA}.vorgaenge v
        LEFT JOIN {TENANT_SCHEMA}.firmen f ON f.id = v.verantwortlich_firma_id
        LEFT JOIN {TENANT_SCHEMA}.bauteile b ON b.id = v.bauteil_id
        LEFT JOIN {TENANT_SCHEMA}.leistungsverzeichnisse lv ON lv.id = v.lv_id
        WHERE v.nummer = :nr AND NOT v.geloescht
        LIMIT 1
    """
    r = db.execute(text(sql), {"nr": nummer}).mappings().first()
    if not r:
        return {"fehler": f"Vorgang '{nummer}' nicht gefunden"}

    return {
        "nummer": r["nummer"],
        "typ": r["typ"],
        "gegenstand": r["gegenstand"],
        "beschreibung": r["beschreibung"],
        "status": r["status"],
        "verursacher": r["verursacher"],
        "verursacher_rolle": r["verursacher_rolle"],
        "bauteil": r["bauteil"],
        "bauteil_name": r["bauteil_name"],
        "lv_nummer": r["lv_nummer"],
        "lv_bezeichnung": r["lv_bezeichnung"],
        "z_tage": int(r["z_tage"]) if r["z_tage"] is not None else None,
        "k_eur": float(r["k_eur"]) if r["k_eur"] is not None else None,
        "betrag_gefordert": float(r["betrag_gefordert"]) if r["betrag_gefordert"] is not None else None,
        "betrag_geprueft": float(r["betrag_geprueft"]) if r["betrag_geprueft"] is not None else None,
        "betrag_genehmigt": float(r["betrag_genehmigt"]) if r["betrag_genehmigt"] is not None else None,
        "konfidenz": float(r["konfidenz"]) if r["konfidenz"] is not None else None,
        "konfidenz_bestaetigt": r["konfidenz_bestaetigt"],
        "anzahl_dokumente": r["anzahl_dokumente"],
    }


def tool_kennzahlen(db: Session, args: dict) -> dict:
    _set_tenant_search_path(db)
    gruppe = args.get("gruppieren_nach", "(keine)")
    where = [
        "v.typ IN ('behinderungsanzeige','bedenkenanzeige','mangelanzeige','nachtrag')",
        "NOT v.geloescht",
    ]
    params: dict[str, Any] = {}
    if args.get("typ_filter"):
        where.append("v.typ::text = ANY(:typen)")
        params["typen"] = list(args["typ_filter"])
    if args.get("bauteil_filter"):
        where.append("b.kennung = :bauteil")
        params["bauteil"] = args["bauteil_filter"]

    select_cols = """
        COUNT(*) AS anzahl,
        COALESCE(SUM(COALESCE(v.zeitauswirkung_tage, v.zeit_arbeitstage)), 0) AS summe_tage,
        COALESCE(SUM(COALESCE(v.kosten_eur, v.betrag_genehmigt, v.betrag_geprueft, v.betrag_gefordert)), 0) AS summe_eur
    """
    if gruppe == "typ":
        sql = f"""
            SELECT v.typ::text AS gruppe, {select_cols}
            FROM {TENANT_SCHEMA}.vorgaenge v
            LEFT JOIN {TENANT_SCHEMA}.bauteile b ON b.id = v.bauteil_id
            WHERE {' AND '.join(where)} GROUP BY v.typ ORDER BY anzahl DESC
        """
    elif gruppe == "verursacher":
        sql = f"""
            SELECT COALESCE(f.name, '(unbekannt)') AS gruppe, {select_cols}
            FROM {TENANT_SCHEMA}.vorgaenge v
            LEFT JOIN {TENANT_SCHEMA}.firmen f ON f.id = v.verantwortlich_firma_id
            LEFT JOIN {TENANT_SCHEMA}.bauteile b ON b.id = v.bauteil_id
            WHERE {' AND '.join(where)} GROUP BY f.name ORDER BY anzahl DESC
        """
    elif gruppe == "bauteil":
        sql = f"""
            SELECT COALESCE(b.kennung, '(unbekannt)') AS gruppe, {select_cols}
            FROM {TENANT_SCHEMA}.vorgaenge v
            LEFT JOIN {TENANT_SCHEMA}.bauteile b ON b.id = v.bauteil_id
            WHERE {' AND '.join(where)} GROUP BY b.kennung ORDER BY anzahl DESC
        """
    elif gruppe == "lv":
        sql = f"""
            SELECT COALESCE(lv.nummer, '(unbekannt)') AS gruppe, {select_cols}
            FROM {TENANT_SCHEMA}.vorgaenge v
            LEFT JOIN {TENANT_SCHEMA}.leistungsverzeichnisse lv ON lv.id = v.lv_id
            LEFT JOIN {TENANT_SCHEMA}.bauteile b ON b.id = v.bauteil_id
            WHERE {' AND '.join(where)} GROUP BY lv.nummer ORDER BY anzahl DESC LIMIT 20
        """
    else:  # (keine)
        sql = f"""
            SELECT 'gesamt' AS gruppe, {select_cols}
            FROM {TENANT_SCHEMA}.vorgaenge v
            LEFT JOIN {TENANT_SCHEMA}.bauteile b ON b.id = v.bauteil_id
            WHERE {' AND '.join(where)}
        """
    rows = db.execute(text(sql), params).mappings().all()
    return {
        "gruppe": gruppe,
        "zeilen": [
            {
                "gruppe": r["gruppe"],
                "anzahl": int(r["anzahl"]),
                "summe_tage": int(r["summe_tage"]),
                "summe_eur": float(r["summe_eur"]),
            }
            for r in rows
        ],
    }


def tool_lv_suche(db: Session, args: dict) -> dict:
    _set_tenant_search_path(db)
    suche = (args.get("suche") or "").strip()
    if not suche:
        return {"fehler": "Parameter 'suche' fehlt"}
    sql = f"""
        SELECT lv.nummer, lv.bezeichnung, lv.auftragnehmer,
               (SELECT COUNT(*) FROM {TENANT_SCHEMA}.vorgaenge v
                WHERE v.lv_id = lv.id AND NOT v.geloescht) AS anzahl_vorgaenge
        FROM {TENANT_SCHEMA}.leistungsverzeichnisse lv
        WHERE NOT lv.geloescht
          AND (lv.nummer = :exakt OR lv.bezeichnung ILIKE :unscharf)
        ORDER BY (lv.nummer = :exakt) DESC, lv.nummer
        LIMIT 15
    """
    rows = db.execute(text(sql), {"exakt": suche, "unscharf": f"%{suche}%"}).mappings().all()
    return {
        "treffer": len(rows),
        "lvs": [
            {
                "nummer": r["nummer"],
                "bezeichnung": r["bezeichnung"],
                "auftragnehmer": r["auftragnehmer"],
                "anzahl_vorgaenge": int(r["anzahl_vorgaenge"]),
            }
            for r in rows
        ],
    }


def tool_verursacher_top(db: Session, args: dict) -> dict:
    _set_tenant_search_path(db)
    metrik = args.get("metrik", "anzahl")
    limit = min(int(args.get("limit") or 5), 20)
    order_by = {
        "anzahl": "anzahl DESC",
        "tage":   "summe_tage DESC",
        "eur":    "summe_eur DESC",
    }.get(metrik, "anzahl DESC")
    sql = f"""
        SELECT f.name AS verursacher, f.rolle,
               COUNT(*) AS anzahl,
               COALESCE(SUM(COALESCE(v.zeitauswirkung_tage, v.zeit_arbeitstage)), 0) AS summe_tage,
               COALESCE(SUM(COALESCE(v.kosten_eur, v.betrag_genehmigt, v.betrag_geprueft, v.betrag_gefordert)), 0) AS summe_eur
        FROM {TENANT_SCHEMA}.vorgaenge v
        JOIN {TENANT_SCHEMA}.firmen f ON f.id = v.verantwortlich_firma_id
        WHERE v.typ IN ('behinderungsanzeige','bedenkenanzeige','mangelanzeige','nachtrag')
          AND NOT v.geloescht
        GROUP BY f.name, f.rolle
        ORDER BY {order_by}
        LIMIT :limit
    """
    rows = db.execute(text(sql), {"limit": limit}).mappings().all()
    return {
        "metrik": metrik,
        "verursacher": [
            {
                "name": r["verursacher"],
                "rolle": r["rolle"],
                "anzahl": int(r["anzahl"]),
                "summe_tage": int(r["summe_tage"]),
                "summe_eur": float(r["summe_eur"]),
            }
            for r in rows
        ],
    }


# -------- Dispatcher -----------------------------------------------------

TOOL_FUNCS = {
    "vorgaenge_filtern": tool_vorgaenge_filtern,
    "vorgang_details": tool_vorgang_details,
    "kennzahlen": tool_kennzahlen,
    "lv_suche": tool_lv_suche,
    "verursacher_top": tool_verursacher_top,
}


def tool_aufrufen(db: Session, name: str, args: dict) -> dict:
    """Ruft das passende Tool auf und faengt Fehler ab.

    Antwort ist immer ein dict — bei Fehlern mit Schluessel 'fehler'.
    """
    fn = TOOL_FUNCS.get(name)
    if not fn:
        return {"fehler": f"Unbekanntes Werkzeug: {name}"}
    try:
        return fn(db, args or {})
    except Exception as e:
        logger.exception("Tool-Fehler %s: %s", name, e)
        return {"fehler": f"Werkzeug-Fehler: {str(e)[:200]}"}
