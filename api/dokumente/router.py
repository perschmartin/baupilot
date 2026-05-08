"""
Dokumente-Router (AP 1.5).
FastAPI-Endpunkte für Upload, Download, Versionierung, Verknüpfung.
"""

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from io import BytesIO

from database import get_db
from auth.dependencies import get_current_user
from .service import DokumenteService

router = APIRouter(prefix="/api/v1/dokumente", tags=["Dokumente"])


def get_service(db: Session = Depends(get_db)) -> DokumenteService:
    return DokumenteService(db)


# ----------------------------------------------------------------
# Liste & Detail
# ----------------------------------------------------------------
@router.get("/")
def dokumente_liste(
    projekt: str = "FLI",
    kategorie: Optional[str] = None,
    suche: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    current_user: dict = Depends(get_current_user),
    svc: DokumenteService = Depends(get_service),
):
    """Dokumente auflisten mit optionalen Filtern."""
    return svc.liste(projekt, kategorie, suche, limit, offset)


@router.get("/statistik")
def dokumente_statistik(
    projekt: str = "FLI",
    current_user: dict = Depends(get_current_user),
    svc: DokumenteService = Depends(get_service),
):
    """Dokumentenstatistik pro Projekt."""
    return svc.statistik(projekt)


@router.get("/{dokument_id}")
def dokument_detail(
    dokument_id: str,
    current_user: dict = Depends(get_current_user),
    svc: DokumenteService = Depends(get_service),
):
    """Einzelnes Dokument mit Metadaten."""
    result = svc.detail(dokument_id)
    if not result:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden")
    return result


@router.get("/{dokument_id}/versionen")
def dokument_versionen(
    dokument_id: str,
    current_user: dict = Depends(get_current_user),
    svc: DokumenteService = Depends(get_service),
):
    """Alle Versionen eines Dokuments."""
    return svc.versionen(dokument_id)


# ----------------------------------------------------------------
# Upload
# ----------------------------------------------------------------
@router.post("/upload", status_code=201)
def dokument_upload(
    datei: UploadFile = File(...),
    projekt: str = Form("FLI"),
    kategorie: str = Form("sonstiges"),
    beschreibung: Optional[str] = Form(None),
    vorgang_id: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user),
    svc: DokumenteService = Depends(get_service),
):
    """Dokument hochladen (multipart/form-data)."""
    datei_bytes = datei.file.read()
    mime_typ = datei.content_type or "application/octet-stream"
    dateiname = datei.filename or "unbenannt"

    result = svc.upload(
        datei_bytes=datei_bytes,
        dateiname=dateiname,
        mime_typ=mime_typ,
        projekt_kurz=projekt,
        kategorie=kategorie,
        beschreibung=beschreibung,
        vorgang_id=vorgang_id,
        mandant_slug=current_user.get("mandant_slug", "tlbv"),
        benutzer_email=current_user.get("email", "system"),
    )

    if "fehler" in result:
        code_map = {
            "mime_typ_nicht_erlaubt": 415,
            "datei_zu_gross": 413,
            "projekt_nicht_gefunden": 404,
            "minio_upload_fehler": 500,
        }
        raise HTTPException(
            status_code=code_map.get(result["fehler"], 400),
            detail=result["detail"],
        )

    return result


@router.post("/{dokument_id}/version", status_code=201)
def dokument_neue_version(
    dokument_id: str,
    datei: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    svc: DokumenteService = Depends(get_service),
):
    """Neue Version eines bestehenden Dokuments hochladen."""
    datei_bytes = datei.file.read()
    mime_typ = datei.content_type or "application/octet-stream"
    dateiname = datei.filename or "unbenannt"

    result = svc.neue_version(
        dokument_id=dokument_id,
        datei_bytes=datei_bytes,
        dateiname=dateiname,
        mime_typ=mime_typ,
        mandant_slug=current_user.get("mandant_slug", "tlbv"),
        benutzer_email=current_user.get("email", "system"),
    )

    if "fehler" in result:
        code_map = {
            "nicht_gefunden": 404,
            "gesperrt": 403,
            "mime_typ_nicht_erlaubt": 415,
            "datei_zu_gross": 413,
            "minio_upload_fehler": 500,
        }
        raise HTTPException(
            status_code=code_map.get(result["fehler"], 400),
            detail=result["detail"],
        )

    return result


# ----------------------------------------------------------------
# Download
# ----------------------------------------------------------------
@router.get("/{dokument_id}/download")
def dokument_download(
    dokument_id: str,
    current_user: dict = Depends(get_current_user),
    svc: DokumenteService = Depends(get_service),
):
    """Datei herunterladen (Streaming-Response)."""
    data, dateiname, mime_typ = svc.download(dokument_id)

    if data is None:
        raise HTTPException(status_code=404, detail=dateiname)  # dateiname enthält Fehlermeldung

    return StreamingResponse(
        BytesIO(data),
        media_type=mime_typ or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{dateiname}"'},
    )


# ----------------------------------------------------------------
# Verknüpfung
# ----------------------------------------------------------------
@router.post("/{dokument_id}/verknuepfen")
def dokument_verknuepfen(
    dokument_id: str,
    vorgang_id: str = Form(...),
    verknuepfungstyp: str = Form("anlage"),
    current_user: dict = Depends(get_current_user),
    svc: DokumenteService = Depends(get_service),
):
    """Dokument an einen Vorgang verknüpfen."""
    return svc.verknuepfen(
        dokument_id=dokument_id,
        vorgang_id=vorgang_id,
        verknuepfungstyp=verknuepfungstyp,
        benutzer=current_user.get("email", "system"),
    )


@router.get("/vorgang/{vorgang_id}")
def vorgang_dokumente(
    vorgang_id: str,
    current_user: dict = Depends(get_current_user),
    svc: DokumenteService = Depends(get_service),
):
    """Alle Dokumente eines Vorgangs."""
    return svc.vorgang_dokumente(vorgang_id)


# ----------------------------------------------------------------
# Update & Delete
# ----------------------------------------------------------------
@router.patch("/{dokument_id}")
def dokument_metadaten_update(
    dokument_id: str,
    kategorie: Optional[str] = Form(None),
    beschreibung: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user),
    svc: DokumenteService = Depends(get_service),
):
    """Metadaten aktualisieren (Kategorie, Beschreibung)."""
    result = svc.metadaten_update(
        dokument_id=dokument_id,
        kategorie=kategorie,
        beschreibung=beschreibung,
        benutzer=current_user.get("email", "system"),
    )

    if not result:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden")
    if "fehler" in result:
        raise HTTPException(status_code=403, detail=result["detail"])

    return result


@router.delete("/{dokument_id}")
def dokument_loeschen(
    dokument_id: str,
    current_user: dict = Depends(get_current_user),
    svc: DokumenteService = Depends(get_service),
):
    """Dokument soft-löschen."""
    result = svc.soft_delete(
        dokument_id=dokument_id,
        benutzer=current_user.get("email", "system"),
    )

    if not result:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden")
    if "fehler" in result:
        raise HTTPException(status_code=403, detail=result["detail"])

    return result
