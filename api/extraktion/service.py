"""Extraktor-Service: PDF -> pdfplumber -> LLM -> strukturiertes JSON.

Reine Pipeline-Funktion ohne FastAPI-Spezifika. Wird vom Router aufgerufen,
um das Heavy-Lifting (MinIO-Download, PDF-Text, LLM-Call) zu kapseln.

Verifiziert in Sandbox:
  C:\\Tools\\claude-sandbox\\bp-extraktor\\test_extraktion.py
"""

from __future__ import annotations

import io
import json
import logging
from typing import Any
from uuid import UUID

import httpx
import pdfplumber
from minio import Minio
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import settings

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """Du bist BauPilot-Extraktor fuer Stoerungs-Schreiben im oeffentlichen Hochbau (VOB/B).
Deine Aufgabe: aus dem uebergebenen Dokument strukturierte Felder extrahieren.

STRIKTE REGELN:
- Antworte AUSSCHLIESSLICH mit einem validen JSON-Objekt. Kein Vorspann, kein Nachsatz, kein Markdown.
- Wenn ein Feld nicht eindeutig aus dem Text hervorgeht, setze null. KEINE Halluzinationen.
- Keine Wertungen, keine Schuldzuweisungen (G1).
- Datum im Format YYYY-MM-DD.
- Betraege in EUR als Zahl (ohne Tausenderpunkt, mit Dezimalpunkt).
- Zeitauswirkungen in Arbeitstagen als Integer.

ZIELFORMAT (exakt diese Schluessel, kein anderes):
{
  "beschreibung": "1-3 Saetze, was die Stoerung sachlich ist",
  "verantwortliche_firma": "Firma, die das Schreiben verfasst hat (z.B. AGE, BWP, HTI, ARGE FLI)",
  "empfaenger": "Firma/Person, an die das Schreiben adressiert ist",
  "datum_dokument": "YYYY-MM-DD oder null",
  "betroffene_lv_position": "LV-Nummer und/oder OZ, z.B. 'LV 209' oder null",
  "betroffenes_bauteil": "Gebaeudeabschnitt 30/31/32/33/34 oder 'Aussenanlagen' oder null",
  "auswirkung_kosten_eur": null oder Zahl,
  "auswirkung_zeit_arbeitstage": null oder Integer,
  "auswirkung_qualitaet": "Freitext oder null",
  "konfidenz": 0.0 bis 1.0 — wie sicher bist du dir bei der Extraktion insgesamt
}
"""


class ExtraktionError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


def _minio_client() -> Minio:
    """MinIO-Client aus den Config-Werten (Container-interner Hostname)."""
    return Minio(
        f"{settings.minio_host}:{settings.minio_api_port}",
        access_key=settings.minio_root_user,
        secret_key=settings.minio_root_password,
        secure=False,
    )


def lade_pdf_text(db: Session, vorgang_id: UUID) -> tuple[str, dict[str, Any]]:
    """Laed das erste verknuepfte PDF eines Vorgangs aus MinIO und extrahiert Text.

    Returns:
        Tupel (text, meta) mit:
        - text: Volltext aller Seiten
        - meta: dict mit dokument_id, dateiname, seiten, bytes — fuer Audit-Trail
    """
    row = db.execute(
        text("""
            SELECT d.id, d.dateiname, d.minio_bucket, d.minio_pfad, d.dateigroesse_bytes
            FROM dokumente d
            JOIN vorgang_dokumente vd ON vd.dokument_id = d.id
            WHERE vd.vorgang_id = :vid AND NOT d.geloescht
            ORDER BY d.erstellt_am ASC
            LIMIT 1
        """),
        {"vid": str(vorgang_id)},
    ).mappings().first()
    if not row:
        raise ExtraktionError("Kein verknuepftes Dokument am Vorgang.", 404)

    client = _minio_client()
    try:
        response = client.get_object(row["minio_bucket"], row["minio_pfad"])
        pdf_bytes = response.read()
        response.close()
        response.release_conn()
    except Exception as e:
        raise ExtraktionError(f"MinIO-Download fehlgeschlagen: {e}", 500)

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        seiten = []
        for s in pdf.pages:
            seiten.append(s.extract_text() or "")
        voller_text = "\n\n".join(seiten)
        meta = {
            "dokument_id": str(row["id"]),
            "dateiname": row["dateiname"],
            "seiten": len(pdf.pages),
            "bytes": len(pdf_bytes),
        }
    return voller_text, meta


