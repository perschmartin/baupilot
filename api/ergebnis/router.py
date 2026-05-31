"""Ergebnis-Router — Datenbasis fuer die Ergebnis-Seite (4 Visualisierungen).

Endpoints:
  GET /api/v1/ergebnis/vorgaenge       — flat-Liste mit Verursacher/Bauteil/Z/K
  GET /api/v1/ergebnis/nullterminplan  — Soll-Phasen (JSON-Seed, spaeter X83)
  GET /api/v1/ergebnis/kennzahlen      — KPI-Header (Aggregate)

Filter-Params auf /vorgaenge:
  ?typ=...           — behinderungsanzeige|bedenkenanzeige|mangelanzeige|nachtrag (mehrfach)
  ?verursacher=...   — firmen.id (mehrfach)
  ?bauteil=...       — bauteile.kennung (mehrfach)
  ?nur_bestaetigt=true — nur Vorgaenge mit konfidenz_bestaetigt=TRUE

Alle Endpoints sind read-only und nutzen denselben Filter-Pfad, damit der
Frontend-Filter-Header alle 4 Tabs synchron beeinflusst.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth.dependencies import CurrentUser, get_current_user
from database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/ergebnis", tags=["ergebnis"])

TENANT_SCHEMA = "tenant_tlbv"
DATA_DIR = Path(__file__).parent / "data"


# ---------- /vorgaenge ---------------------------------------------------


def _filter_clauses(typ: list[str] | None,
                    verursacher: list[str] | None,
                    bauteil: list[str] | None,
                    nur_bestaetigt: bool) -> tuple[str, dict[str, Any]]:
    """Baut die WHERE-Klauseln + Parameter aus den Query-Filtern."""
    where = [
        "v.typ IN ('behinderungsanzeige','bedenkenanzeige','mangelanzeige','nachtrag')",
        "NOT v.geloescht",
    ]
    params: dict[str, Any] = {}
    if typ:
        where.append("v.typ::text = ANY(:typen)")
        params["typen"] = list(typ)
    if verursacher:
        where.append("v.verantwortlich_firma_id::text = ANY(:firmen)")
        params["firmen"] = list(verursacher)
    if bauteil:
        where.append("b.kennung = ANY(:bauteile)")
        params["bauteile"] = list(bauteil)
    if nur_bestaetigt:
        where.append("v.konfidenz_bestaetigt = TRUE")
    return " AND ".join(where), params


@router.get("/vorgaenge")
def vorgaenge_liste(
    user: CurrentUser,
    db: Session = Depends(get_db),
    typ: list[str] | None = Query(default=None),
    verursacher: list[str] | None = Query(default=None),
    bauteil: list[str] | None = Query(default=None),
    nur_bestaetigt: bool = False,
):
    """Flat-Tabelle: ein Eintrag pro Vorgang mit aufgeloesten Joins.

    Das ist die EINZIGE Datenquelle fuer alle vier Charts im Frontend —
    Gantt, Sankey, Wasserfall, Heatmap lesen daraus und aggregieren selbst.
    """
    where, params = _filter_clauses(typ, verursacher, bauteil, nur_bestaetigt)
    sql = f"""
        SELECT
          v.id::text                            AS id,
          v.nummer,
          v.typ::text                           AS typ,
          v.status::text                        AS status,
          v.gegenstand,
          v.beschreibung,
          v.verantwortlich_firma_id::text       AS verursacher_id,
          f.name                                AS verursacher_name,
          f.rolle                               AS verursacher_rolle,
          v.bauteil_id::text                    AS bauteil_id,
          b.kennung                             AS bauteil_kennung,
          b.name                                AS bauteil_name,
          v.zeitauswirkung_tage,
          v.zeit_arbeitstage,
          COALESCE(v.zeitauswirkung_tage, v.zeit_arbeitstage) AS z_tage,
          v.kosten_eur,
          v.betrag_gefordert,
          v.betrag_geprueft,
          v.betrag_genehmigt,
          v.nachtragsfolge_eur,
          v.folgekosten_betrieb_eur,
          v.minderkosten_eur,
          COALESCE(v.kosten_eur, v.betrag_genehmigt, v.betrag_geprueft, v.betrag_gefordert) AS k_eur,
          v.qualitaet_bewertung,
          v.qualitaetsauswirkung,
          v.konfidenz,
          v.konfidenz_bestaetigt,
          v.vorgaenger_id::text                 AS vorgaenger_id,
          v.beziehungstyp::text                 AS beziehungstyp,
          -- Vorfalls-Datum: aus dem LLM-Ergebnis im Pruefschritt 1 ziehen,
          -- fallback erstellt_am (Import-Datum, weniger praezise).
          COALESCE(
            (SELECT (p.ki_ergebnis->>'datum_dokument')::date
             FROM {TENANT_SCHEMA}.behinderungspruefung p
             WHERE p.vorgang_id = v.id AND p.schritt = 1
               AND p.ki_ergebnis->>'datum_dokument' ~ '^\\d{{4}}-(0[1-9]|1[0-2])-(0[1-9]|[12]\\d|3[01])$'),
            (SELECT (p.ki_ergebnis->>'datum_dokument')::date
             FROM {TENANT_SCHEMA}.bedenkenpruefung p
             WHERE p.vorgang_id = v.id AND p.schritt = 1
               AND p.ki_ergebnis->>'datum_dokument' ~ '^\\d{{4}}-(0[1-9]|1[0-2])-(0[1-9]|[12]\\d|3[01])$'),
            (SELECT (p.ki_ergebnis->>'datum_dokument')::date
             FROM {TENANT_SCHEMA}.mangelpruefung p
             WHERE p.vorgang_id = v.id AND p.schritt = 1
               AND p.ki_ergebnis->>'datum_dokument' ~ '^\\d{{4}}-(0[1-9]|1[0-2])-(0[1-9]|[12]\\d|3[01])$'),
            (SELECT (p.ki_ergebnis->>'datum_dokument')::date
             FROM {TENANT_SCHEMA}.nachtragspruefung p
             WHERE p.vorgang_id = v.id AND p.schritt = 1
               AND p.ki_ergebnis->>'datum_dokument' ~ '^\\d{{4}}-(0[1-9]|1[0-2])-(0[1-9]|[12]\\d|3[01])$'),
            v.erstellt_am::date
          )                                     AS vorfalls_datum,
          v.erstellt_am,
          -- Dokumente als JSON-Array: alle verknuepften PDFs des Vorgangs (id, name, groesse)
          COALESCE(
            (SELECT json_agg(json_build_object('id', d.id::text, 'dateiname', d.dateiname, 'groesse', d.dateigroesse_bytes) ORDER BY d.erstellt_am)
             FROM {TENANT_SCHEMA}.vorgang_dokumente vd
             JOIN {TENANT_SCHEMA}.dokumente d ON d.id = vd.dokument_id
             WHERE vd.vorgang_id = v.id AND NOT d.geloescht),
            '[]'::json
          )                                     AS dokumente
        FROM {TENANT_SCHEMA}.vorgaenge v
        LEFT JOIN {TENANT_SCHEMA}.firmen   f ON f.id = v.verantwortlich_firma_id
        LEFT JOIN {TENANT_SCHEMA}.bauteile b ON b.id = v.bauteil_id
        WHERE {where}
        ORDER BY v.typ::text, v.nummer
    """
    rows = db.execute(text(sql), params).mappings().all()
    return {
        "anzahl": len(rows),
        "vorgaenge": [dict(r) for r in rows],
    }


# ---------- /nullterminplan ---------------------------------------------


@router.get("/nullterminplan")
def nullterminplan(user: CurrentUser):
    """Liefert den (vorlaeufigen) Nullterminplan als JSON-Seed.

    Spaeter ersetzt durch Asta-X83-Import (AP 3.1).
    """
    p = DATA_DIR / "nullterminplan.json"
    if not p.exists():
        return {"phasen": [], "meilensteine": [], "hinweis": "kein Plan hinterlegt"}
    return json.loads(p.read_text(encoding="utf-8"))


@router.get("/netzplan")
def netzplan(user: CurrentUser, db: Session = Depends(get_db)):
    """Liefert den aggregierten Vorgangsknotennetzplan (B-013 POC).

    Quelle: Skript netzplan_extract.py auf BWP-xlsx (Stand 2024-10-31).
    Knoten = L0+L1 Sammelvorgaenge, Kanten = aggregierte Vorgaenger-Beziehungen,
    CPM-Felder (FA/FE/SA/SE/GP) per Forward+Backward Pass berechnet.

    Live-Anreicherung: pro Knoten werden zusaetzlich die aktuell betroffenen
    BauPilot-Vorgangs-IDs (aus DB) angehaengt, damit das Frontend nicht
    noch einen extra Request pro Klick machen muss.
    """
    p = DATA_DIR / "netzplan.json"
    if not p.exists():
        return {"knoten": [], "kanten": [], "hinweis": "kein Netzplan extrahiert"}
    data = json.loads(p.read_text(encoding="utf-8"))

    # Live-Anreicherung der BauPilot-Verbindungen: aus den Vorgangs-Nummern
    # die echten Vorgangs-IDs ziehen, damit das Frontend direkt klicken kann.
    nummern = set()
    for liste in (data.get("verbindungen_zu_baupilot") or {}).values():
        nummern.update(liste)

    nummer_zu_id: dict[str, str] = {}
    if nummern:
        rows = db.execute(text(f"""
            SELECT nummer, id::text AS id, typ::text AS typ
            FROM {TENANT_SCHEMA}.vorgaenge
            WHERE nummer = ANY(:nums) AND NOT geloescht
        """), {"nums": list(nummern)}).mappings().all()
        nummer_zu_id = {r["nummer"]: {"id": r["id"], "typ": r["typ"]} for r in rows}

    # In den Knoten direkt anreichen — pro Knoten ein 'baupilot_vorgaenge'-Array
    verbindungen = data.get("verbindungen_zu_baupilot") or {}
    for k in data.get("knoten", []):
        nrs = verbindungen.get(str(k["id"]), [])
        k["baupilot_vorgaenge"] = [
            {"nummer": n, **nummer_zu_id[n]} for n in nrs if n in nummer_zu_id
        ]
    return data


# ---------- /kennzahlen --------------------------------------------------


@router.get("/kennzahlen")
def kennzahlen(
    user: CurrentUser,
    db: Session = Depends(get_db),
    typ: list[str] | None = Query(default=None),
    verursacher: list[str] | None = Query(default=None),
    bauteil: list[str] | None = Query(default=None),
    nur_bestaetigt: bool = False,
):
    """Aggregat-KPIs fuer den Filter-Header.

    Liefert: Anzahl pro Vorgangstyp, Σ Tage, Σ Euro, davon mit Verursacher,
    Anzahl Firmen, Datum-Spanne.
    """
    where, params = _filter_clauses(typ, verursacher, bauteil, nur_bestaetigt)
    sql = f"""
        SELECT
          COUNT(*)                                              AS anzahl_gesamt,
          COUNT(*) FILTER (WHERE v.typ::text='behinderungsanzeige') AS anzahl_beha,
          COUNT(*) FILTER (WHERE v.typ::text='bedenkenanzeige')     AS anzahl_bed,
          COUNT(*) FILTER (WHERE v.typ::text='mangelanzeige')       AS anzahl_ma,
          COUNT(*) FILTER (WHERE v.typ::text='nachtrag')            AS anzahl_nt,
          COUNT(*) FILTER (WHERE v.verantwortlich_firma_id IS NOT NULL) AS mit_verursacher,
          COUNT(*) FILTER (WHERE v.bauteil_id IS NOT NULL)         AS mit_bauteil,
          COUNT(DISTINCT v.verantwortlich_firma_id) FILTER (WHERE v.verantwortlich_firma_id IS NOT NULL) AS firmen_anzahl,
          COALESCE(SUM(COALESCE(v.zeitauswirkung_tage, v.zeit_arbeitstage)), 0) AS summe_tage,
          COALESCE(SUM(COALESCE(v.kosten_eur, v.betrag_genehmigt, v.betrag_geprueft, v.betrag_gefordert)), 0) AS summe_eur
        FROM {TENANT_SCHEMA}.vorgaenge v
        LEFT JOIN {TENANT_SCHEMA}.firmen   f ON f.id = v.verantwortlich_firma_id
        LEFT JOIN {TENANT_SCHEMA}.bauteile b ON b.id = v.bauteil_id
        WHERE {where}
    """
    row = db.execute(text(sql), params).mappings().first()
    return dict(row) if row else {}


# ---------- /firmen + /bauteile (Filter-Optionen) -----------------------


@router.get("/firmen")
def firmen_optionen(user: CurrentUser, db: Session = Depends(get_db)):
    """Firmen-Stammdaten fuer den Verursacher-Filter."""
    rows = db.execute(text(f"""
        SELECT id::text AS id, name, rolle
        FROM {TENANT_SCHEMA}.firmen
        ORDER BY name
    """)).mappings().all()
    return {"firmen": [dict(r) for r in rows]}


@router.get("/lv-uebersicht")
def lv_uebersicht(user: CurrentUser, db: Session = Depends(get_db)):
    """Liste aller 60 LVs mit Aggregaten der betroffenen Vorgaenge.

    Pro LV: Anzahl Vorgaenge (gesamt + pro Typ), Σ Tage Verzug, Σ Schaden Euro,
    Datums-Spanne der Vorfaelle. Sortiert nach Anzahl Vorgaenge (mehr = oben).
    """
    rows = db.execute(text(f"""
        SELECT
          lv.id::text                                  AS id,
          lv.nummer,
          lv.bezeichnung,
          lv.auftragnehmer,
          lv.positionen_anzahl,
          lv.bauteil_id::text                          AS bauteil_id,
          b.kennung                                    AS bauteil_kennung,
          COUNT(v.id)                                  AS anzahl_vorgaenge,
          COUNT(v.id) FILTER (WHERE v.typ='behinderungsanzeige') AS anzahl_beha,
          COUNT(v.id) FILTER (WHERE v.typ='bedenkenanzeige')     AS anzahl_bed,
          COUNT(v.id) FILTER (WHERE v.typ='mangelanzeige')       AS anzahl_ma,
          COUNT(v.id) FILTER (WHERE v.typ='nachtrag')            AS anzahl_nt,
          COUNT(v.id) FILTER (WHERE v.verantwortlich_firma_id IS NOT NULL) AS mit_verursacher,
          COALESCE(SUM(COALESCE(v.zeitauswirkung_tage, v.zeit_arbeitstage)), 0) AS summe_tage,
          COALESCE(SUM(COALESCE(v.kosten_eur, v.betrag_genehmigt, v.betrag_geprueft, v.betrag_gefordert)), 0) AS summe_eur
        FROM {TENANT_SCHEMA}.leistungsverzeichnisse lv
        LEFT JOIN {TENANT_SCHEMA}.bauteile b ON b.id = lv.bauteil_id
        LEFT JOIN {TENANT_SCHEMA}.vorgaenge v ON v.lv_id = lv.id AND NOT v.geloescht
        GROUP BY lv.id, lv.nummer, lv.bezeichnung, lv.auftragnehmer, lv.positionen_anzahl, lv.bauteil_id, b.kennung
        ORDER BY COUNT(v.id) DESC, lv.nummer
    """)).mappings().all()
    return {"anzahl": len(rows), "lvs": [dict(r) for r in rows]}


@router.get("/lv-detail/{lv_id}")
def lv_detail(lv_id: str, user: CurrentUser, db: Session = Depends(get_db)):
    """Detail eines LV mit zugeordneten Vorgaengen.

    Liefert:
      - LV-Header (nummer, bezeichnung, auftragnehmer, positionen_anzahl, bauteil_kennung)
      - lv_positionen (sortiert nach OZ) — fuer spaeteren Drill-Down
      - Vorgaenge mit lv_id == lv_id, sortiert nach vorfalls_datum
      - Soll-Zeitfenster (aus dem Plan, sofern LV ein Bauteil hat)
    """
    lv = db.execute(text(f"""
        SELECT lv.id::text AS id, lv.nummer, lv.bezeichnung, lv.auftragnehmer,
               lv.positionen_anzahl, lv.bauteil_id::text AS bauteil_id,
               b.kennung AS bauteil_kennung, b.name AS bauteil_name
        FROM {TENANT_SCHEMA}.leistungsverzeichnisse lv
        LEFT JOIN {TENANT_SCHEMA}.bauteile b ON b.id = lv.bauteil_id
        WHERE lv.id = :id
    """), {"id": lv_id}).mappings().first()
    if not lv:
        return {"detail": "LV nicht gefunden"}

    positionen = db.execute(text(f"""
        SELECT id::text AS id, oz, kurztext, einheit, menge, einheitspreis, gesamtpreis,
               hierarchie_ebene, ist_titel
        FROM {TENANT_SCHEMA}.lv_positionen
        WHERE lv_id = :id AND NOT geloescht
        ORDER BY oz
        LIMIT 500
    """), {"id": lv_id}).mappings().all()

    vorgaenge = db.execute(text(f"""
        SELECT v.id::text AS id, v.nummer, v.typ::text AS typ, v.gegenstand, v.beschreibung,
               f.name AS verursacher_name,
               COALESCE(v.zeitauswirkung_tage, v.zeit_arbeitstage) AS z_tage,
               COALESCE(v.kosten_eur, v.betrag_genehmigt, v.betrag_geprueft, v.betrag_gefordert) AS k_eur,
               COALESCE(
                 (SELECT (p.ki_ergebnis->>'datum_dokument')::date
                  FROM {TENANT_SCHEMA}.behinderungspruefung p
                  WHERE p.vorgang_id = v.id AND p.schritt = 1
                    AND p.ki_ergebnis->>'datum_dokument' ~ '^\\d{{4}}-(0[1-9]|1[0-2])-(0[1-9]|[12]\\d|3[01])$'),
                 (SELECT (p.ki_ergebnis->>'datum_dokument')::date
                  FROM {TENANT_SCHEMA}.bedenkenpruefung p
                  WHERE p.vorgang_id = v.id AND p.schritt = 1
                    AND p.ki_ergebnis->>'datum_dokument' ~ '^\\d{{4}}-(0[1-9]|1[0-2])-(0[1-9]|[12]\\d|3[01])$'),
                 (SELECT (p.ki_ergebnis->>'datum_dokument')::date
                  FROM {TENANT_SCHEMA}.nachtragspruefung p
                  WHERE p.vorgang_id = v.id AND p.schritt = 1
                    AND p.ki_ergebnis->>'datum_dokument' ~ '^\\d{{4}}-(0[1-9]|1[0-2])-(0[1-9]|[12]\\d|3[01])$'),
                 v.erstellt_am::date
               ) AS vorfalls_datum,
               v.konfidenz, v.konfidenz_bestaetigt
        FROM {TENANT_SCHEMA}.vorgaenge v
        LEFT JOIN {TENANT_SCHEMA}.firmen f ON f.id = v.verantwortlich_firma_id
        WHERE v.lv_id = :id AND NOT v.geloescht
        ORDER BY v.typ::text, v.nummer
    """), {"id": lv_id}).mappings().all()

    return {
        "lv": dict(lv),
        "positionen": [dict(p) for p in positionen],
        "positionen_anzahl_gesamt": len(positionen),
        "vorgaenge": [dict(v) for v in vorgaenge],
    }


@router.get("/pipeline-status")
def pipeline_status(user: CurrentUser, db: Session = Depends(get_db)):
    """Liefert den Verarbeitungs-Stand der zweistufigen Extraktor-Pipeline.

    Stufe 1: PDF -> beschreibung (Pass-1, alter PowerShell-Lauf)
    Stufe 2: beschreibung -> verursacher/bauteil/Z/K (mein v2-Lauf)

    Zusätzlich: letzte N Zeilen aus /tmp/extraktor_v2.log (Container-lokal,
    pragmatisch fuer Live-Anzeige des aktuellen Vorgangs).
    """
    rows = db.execute(text(f"""
        SELECT
          COUNT(*)                                                 AS gesamt,
          COUNT(*) FILTER (WHERE EXISTS (
            SELECT 1 FROM {TENANT_SCHEMA}.vorgang_dokumente vd
            WHERE vd.vorgang_id = v.id
          ))                                                       AS mit_pdf,
          COUNT(*) FILTER (WHERE v.beschreibung IS NOT NULL)       AS mit_beschreibung,
          COUNT(*) FILTER (WHERE v.verantwortlich_firma_id IS NOT NULL) AS mit_verursacher,
          COUNT(*) FILTER (WHERE v.bauteil_id IS NOT NULL)         AS mit_bauteil,
          COUNT(*) FILTER (WHERE v.vorgaenger_id IS NOT NULL)      AS mit_verknuepfung,
          MAX(v.geaendert_am)                                      AS letzte_aenderung
        FROM {TENANT_SCHEMA}.vorgaenge v
        WHERE v.typ IN ('behinderungsanzeige','bedenkenanzeige','mangelanzeige','nachtrag')
          AND NOT v.geloescht
    """)).mappings().first()

    # Log-Tail: letzte N Zeilen aus dem v2-Lauf (best effort, kein Fehler wenn nicht da).
    log_pfad = Path("/tmp/extraktor_v2.log")
    log_tail: list[str] = []
    aktuell_laeuft = False
    if log_pfad.exists():
        try:
            txt = log_pfad.read_text(encoding="utf-8", errors="replace")
            lines = [l for l in txt.splitlines() if l.strip()]
            log_tail = lines[-12:]
            # Heuristik "läuft": letzte Zeile innerhalb 5 min UND kein 'Fertig nach'
            from datetime import datetime, timezone
            for raw in reversed(lines[-20:]):
                if " Fertig nach " in raw:
                    aktuell_laeuft = False
                    break
                # Zeitstempel HH:MM:SS am Anfang
                if len(raw) > 8 and raw[2] == ":" and raw[5] == ":":
                    try:
                        hh, mm, ss = int(raw[:2]), int(raw[3:5]), int(raw[6:8])
                        jetzt = datetime.now(timezone.utc)
                        # Sekunden seit Mitternacht — Container läuft UTC
                        sekunden_log = hh * 3600 + mm * 60 + ss
                        sekunden_jetzt = jetzt.hour * 3600 + jetzt.minute * 60 + jetzt.second
                        delta = (sekunden_jetzt - sekunden_log) % 86400
                        aktuell_laeuft = delta < 300
                    except ValueError:
                        pass
                    break
        except OSError:
            pass

    return {
        **dict(rows),
        "log_tail": log_tail,
        "extraktor_v2_aktiv": aktuell_laeuft,
    }


@router.get("/bauteile")
def bauteile_optionen(user: CurrentUser, db: Session = Depends(get_db)):
    """Bauteil-Stammdaten fuer den Bauteil-Filter."""
    rows = db.execute(text(f"""
        SELECT id::text AS id, kennung, name, typ::text AS typ
        FROM {TENANT_SCHEMA}.bauteile
        WHERE NOT geloescht
        ORDER BY kennung
    """)).mappings().all()
    return {"bauteile": [dict(r) for r in rows]}
