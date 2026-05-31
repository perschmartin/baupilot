"""BauPilot — Mandantenverwaltung.

B-003: Schema-per-Tenant — beim Anlegen eines Mandanten wird
automatisch ein PostgreSQL-Schema erstellt.
"""

from uuid import UUID

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db, create_tenant_schema, SHARED_SCHEMA
from models.tenant import Mandant

router = APIRouter(prefix="/tenants", tags=["tenants"])


class TenantCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(
        ...,
        min_length=1,
        max_length=63,
        pattern=r"^[a-z][a-z0-9_]*$",
        description="Eindeutiger Slug, wird zum PostgreSQL-Schema-Namen",
    )
    beschreibung: str | None = None


class TenantResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    beschreibung: str | None
    aktiv: bool

    model_config = {"from_attributes": True}


@router.post("/", response_model=TenantResponse, status_code=201)
def create_tenant(data: TenantCreate, db: Session = Depends(get_db)) -> Mandant:
    """Neuen Mandanten anlegen und PostgreSQL-Schema erstellen."""
    existing = db.execute(
        select(Mandant).where(Mandant.slug == data.slug)
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail=f"Mandant '{data.slug}' existiert bereits.")

    mandant = Mandant(
        name=data.name,
        slug=data.slug,
        beschreibung=data.beschreibung,
    )
    db.add(mandant)
    db.commit()
    db.refresh(mandant)

    # PostgreSQL-Schema anlegen (B-003)
    create_tenant_schema(data.slug)

    return mandant


@router.get("/", response_model=list[TenantResponse])
def list_tenants(db: Session = Depends(get_db)) -> list[Mandant]:
    """Alle aktiven Mandanten auflisten."""
    result = db.execute(
        select(Mandant).where(Mandant.geloescht == False).order_by(Mandant.name)
    )
    return list(result.scalars().all())
