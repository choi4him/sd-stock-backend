"""
app/models/strains.py
Species, Strain Pydantic v2 스키마
"""
from uuid import UUID
from pydantic import BaseModel, Field


# ── Species ──────────────────────────────────────────────────
class SpeciesBase(BaseModel):
    name: str = Field(..., max_length=100, examples=["Rat"])


class SpeciesCreate(SpeciesBase):
    pass


class SpeciesRead(SpeciesBase):
    id: UUID

    model_config = {"from_attributes": True}


# ── Strain ───────────────────────────────────────────────────
class StrainBase(BaseModel):
    species_id: UUID
    code: str = Field(..., max_length=50, examples=["SD"])
    full_name: str = Field(..., max_length=200, examples=["Sprague-Dawley"])
    is_active: bool = True


class StrainCreate(StrainBase):
    pass


class StrainRead(StrainBase):
    id: UUID

    model_config = {"from_attributes": True}
