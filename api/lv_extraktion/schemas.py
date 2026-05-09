"""Pydantic v2 Schemas fuer LV-Extraktion (AP 1.2). KORRIGIERT: lv_id, nummernkreis als int."""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# --- LV (Leistungsverzeichnis) ---

class LVBasis(BaseModel):
    nummer: str = Field(..., description="LV-Nummer, z.B. '101'")
    bezeichnung: str = Field(..., description="Bezeichnung des LV")
    nummernkreis: Optional[int] = Field(None, description="1=100er, 2=200er, ...")
    klassifikation: Optional[str] = Field(default="intern")


class LVDetail(LVBasis):
    id: UUID
    projekt_id: UUID
    dateiname: Optional[str] = None
    positionen_anzahl: Optional[int] = 0
    extraktion_status: Optional[str] = "ausstehend"
    erstellt_am: Optional[datetime] = None


class LVListe(BaseModel):
    items: list[LVDetail]
    gesamt: int


class LVStatistik(BaseModel):
    lv_gesamt: int
    positionen_gesamt: int
    extrahiert: int
    ausstehend: int
    fehler: int


# --- LV-Position ---

class LVPositionDetail(BaseModel):
    id: UUID
    lv_id: UUID
    oz: Optional[str] = None
    kurztext: Optional[str] = None
    langtext: Optional[str] = None
    menge: Optional[Decimal] = None
    einheit: Optional[str] = None
    einheitspreis: Optional[Decimal] = None
    gesamtpreis: Optional[Decimal] = None
    hierarchie_ebene: Optional[int] = 0
    ist_titel: Optional[bool] = False
    extrahiert_am: Optional[datetime] = None
    extrahiert_mit: Optional[str] = None


class LVPositionenListe(BaseModel):
    items: list[LVPositionDetail]
    gesamt: int
    lv_nummer: str