def llm_extrahiere(text_input: str, max_chars: int = 8000) -> dict[str, Any]:
    """Sendet den Text an LiteLLM/Qwen und parst die JSON-Antwort.

    Returns:
        Dict mit den ZIELFORMAT-Feldern. Bei JSON-Parse-Fehler wird eine
        ExtraktionError geworfen.
    """
    # Lange Dokumente kuerzen — sonst Token-Overflow. Spaeter chunken.
    kurz_text = text_input[:max_chars]

    payload = {
        "model": "qwen-32b",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"DOKUMENT-TEXT:\n\n{kurz_text}"},
        ],
        "temperature": 0.1,
        "max_tokens": 800,
    }

    url = f"http://{settings.litellm_host}:{settings.litellm_port}/v1/chat/completions"
    with httpx.Client(timeout=180) as http:
        r = http.post(url, json=payload)
        if r.status_code != 200:
            raise ExtraktionError(f"LLM-Aufruf fehlgeschlagen: HTTP {r.status_code} {r.text[:300]}", 502)
        data = r.json()

    llm_text = data["choices"][0]["message"]["content"].strip()
    cleaned = _bereinige_json_block(llm_text)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ExtraktionError(f"LLM-Antwort kein valides JSON: {e}; roh: {llm_text[:300]}", 502)

    return parsed


def _bereinige_json_block(s: str) -> str:
    """Manche Modelle wickeln das JSON in ```json ... ``` ein oder packen
    Text drumherum. Wir extrahieren das erste {...}-Block.
    """
    if s.startswith("```"):
        s = s.strip("`")
        if s.lower().startswith("json"):
            s = s[4:]
        s = s.strip()
    i = s.find("{")
    j = s.rfind("}")
    if i >= 0 and j > i:
        s = s[i:j + 1]
    return s


def speichere_ergebnis_in_pruefschritt(
    db: Session,
    vorgang_id: UUID,
    typ: str,
    extrahiert: dict[str, Any],
    eingabe_meta: dict[str, Any],
    benutzer_id: str,
) -> None:
    """Persistiert das LLM-Ergebnis im Pruefschritt 1 (Erfassung) der jeweiligen
    Stoerungspruefung-Tabelle. So bleibt die KI-Spur im Audit-Trail (G2).

    typ ∈ {behinderungsanzeige, bedenkenanzeige, mangelanzeige}
    """
    tabelle = {
        "behinderungsanzeige": "behinderungspruefung",
        "bedenkenanzeige": "bedenkenpruefung",
        "mangelanzeige": "mangelpruefung",
        "nachtrag": "nachtragspruefung",
    }.get(typ)
    if not tabelle:
        raise ExtraktionError(f"Unbekannter Vorgangstyp: {typ}", 400)

    # ki_eingabe enthaelt den Audit-Trail (welches Dokument, wie viel Text),
    # ki_ergebnis das strukturierte LLM-Ergebnis. Beide JSONB.
    db.execute(
        text(f"""
            UPDATE {tabelle}
            SET ki_eingabe = CAST(:in AS jsonb),
                ki_ergebnis = CAST(:out AS jsonb),
                ki_konfidenz = :konf,
                ki_bestaetigt = NULL,
                geaendert_am = NOW(),
                geaendert_von = :ben
            WHERE vorgang_id = :vid AND schritt = 1
        """),
        {
            "vid": str(vorgang_id),
            "in": json.dumps({
                "modell": "qwen-32b",
                "system_prompt_version": 1,
                "dokument": eingabe_meta,
                "max_chars": 8000,
            }),
            "out": json.dumps(extrahiert),
            "konf": float(extrahiert.get("konfidenz") or 0.0),
            "ben": benutzer_id,
        },
    )
    db.commit()


