"""
Nachtrags-Router — API-Endpunkte fuer AP 2.1.

7-Schritte-Workflow mit LV-Abgleich, Kostenabgleich und Entscheidungsvorlage.
Schritte 5-7 erfordern Rolle projektleiter oder admin.

Endpunkte:
  GET    /nachtraege/                         — Nachtraege auflisten
  POST   /nachtraege/                         — Nachtrag manuell anlegen
  GET    /nachtraege/{id}                     — Nachtrag mit Pruefschritten
  PATCH  /nachtraege/{id}                     — Nachtrag aktualisieren
  POST   /nachtraege/{id}/schritt/{nr}        — Pruefschritt abschliessen
  POST   /nachtraege/{id}/lv-abgleich         — LV-Abgleich (Schritt 2)
  POST   /nachtraege/{id}/kostenabgleich      — Kostenabgleich (Schritt 3)
  POST   /nachtraege/{id}/entscheidungsvorlage — Vorlage generieren (Schritt 4)
  POST   /nachtraege/{id}/ki-bestaetigung/{nr} — KI-Ergebnis bestaetigen/ablehnen
  POST   /nachtraege/{id}/entscheidung        — Variante A/B/C (Schritt 6)
  POST   /entscheidungsvorlagen/{id}/freigeben — Vorlage freigeben
  GET    /nachtraege/{id}/vorlagen            — Vorlagen eines Nachtrags
"""

from __future__ import annotations

import logging
from uuid import UUID

from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth.dependencies import CurrentUser, get_current_user
from database import get_db

from nachtraege.schemas import (
    NachtragErstellen,
    NachtragAktualisieren,
    NachtragResponse,
    NachtragDetailResponse,
    NachtraegeListe,
    PruefschrittAbschliessen,
    KiBestaetigung,
    LVAbgleichResponse,
    KostenabgleichResponse,
    EntscheidungsvorlageResponse,
    VorlageFreigabe,
)
from nachtraege.service import NachtragsError, NachtragsService
from nachtraege.lv_abgleich import LVAbgleichService
from nachtraege.kostenabgleich import KostenabgleichService
from nachtraege.entscheidungsvorlage import EntscheidungsvorlageService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/nachtraege", tags=["nachtraege"])


def _get_service(db: Session = Depends(get_db), user: dict = Depends(get_current_user)) -> NachtragsService:
    return NachtragsService(db=db, mandant_slug=user.get("mandant_slug", ""))


def _benutzer_name(user: dict) -> str:
    return f"{user.get('vorname', '')} {user.get('nachname', '')}".strip() or user.get("email", "unbekannt")


def _benutzer_rollen(db: Session, user_id: str) -> set[str]:
    result = db.execute(
        text("SELECT rolle FROM shared.benutzer_projekt_rollen WHERE benutzer_id = :bid"),
        {"bid": user_id},
    )
    return {r[0] for r in result.all()}


# ===================================================================
# NACHTRAEGE AUFLISTEN
# ===================================================================

