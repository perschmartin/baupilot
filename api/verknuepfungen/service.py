"""Verknuepfungsanalyse — BK->BA->NT Kausalketten (B-002, E12).

Zwei Schichten:
  1. Deterministisch: gleiche LV-Position, gleiches Bauteil, Datums-Naehe
  2. LLM-gestuetzt: semantische Aehnlichkeit der Beschreibungen

Alle Vorschlaege gehen durch das B-002-Bestaetigungs-Gate:
  - vorgaenger_id + beziehungstyp='llm_vorschlag' + konfidenz
  - Mensch bestaetigt oder lehnt ab
  - Erst nach Bestaetigung wird beziehungstyp auf den echten Typ gesetzt
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import settings

logger = logging.getLogger(__name__)

# Gewichtung fuer den deterministischen Score
GEWICHT_LV = 0.4        # gleiche LV-Position
GEWICHT_BAUTEIL = 0.2   # gleiches Bauteil
GEWICHT_DATUM = 0.2     # zeitliche Naehe (innerhalb 90 Tage)
GEWICHT_GEWERK = 0.2    # Reserve (Bauteil-Bonus)

# Schwelle ab der ein Vorschlag gespeichert wird
KONFIDENZ_SCHWELLE = 0.3

# Maximale Anzahl Vorschlaege pro Vorgang
MAX_VORSCHLAEGE = 5


def finde_verknuepfungen_deterministisch(
    db: Session, vorgang_id: UUID
) -> list[dict[str, Any]]:
    """Deterministische Suche nach verwandten Vorgaengen.

    Prueft: LV-Position, Bauteil, Gewerk, zeitliche Naehe.
    Gibt sortierte Liste mit Score zurueck.
    """
    # Quellvorgang laden
    quelle = db.execute(
        text("""
            SELECT v.id, v.typ::text AS typ, v.nummer, v.beschreibung,
                   v.lv_id, v.bauteil_id,
                   v.erstellt_am::date AS datum,
                   lv.nummer AS lv_nummer
            FROM vorgaenge v
            LEFT JOIN leistungsverzeichnisse lv ON lv.id = v.lv_id
            WHERE v.id = :vid AND NOT v.geloescht
        """),
        {"vid": str(vorgang_id)},
    ).mappings().first()

    if not quelle:
        return []

    # Kandidaten: alle anderen Vorgaenge (anderer Typ bevorzugt fuer Kausalketten)
    kandidaten = db.execute(
        text("""
            SELECT v.id, v.typ::text AS typ, v.nummer, v.beschreibung,
                   v.lv_id, v.bauteil_id,
                   v.erstellt_am::date AS datum,
                   lv.nummer AS lv_nummer,
                   v.vorgaenger_id
            FROM vorgaenge v
            LEFT JOIN leistungsverzeichnisse lv ON lv.id = v.lv_id
            WHERE v.id != :vid AND NOT v.geloescht
              AND v.typ::text != :typ
            ORDER BY v.erstellt_am DESC
            LIMIT 200
        """),
        {"vid": str(vorgang_id), "typ": quelle["typ"]},
    ).mappings().all()

    ergebnisse = []
    for k in kandidaten:
        score = 0.0
        gruende = []

        # LV-Match
        if quelle["lv_id"] and k["lv_id"] and quelle["lv_id"] == k["lv_id"]:
            score += GEWICHT_LV
            gruende.append(f"Gleiche LV ({k['lv_nummer']})")

        # Bauteil-Match
        if quelle["bauteil_id"] and k["bauteil_id"] and quelle["bauteil_id"] == k["bauteil_id"]:
            score += GEWICHT_BAUTEIL + GEWICHT_GEWERK
            gruende.append("Gleiches Bauteil")

        # Zeitliche Naehe (innerhalb 90 Tage)
        if quelle["datum"] and k["datum"]:
            diff = abs((quelle["datum"] - k["datum"]).days)
            if diff <= 90:
                zeit_score = GEWICHT_DATUM * (1.0 - diff / 90.0)
                score += zeit_score
                gruende.append(f"Zeitnah ({diff} Tage)")

        if score >= KONFIDENZ_SCHWELLE:
            ergebnisse.append({
                "ziel_id": str(k["id"]),
                "ziel_typ": k["typ"],
                "ziel_nummer": k["nummer"],
                "ziel_beschreibung": (k["beschreibung"] or "")[:200],
                "score": round(score, 3),
                "methode": "deterministisch",
                "gruende": gruende,
                "bereits_verknuepft": k["vorgaenger_id"] is not None,
            })

    ergebnisse.sort(key=lambda x: x["score"], reverse=True)
    return ergebnisse[:MAX_VORSCHLAEGE]


def finde_verknuepfungen_llm(
    db: Session, vorgang_id: UUID, kandidaten_det: list[dict]
) -> list[dict[str, Any]]:
    """LLM-gestuetzte Verknuepfungsanalyse.

    Nimmt die deterministischen Kandidaten + weitere Vorgaenge ohne
    deterministische Treffer und bewertet semantische Aehnlichkeit.
    """
    quelle = db.execute(
        text("""
            SELECT v.id, v.typ::text AS typ, v.nummer, v.beschreibung,
                   lv.nummer AS lv_nummer
            FROM vorgaenge v
            LEFT JOIN leistungsverzeichnisse lv ON lv.id = v.lv_id
            WHERE v.id = :vid AND NOT v.geloescht
        """),
        {"vid": str(vorgang_id)},
    ).mappings().first()

    if not quelle or not quelle["beschreibung"]:
        return kandidaten_det  # ohne Beschreibung kein LLM-Scoring moeglich

    # Top-20 Vorgaenge anderer Typen mit Beschreibung laden
    andere = db.execute(
        text("""
            SELECT v.id, v.typ::text AS typ, v.nummer, v.beschreibung
            FROM vorgaenge v
            WHERE v.id != :vid AND NOT v.geloescht
              AND v.typ::text != :typ
              AND v.beschreibung IS NOT NULL AND v.beschreibung != ''
            ORDER BY v.erstellt_am DESC
            LIMIT 20
        """),
        {"vid": str(vorgang_id), "typ": quelle["typ"]},
    ).mappings().all()

    if not andere:
        return kandidaten_det

    # Batch-Prompt: LLM bewertet Aehnlichkeit aller Kandidaten auf einmal
    kandidaten_text = "\n".join(
        f"[{i+1}] {a['typ']} {a['nummer']}: {(a['beschreibung'] or '')[:150]}"
        for i, a in enumerate(andere)
    )

    prompt = f"""Du bist BauPilot-Verknuepfungsanalyst. Pruefe welche der folgenden Vorgaenge
