"""Pydantic-Schemas fuer Benachrichtigungs-Endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


# Werte des benachrichtigungstyp-Enums aus Migration 008
TypLiteral = Literal[
    "aufgabe_ueberfaellig",
    "beha_erinnerung",
    "neuer_vorgang",
    "entscheidung_ausstehend",
    "doppelbeauftragung",
    "system",
]

PrioritaetLiteral = Literal["info", "hinweis", "warnung"]


class BenachrichtigungResponse(BaseModel):
    id: UUID
    benutzer_id: UUID
    vorgang_id: UUID | None = None
    typ: TypLiteral
    prioritaet: PrioritaetLiteral
    titel: str
    inhalt: str
    gelesen: bool = False
    gelesen_am: datetime | None = None
    erstellt_am: datetime


class BenachrichtigungenListe(BaseModel):
    benachrichtigungen: list[BenachrichtigungResponse]
    gesamt: int
    ungelesen: int


class UngelesenAntwort(BaseModel):
    """Leichtgewichtige Antwort fuer Polling-Anwendungen (Badge)."""
    ungelesen: int