@router.get("/", response_model=NachtraegeListe)
def nachtraege_liste(
    user: CurrentUser,
    service: NachtragsService = Depends(_get_service),
    status: str | None = Query(default=None),
    lv_id: UUID | None = Query(default=None),
    kostengruppe: str | None = Query(default=None),
    suche: str | None = Query(default=None),
    projekt: str = Query(default="FLI"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """Nachtraege eines Projekts auflisten mit Filtern und Summen."""
    try:
        return service.liste_nachtraege(
            projekt_kurz=projekt,
            status=status,
            lv_id=lv_id,
            kostengruppe=kostengruppe,
            suche=suche,
            limit=limit,
            offset=offset,
        )
    except NachtragsError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


# ===================================================================
# NACHTRAG ERSTELLEN
# ===================================================================

@router.post("/", response_model=NachtragResponse, status_code=201)
def nachtrag_erstellen(
    body: NachtragErstellen,
    user: CurrentUser,
    service: NachtragsService = Depends(_get_service),
    projekt: str = Query(default="FLI"),
):
    """Neuen Nachtrag manuell anlegen."""
    try:
        return service.erstelle_nachtrag(
            projekt_kurz=projekt,
            gegenstand=body.gegenstand,
            erstellt_von_id=UUID(user["sub"]),
            erstellt_von_name=_benutzer_name(user),
            beschreibung=body.beschreibung,
            betrag_gefordert=body.betrag_gefordert,
            zeitauswirkung_tage=body.zeitauswirkung_tage,
            qualitaetsauswirkung=body.qualitaetsauswirkung,
            lv_id=body.lv_id,
            kostengruppe_din276=body.kostengruppe_din276,
            verantwortlich_firma_id=body.verantwortlich_firma_id,
        )
    except NachtragsError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


# ===================================================================
# NACHTRAG DETAIL
# ===================================================================

@router.get("/{nachtrag_id}", response_model=NachtragDetailResponse)
def nachtrag_detail(
    nachtrag_id: UUID,
    user: CurrentUser,
    service: NachtragsService = Depends(_get_service),
):
    """Nachtrag mit 7-Schritte-Workflow laden."""
    try:
        return service.lade_nachtrag(nachtrag_id)
    except NachtragsError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


# ===================================================================
# NACHTRAG AKTUALISIEREN
# ===================================================================

@router.patch("/{nachtrag_id}", response_model=NachtragDetailResponse)
def nachtrag_aktualisieren(
    nachtrag_id: UUID,
    body: NachtragAktualisieren,
    user: CurrentUser,
    service: NachtragsService = Depends(_get_service),
):
    """Nachtrag-Felder aktualisieren."""
    felder = body.model_dump(exclude_unset=True)
    if not felder:
        raise HTTPException(status_code=400, detail="Keine Felder zum Aktualisieren.")
    try:
        return service.aktualisiere_nachtrag(
            nachtrag_id=nachtrag_id,
            benutzer_id=UUID(user["sub"]),
            benutzer_name=_benutzer_name(user),
            **felder,
        )
    except NachtragsError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


# ===================================================================
# PRUEFSCHRITT ABSCHLIESSEN
# ===================================================================

@router.post("/{nachtrag_id}/schritt/{schritt_nr}", response_model=NachtragDetailResponse)
def schritt_abschliessen(
    nachtrag_id: UUID,
    schritt_nr: int,
    body: PruefschrittAbschliessen,
    user: CurrentUser,
    db: Session = Depends(get_db),
    service: NachtragsService = Depends(_get_service),
):
    """Einen Pruefschritt manuell abschliessen."""
    rollen = _benutzer_rollen(db, user["sub"])
    try:
        return service.schritt_abschliessen(
            nachtrag_id=nachtrag_id,
            schritt_nr=schritt_nr,
            benutzer_id=user["sub"],
            benutzer_name=_benutzer_name(user),
            ergebnis=body.ergebnis,
            benutzer_rollen=rollen,
        )
    except NachtragsError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


# ===================================================================
# LV-ABGLEICH (Schritt 2)
# ===================================================================

@router.post("/{nachtrag_id}/lv-abgleich", response_model=LVAbgleichResponse)
def lv_abgleich(
    nachtrag_id: UUID,
    user: CurrentUser,
    db: Session = Depends(get_db),
    service: NachtragsService = Depends(_get_service),
    suchbegriff: str | None = Query(default=None),
):
    """LV-Abgleich durchfuehren und Ergebnis als KI-Ergebnis speichern."""
    lv_svc = LVAbgleichService(db=db, mandant_slug=user.get("mandant_slug", ""))
    ergebnis = lv_svc.abgleich(vorgang_id=nachtrag_id, suchbegriff=suchbegriff)

    # KI-Ergebnis an Schritt 2 speichern
    try:
        service.ki_ergebnis_speichern(
            nachtrag_id=nachtrag_id,
            schritt_nr=2,
            benutzer_id=user["sub"],
            ki_eingabe={"suchbegriff": ergebnis.get("suchbegriff", "")},
            ki_ergebnis=ergebnis,
            ki_konfidenz=0.8 if ergebnis.get("anzahl_treffer", 0) > 0 else 0.2,
        )
    except NachtragsError as e:
        logger.warning(f"KI-Ergebnis konnte nicht gespeichert werden: {e}")

    return ergebnis


# ===================================================================
# KOSTENABGLEICH (Schritt 3)
# ===================================================================

@router.post("/{nachtrag_id}/kostenabgleich", response_model=KostenabgleichResponse)
def kostenabgleich(
    nachtrag_id: UUID,
    user: CurrentUser,
    db: Session = Depends(get_db),
    service: NachtragsService = Depends(_get_service),
):
    """Kostenabgleich gegen LV-Preise und BKI-Baupreise."""
    # Zuerst LV-Treffer holen (falls vorhanden)
    lv_svc = LVAbgleichService(db=db, mandant_slug=user.get("mandant_slug", ""))
    lv_ergebnis = lv_svc.abgleich(vorgang_id=nachtrag_id)

    kosten_svc = KostenabgleichService(db=db, mandant_slug=user.get("mandant_slug", ""))
    ergebnis = kosten_svc.abgleich(
        vorgang_id=nachtrag_id,
        lv_treffer=lv_ergebnis.get("treffer"),
    )

    # KI-Ergebnis an Schritt 3 speichern
    try:
        service.ki_ergebnis_speichern(
            nachtrag_id=nachtrag_id,
            schritt_nr=3,
            benutzer_id=user["sub"],
            ki_eingabe={"betrag_gefordert": ergebnis.get("betrag_gefordert")},
            ki_ergebnis=ergebnis,
            ki_konfidenz=0.7 if ergebnis.get("vergleiche") else 0.1,
        )
    except NachtragsError as e:
        logger.warning(f"KI-Ergebnis konnte nicht gespeichert werden: {e}")

    return ergebnis


# ===================================================================
# ENTSCHEIDUNGSVORLAGE (Schritt 4)
# ===================================================================

@router.post("/{nachtrag_id}/entscheidungsvorlage", response_model=EntscheidungsvorlageResponse)
def entscheidungsvorlage_generieren(
    nachtrag_id: UUID,
    user: CurrentUser,
    db: Session = Depends(get_db),
    service: NachtragsService = Depends(_get_service),
):
    """Entscheidungsvorlage generieren (LLM-Aufruf)."""
    # Kontext aus Schritt 2+3 laden
    lv_svc = LVAbgleichService(db=db, mandant_slug=user.get("mandant_slug", ""))
    lv_ergebnis = lv_svc.abgleich(vorgang_id=nachtrag_id)

    kosten_svc = KostenabgleichService(db=db, mandant_slug=user.get("mandant_slug", ""))
    kosten_ergebnis = kosten_svc.abgleich(
        vorgang_id=nachtrag_id,
        lv_treffer=lv_ergebnis.get("treffer"),
    )

    ev_svc = EntscheidungsvorlageService(db=db, mandant_slug=user.get("mandant_slug", ""))
    try:
        ergebnis = ev_svc.generiere(
            vorgang_id=nachtrag_id,
            erstellt_von_id=user["sub"],
            lv_abgleich=lv_ergebnis,
            kostenabgleich=kosten_ergebnis,
        )

        # KI-Ergebnis an Schritt 4 speichern
        service.ki_ergebnis_speichern(
            nachtrag_id=nachtrag_id,
            schritt_nr=4,
            benutzer_id=user["sub"],
            ki_eingabe={"nachtrag_id": str(nachtrag_id)},
            ki_ergebnis={"vorlage_id": str(ergebnis["id"]), "version": ergebnis["version"]},
            ki_konfidenz=0.6,
        )

        return ergebnis

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Vorlage konnte nicht generiert werden: {e}")


# ===================================================================
# KI-BESTAETIGUNG
# ===================================================================

@router.post("/{nachtrag_id}/ki-bestaetigung/{schritt_nr}", response_model=NachtragDetailResponse)
def ki_bestaetigung(
    nachtrag_id: UUID,
    schritt_nr: int,
    body: KiBestaetigung,
    user: CurrentUser,
    service: NachtragsService = Depends(_get_service),
):
    """KI-Ergebnis bestaetigen oder ablehnen (menschliches Gate, B-002)."""
    try:
        return service.ki_bestaetigen(
            nachtrag_id=nachtrag_id,
            schritt_nr=schritt_nr,
            benutzer_id=user["sub"],
            bestaetigt=body.bestaetigt,
            kommentar=body.kommentar,
        )
    except NachtragsError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


# ===================================================================
# ENTSCHEIDUNG (Schritt 6)
# ===================================================================

@router.post("/{nachtrag_id}/entscheidung", response_model=NachtragDetailResponse)
def entscheidung(
    nachtrag_id: UUID,
    user: CurrentUser,
    db: Session = Depends(get_db),
    service: NachtragsService = Depends(_get_service),
    variante: str = Query(pattern=r"^[ABC]$"),
    betrag_genehmigt: float | None = Query(default=None),
    kommentar: str | None = Query(default=None),
    begruendung_grund: str | None = Query(default=None),
    begruendung_hoehe: str | None = Query(default=None),
):
    """Entscheidung treffen: A (genehmigt), B (teilweise), C (abgelehnt).

    NT-F-04: begruendung_grund und begruendung_hoehe werden in nachtragspruefung
    (Schritt 6) abgelegt. Die BOOL-Felder entscheidung_grund/hoehe werden aus
    der Variante abgeleitet. Siehe service.entscheidung_treffen Docstring.
    """
    rollen = _benutzer_rollen(db, user["sub"])
    if not rollen.intersection({"projektleiter", "admin"}):
        raise HTTPException(status_code=403, detail="Entscheidung erfordert Rolle 'projektleiter' oder 'admin'.")

    try:
        return service.entscheidung_treffen(
            nachtrag_id=nachtrag_id,
            variante=variante,
            benutzer_id=user["sub"],
            benutzer_name=_benutzer_name(user),
            betrag_genehmigt=betrag_genehmigt,
            kommentar=kommentar,
            begruendung_grund=begruendung_grund,
            begruendung_hoehe=begruendung_hoehe,
        )
    except NachtragsError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


# ===================================================================
# VORLAGEN FREIGEBEN
# ===================================================================

@router.post("/vorlagen/{vorlage_id}/freigeben", response_model=EntscheidungsvorlageResponse)
def vorlage_freigeben(
    vorlage_id: UUID,
    user: CurrentUser,
    db: Session = Depends(get_db),
):
    """Entscheidungsvorlage freigeben (nur PL/Admin)."""
    rollen = _benutzer_rollen(db, user["sub"])
    if not rollen.intersection({"projektleiter", "admin"}):
        raise HTTPException(status_code=403, detail="Freigabe erfordert Rolle 'projektleiter' oder 'admin'.")

    ev_svc = EntscheidungsvorlageService(db=db, mandant_slug=user.get("mandant_slug", ""))
    try:
        return ev_svc.freigeben(vorlage_id=vorlage_id, freigegeben_von_id=user["sub"])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ===================================================================
# VORLAGEN EINES NACHTRAGS
# ===================================================================

@router.get("/{nachtrag_id}/vorlagen")
def vorlagen_liste(
    nachtrag_id: UUID,
    user: CurrentUser,
    db: Session = Depends(get_db),
):
    """Alle Entscheidungsvorlagen eines Nachtrags laden."""
    ev_svc = EntscheidungsvorlageService(db=db, mandant_slug=user.get("mandant_slug", ""))
    return {"vorlagen": ev_svc.lade_vorlagen(vorgang_id=nachtrag_id)}


# ===================================================================
# PROTOKOLLGENERIERUNG (AP 2.5, Roadmap E12)
# ===================================================================

@router.get("/{nachtrag_id}/protokoll")
def protokoll_herunterladen(
    nachtrag_id: UUID,
    user: CurrentUser,
    service: NachtragsService = Depends(_get_service),
):
    """Pruefprotokoll als Word-Dokument (.docx) erzeugen und streamen.

    Liefert den fertig gerenderten 1-Pager mit Stammdaten, Dreiklang Q/Z/K,
    7-Schritte-Pruefablauf, getrennter Entscheidung Grund/Hoehe (NT-F-04)
    und NTV-Verknuepfung (NT-F-05). Reine Datenwiedergabe — G1 konform,
    keine Interpretation oder Wertung im Text.

    Quelle: NachtragsService.lade_nachtrag() liefert ein Dict, das direkt
    an protokolle.render_nachtrag_protokoll uebergeben wird.
    """
    from protokolle import render_nachtrag_protokoll

    try:
        nt = service.lade_nachtrag(nachtrag_id)
    except NachtragsError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    doc = render_nachtrag_protokoll(nt)

    # In-Memory-Buffer — kein Disk-Schreiben, damit Protokolle nirgendwo
    # ausserhalb der DB zwischengelagert werden (G7).
    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)

    dateiname = f"Protokoll-{nt.get('nummer', 'NT')}.docx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{dateiname}"'},
    )