sachlich mit dem Quellvorgang zusammenhaengen (gleicher Sachverhalt, gleiche Ursache,
Folge voneinander).

QUELLVORGANG:
{quelle['typ']} {quelle['nummer']}: {(quelle['beschreibung'] or '')[:300]}

KANDIDATEN:
{kandidaten_text}

Antworte NUR mit einem JSON-Array. Jedes Element:
{{"nr": 1, "score": 0.0-1.0, "grund": "kurze Begruendung"}}

Nur Kandidaten mit score >= 0.3 aufnehmen. Leeres Array [] wenn keiner passt.
KEINE Einleitung, KEIN Markdown, NUR das JSON-Array."""

    try:
        url = f"http://{settings.litellm_host}:{settings.litellm_port}/v1/chat/completions"
        with httpx.Client(timeout=120) as http:
            r = http.post(url, json={
                "model": "qwen-32b",
                "messages": [
                    {"role": "system", "content": "Du bewertest sachliche Zusammenhaenge zwischen Bauvorgaengen. Antworte nur mit JSON."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
                "max_tokens": 600,
            })
            if r.status_code != 200:
                logger.warning("LLM-Aufruf fehlgeschlagen: %s", r.status_code)
                return kandidaten_det

        llm_text = r.json()["choices"][0]["message"]["content"].strip()
        # JSON-Bereinigung
        if llm_text.startswith("```"):
            llm_text = llm_text.strip("`").strip()
            if llm_text.lower().startswith("json"):
                llm_text = llm_text[4:].strip()
        i = llm_text.find("[")
        j = llm_text.rfind("]")
        if i >= 0 and j > i:
            llm_text = llm_text[i:j + 1]

        llm_ergebnisse = json.loads(llm_text)
    except Exception as e:
        logger.warning("LLM-Verknuepfungsanalyse fehlgeschlagen: %s", e)
        return kandidaten_det

    # LLM-Ergebnisse mit deterministischen Ergebnissen zusammenfuehren
    det_ids = {e["ziel_id"] for e in kandidaten_det}
    for llm_e in llm_ergebnisse:
        nr = llm_e.get("nr", 0) - 1
        if 0 <= nr < len(andere):
            a = andere[nr]
            ziel_id = str(a["id"])
            if ziel_id in det_ids:
                # Score aufaddieren
                for det_e in kandidaten_det:
                    if det_e["ziel_id"] == ziel_id:
                        det_e["score"] = round(min(det_e["score"] + llm_e["score"] * 0.5, 1.0), 3)
                        det_e["methode"] = "deterministisch+llm"
                        det_e["gruende"].append(f"LLM: {llm_e.get('grund', '')}")
                        break
            else:
                kandidaten_det.append({
                    "ziel_id": ziel_id,
                    "ziel_typ": a["typ"],
                    "ziel_nummer": a["nummer"],
                    "ziel_beschreibung": (a["beschreibung"] or "")[:200],
                    "score": round(llm_e["score"], 3),
                    "methode": "llm",
                    "gruende": [llm_e.get("grund", "LLM-Vorschlag")],
                    "bereits_verknuepft": False,
                })

    kandidaten_det.sort(key=lambda x: x["score"], reverse=True)
    return kandidaten_det[:MAX_VORSCHLAEGE]


def speichere_vorschlaege(
    db: Session, vorgang_id: UUID, vorschlaege: list[dict], benutzer_id: str
) -> int:
    """Speichert Verknuepfungsvorschlaege als llm_vorschlag in der DB.

    Setzt vorgaenger_id und beziehungstyp='llm_vorschlag' auf dem Ziel-Vorgang.
    Ueberschreibt KEINE bestehenden Verknuepfungen.
    Returns: Anzahl neu gespeicherter Vorschlaege.
    """
    gespeichert = 0
    for v in vorschlaege:
        if v.get("bereits_verknuepft"):
            continue

        result = db.execute(
            text("""
                UPDATE vorgaenge
                SET vorgaenger_id = :quelle,
                    beziehungstyp = CAST('llm_vorschlag' AS beziehungstyp),
                    konfidenz = :konf,
                    konfidenz_bestaetigt = NULL,
                    konfidenz_bestaetigt_von = NULL,
                    konfidenz_bestaetigt_am = NULL,
                    geaendert_am = NOW(),
                    geaendert_von = :ben
                WHERE id = :ziel
                  AND vorgaenger_id IS NULL
                  AND NOT geloescht
            """),
            {
                "quelle": str(vorgang_id),
                "ziel": v["ziel_id"],
                "konf": v["score"],
                "ben": benutzer_id,
            },
        )
        if result.rowcount > 0:
            gespeichert += 1

    db.commit()
    return gespeichert


def bestaetige_verknuepfung(
    db: Session, vorgang_id: UUID, benutzer_id: str
) -> bool:
    """B-002 Gate: Bestaetigt eine LLM-Verknuepfung.

    Setzt beziehungstyp von 'llm_vorschlag' auf 'ursache' und
    konfidenz_bestaetigt=TRUE.
    """
    result = db.execute(
        text("""
            UPDATE vorgaenge
            SET beziehungstyp = CAST('ursache' AS beziehungstyp),
                konfidenz_bestaetigt = TRUE,
                konfidenz_bestaetigt_von = :ben_id,
                konfidenz_bestaetigt_am = NOW(),
                geaendert_am = NOW(),
                geaendert_von = :ben_id
            WHERE id = :vid
              AND beziehungstyp = CAST('llm_vorschlag' AS beziehungstyp)
              AND NOT geloescht
        """),
        {"vid": str(vorgang_id), "ben_id": benutzer_id},
    )
    db.commit()
    return result.rowcount > 0


def lehne_verknuepfung_ab(
    db: Session, vorgang_id: UUID, benutzer_id: str
) -> bool:
    """B-002 Gate: Lehnt eine LLM-Verknuepfung ab.

    Loescht die Verknuepfung (setzt vorgaenger_id=NULL).
    """
    result = db.execute(
        text("""
            UPDATE vorgaenge
            SET vorgaenger_id = NULL,
                beziehungstyp = NULL,
                konfidenz = NULL,
                konfidenz_bestaetigt = FALSE,
                konfidenz_bestaetigt_von = :ben_id,
                konfidenz_bestaetigt_am = NOW(),
                geaendert_am = NOW(),
                geaendert_von = :ben_id
            WHERE id = :vid
              AND beziehungstyp = CAST('llm_vorschlag' AS beziehungstyp)
              AND NOT geloescht
        """),
        {"vid": str(vorgang_id), "ben_id": benutzer_id},
    )
    db.commit()
    return result.rowcount > 0


def lade_vorschlaege(db: Session, vorgang_id: UUID) -> list[dict]:
    """Laedt bestehende Verknuepfungsvorschlaege zu einem Vorgang."""
    # Vorwaerts: dieser Vorgang ist vorgaenger von anderen
    vorwaerts = db.execute(
        text("""
            SELECT v.id, v.typ::text AS typ, v.nummer, v.beschreibung,
                   v.beziehungstyp::text AS beziehungstyp, v.konfidenz,
                   v.konfidenz_bestaetigt, v.konfidenz_bestaetigt_am,
                   'vorwaerts' AS richtung
            FROM vorgaenge v
            WHERE v.vorgaenger_id = :vid AND NOT v.geloescht
            ORDER BY v.konfidenz DESC NULLS LAST
        """),
        {"vid": str(vorgang_id)},
    ).mappings().all()

    # Rueckwaerts: dieser Vorgang hat einen vorgaenger
    rueckwaerts = db.execute(
        text("""
            SELECT v2.id, v2.typ::text AS typ, v2.nummer, v2.beschreibung,
                   v.beziehungstyp::text AS beziehungstyp, v.konfidenz,
                   v.konfidenz_bestaetigt, v.konfidenz_bestaetigt_am,
                   'rueckwaerts' AS richtung
            FROM vorgaenge v
            JOIN vorgaenge v2 ON v2.id = v.vorgaenger_id
            WHERE v.id = :vid AND v.vorgaenger_id IS NOT NULL AND NOT v.geloescht
        """),
        {"vid": str(vorgang_id)},
    ).mappings().all()

    return [
        {
            "id": str(r["id"]),
            "typ": r["typ"],
            "nummer": r["nummer"],
            "beschreibung": (r["beschreibung"] or "")[:200],
            "beziehungstyp": r["beziehungstyp"],
            "konfidenz": float(r["konfidenz"]) if r["konfidenz"] else None,
            "bestaetigt": r["konfidenz_bestaetigt"],
            "bestaetigt_am": str(r["konfidenz_bestaetigt_am"]) if r["konfidenz_bestaetigt_am"] else None,
            "richtung": r["richtung"],
        }
        for r in list(vorwaerts) + list(rueckwaerts)
    ]
