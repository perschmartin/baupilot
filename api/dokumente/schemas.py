"""
Pydantic v2 Schemas für Dokumentenverwaltung (AP 1.5).
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, Field


# --- Enum-Werte als Strings (spiegeln DB-Enums) ---

DOKUMENTKATEGORIEN = [
    "nachtrag", "behinderungsanzeige", "bedenkenanzeige", "mangelanzeige",
    "protokoll", "plan", "foto", "rechnung", "vertrag", "sonstiges",
]

SIGNATURSTATUS_WERTE = [
    "nicht_signiert", "signatur_angefordert", "signiert", "signatur_ungueltig",
]


# --- Response-Schemas ---

class DokumentListeItem(BaseModel):
    id: UUID
    dateiname: str
    kategorie: str
    version_nummer: int
    mime_typ: Optional[str] = None
    dateigroesse_bytes: Optional[int] = None
    sha256_hash: Optional[str] = None
    signatur_status: str = "nicht_signiert"
    beschreibung: Optional[str] = None
    erstellt_am: Optional[datetime] = None
    erstellt_von: Optional[str] = None


class DokumentDetail(DokumentListeItem):
    projekt_id: Optional[UUID] = None
    minio_bucket: Optional[str] = None
    minio_pfad: Optional[str] = None
    vorgaenger_version_id: Optional[UUID] = None
    signiert_von: Optional[UUID] = None
    signiert_am: Optional[datetime] = None
    gesperrt: bool = False
    geaendert_am: Optional[datetime] = None
    geaendert_von: Optional[str] = None


class DokumentVersion(BaseModel):
    id: UUID
    version_nummer: int
    dateiname: str
    dateigroesse_bytes: Optional[int] = None
    sha256_hash: Optional[str] = None
    erstellt_am: Optional[datetime] = None
    erstellt_von: Optional[str] = None


class DokumentUploadResponse(BaseModel):
    id: UUID
    dateiname: str
    version_nummer: int
    sha256_hash: str
    dateigroesse_bytes: int
    kategorie: str
    duplikat_warnung: Optional[str] = None


class DokumentVerknuepfung(BaseModel):
    vorgang_id: UUID
    dokument_id: UUID
    verknuepfungstyp: str = "anlage"
    erstellt_am: Optional[datetime] = None


class DokumentStatistik(BaseModel):
    gesamt: int = 0
    nach_kategorie: dict = Field(default_factory=dict)
    gesamtgroesse_bytes: int = 0
    signiert: int = 0


# --- Request-Schemas ---

class DokumentMetadatenUpdate(BaseModel):
    kategorie: Optional[str] = None
    beschreibung: Optional[str] = None

    def validate_kategorie(self):
        if self.kategorie and self.kategorie not in DOKUMENTKATEGORIEN:
            raise ValueError(f"Ungültige Kategorie: {self.kategorie}")


class DokumentVerknuepfungErstellen(BaseModel):
    vorgang_id: UUID
    verknuepfungstyp: str = "anlage"