def uebernehme_in_vorgang(
    db: Session,
    vorgang_id: UUID,
    extrahiert: dict[str, Any],
    benutzer_name: str,
) -> None:
    """Bei User-Bestaetigung: ausgewaehlte Felder aus dem LLM-Vorschlag in die
    vorgaenge-Tabelle uebernehmen.

    Nur Felder, die im Vorschlag nicht null sind, werden geschrieben. Bestehende
    Werte werden NICHT ueberschrieben (Schutz vor versehentlichem Overwrite —
    Anwender muss eine vorhandene Beschreibung manuell loeschen, wenn er sie
    durch die KI-Version ersetzen will).
    """
    set_parts: list[str] = []
    params: dict[str, Any] = {"vid": str(vorgang_id), "ben": benutzer_name}

    # Den Vorgangstyp brauchen wir fuer das Mapping NT-spezifischer Felder.
    typ_row = db.execute(
        text("SELECT typ::text FROM vorgaenge WHERE id = :vid"),
        {"vid": str(vorgang_id)},
    ).first()
    typ = typ_row[0] if typ_row else None

    if extrahiert.get("beschreibung"):
        set_parts.append("beschreibung = COALESCE(beschreibung, :besch)")
        params["besch"] = extrahiert["beschreibung"]
    if extrahiert.get("auswirkung_kosten_eur") is not None:
        if typ == "nachtrag":
            # Nachtraege haben betrag_gefordert statt kosten_eur (Migration 007)
            set_parts.append("betrag_gefordert = COALESCE(betrag_gefordert, :k)")
        else:
            set_parts.append("kosten_eur = COALESCE(kosten_eur, :k)")
        params["k"] = float(extrahiert["auswirkung_kosten_eur"])
    if extrahiert.get("auswirkung_zeit_arbeitstage") is not None:
        if typ == "nachtrag":
            set_parts.append("zeitauswirkung_tage = COALESCE(zeitauswirkung_tage, :z)")
        else:
            set_parts.append("zeit_arbeitstage = COALESCE(zeit_arbeitstage, :z)")
        params["z"] = int(extrahiert["auswirkung_zeit_arbeitstage"])
    if extrahiert.get("auswirkung_qualitaet"):
        if typ == "nachtrag":
            set_parts.append("qualitaetsauswirkung = COALESCE(qualitaetsauswirkung, :q)")
        else:
            set_parts.append("qualitaet_bewertung = COALESCE(qualitaet_bewertung, :q)")
        params["q"] = extrahiert["auswirkung_qualitaet"]

    if not set_parts:
        return  # nichts zu uebernehmen

    set_parts.extend(["geaendert_am = NOW()", "geaendert_von = :ben"])
    sql = f"UPDATE vorgaenge SET {', '.join(set_parts)} WHERE id = :vid"
    db.execute(text(sql), params)
    # KI-Bestaetigt-Flag im Pruefschritt 1 aller Pruefungs-Tabellen setzen.
    # Nur eine Tabelle hat die passende Zeile — die anderen UPDATEs sind No-Op.
    db.execute(
        text("""
            UPDATE behinderungspruefung SET ki_bestaetigt = TRUE, ki_bestaetigt_von = (
                SELECT id FROM shared.benutzer WHERE email = 'admin@baupilot.de' LIMIT 1
            ), ki_bestaetigt_am = NOW() WHERE vorgang_id = :vid AND schritt = 1;
            UPDATE bedenkenpruefung SET ki_bestaetigt = TRUE, ki_bestaetigt_von = (
                SELECT id FROM shared.benutzer WHERE email = 'admin@baupilot.de' LIMIT 1
            ), ki_bestaetigt_am = NOW() WHERE vorgang_id = :vid AND schritt = 1;
            UPDATE mangelpruefung SET ki_bestaetigt = TRUE, ki_bestaetigt_von = (
                SELECT id FROM shared.benutzer WHERE email = 'admin@baupilot.de' LIMIT 1
            ), ki_bestaetigt_am = NOW() WHERE vorgang_id = :vid AND schritt = 1;
            UPDATE nachtragspruefung SET ki_bestaetigt = TRUE, ki_bestaetigt_von = (
                SELECT id FROM shared.benutzer WHERE email = 'admin@baupilot.de' LIMIT 1
            ), ki_bestaetigt_am = NOW() WHERE vorgang_id = :vid AND schritt = 1;
        """),
        {"vid": str(vorgang_id)},
    )
    db.commit()
