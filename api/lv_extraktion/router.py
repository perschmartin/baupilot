"""
LV-Router: API-Endpunkte fuer Leistungsverzeichnisse und Positionen (AP 1.2).
KORRIGIERT: nummernkreis als int, lv_id statt leistungsverzeichnis_id.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session

from database import get_db
from auth.dependencies import get_current_user
from lv_extraktion.service import LVService
from lv_extraktion.docling_client import DoclingClient
from lv_extraktion.lv_parser import parse_lv_tables
from lv_extraktion.schemas import (
    LVDetail, LVListe, LVStatistik,
    LVPositionDetail, LVPositionenListe,
)

logger = logging.getLogger("baupilot.lv_router")

lv_router = APIRouter(prefix="/api/v1/lv", tags=["Leistungsverzeichnisse"])


@lv_router.get("/", response_model=LVListe)
def lv_auflisten(
    projekt: str = Query(default="FLI"),
    db: Session = Depends(get_db),
    benutzer=Depends(get_current_user),
):
    """Alle Leistungsverzeichnisse eines Projekts."""
    svc = LVService(db)
    items = svc.lv_liste(projekt_kurz=projekt)
    return LVListe(
        items=[LVDetail(**item) for item in items],
        gesamt=len(items),
    )


@lv_router.get("/statistik", response_model=LVStatistik)
def lv_statistik(
    projekt: str = Query(default="FLI"),
    db: Session = Depends(get_db),
    benutzer=Depends(get_current_user),
):
    """Statistik ueber alle LVs."""
    svc = LVService(db)
    stats = svc.statistik(projekt_kurz=projekt)
    return LVStatistik(**stats)


@lv_router.get("/{lv_id}")
def lv_detail(
    lv_id: str,
    db: Session = Depends(get_db),
    benutzer=Depends(get_current_user),
):
    """Ein Leistungsverzeichnis mit Details laden."""
    svc = LVService(db)
    lv = svc.lv_detail(lv_id)
    if not lv:
        raise HTTPException(status_code=404, detail="LV nicht gefunden")
    return lv


@lv_router.get("/{lv_id}/positionen", response_model=LVPositionenListe)
def lv_positionen(
    lv_id: str,
    suche: Optional[str] = Query(default=None),
    nur_positionen: bool = Query(default=False, description="Titel ausblenden"),
    db: Session = Depends(get_db),
    benutzer=Depends(get_current_user),
):
    """Positionen eines Leistungsverzeichnisses."""
    svc = LVService(db)
    lv = svc.lv_detail(lv_id)
    if not lv:
        raise HTTPException(status_code=404, detail="LV nicht gefunden")

    items = svc.positionen_liste(lv_id, suche=suche, nur_positionen=nur_positionen)
    return LVPositionenListe(
        items=[LVPositionDetail(**item) for item in items],
        gesamt=len(items),
        lv_nummer=lv.get("nummer", "?"),
    )


@lv_router.post("/extract")
def lv_extrahieren(
    datei: UploadFile = File(...),
    projekt: str = Query(default="FLI"),
    nummer: str = Query(..., description="LV-Nummer, z.B. '101'"),
    bezeichnung: str = Query(..., description="LV-Bezeichnung"),
    nummernkreis: Optional[int] = Query(default=None, description="1=100er, 2=200er, ..."),
    db: Session = Depends(get_db),
    benutzer=Depends(get_current_user),
):
    """
    Ein LV-PDF hochladen, extrahieren und Positionen speichern.
    """
    svc = LVService(db)

    # 1. LV anlegen
    klassifikation = "vs_nfd" if nummer == "211" else "intern"
    lv_id = svc.lv_anlegen(
        projekt_kurz=projekt,
        nummer=nummer,
        bezeichnung=bezeichnung,
        dateiname=datei.filename,
        nummernkreis=nummernkreis,
        klassifikation=klassifikation,
        benutzer=benutzer.get("email", "system") if isinstance(benutzer, dict) else "system",
    )

    # 2. Status: laeuft
    svc.lv_status_setzen(lv_id, "laeuft")

    try:
        # 3. PDF an spark-docling senden
        pdf_bytes = datei.file.read()
        client = DoclingClient()
        result = client.extract(pdf_bytes, filename=datei.filename)

        # 4. Tabellen parsen
        positionen = parse_lv_tables(result.get("tables", []))

        if not positionen:
            logger.warning(f"Keine Tabellen in {datei.filename}")
            svc.lv_status_setzen(lv_id, "fehler", 0)
            return {
                "lv_id": lv_id,
                "status": "fehler",
                "detail": "Keine LV-Tabellen erkannt. Manuelle Pruefung noetig.",
                "extractor": result.get("extractor", "unknown"),
                "pages": result.get("pages", 0),
            }

        # 5. Positionen speichern
        count = svc.positionen_einfuegen(
            lv_id=lv_id,
            positionen=positionen,
            extractor=result.get("extractor", "unknown"),
        )

        # 6. Status: abgeschlossen
        svc.lv_status_setzen(lv_id, "abgeschlossen", count)

        return {
            "lv_id": lv_id,
            "status": "abgeschlossen",
            "positionen": count,
            "extractor": result.get("extractor", "unknown"),
            "pages": result.get("pages", 0),
            "duration_seconds": result.get("duration_seconds", 0),
        }

    except Exception as e:
        logger.error(f"LV-Extraktion fehlgeschlagen fuer {datei.filename}: {e}")
        svc.lv_status_setzen(lv_id, "fehler")
        raise HTTPException(status_code=500, detail=f"Extraktion fehlgeschlagen: {e}")
