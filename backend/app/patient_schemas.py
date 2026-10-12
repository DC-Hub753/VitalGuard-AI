"""Validated request/response schemas for patient management."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PatientCreate(BaseModel):
    """Create a new patient record."""

    model_config = ConfigDict(extra="forbid")

    patient_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")
    display_name: str = Field(min_length=1, max_length=120)
    sex: Literal["M", "F", "U"] = "U"
    date_of_birth: str | None = Field(
        default=None, min_length=10, max_length=10, pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="ISO date YYYY-MM-DD; optional for demo patients.",
    )
    ward: str = Field(default="General Ward", min_length=1, max_length=80)
    bed: str = Field(default="", max_length=20)

    @field_validator("patient_id")
    @classmethod
    def no_whitespace_in_id(cls, value: str) -> str:
        if " " in value or "\t" in value:
            raise ValueError("patient_id must not contain whitespace")
        return value


class PatientUpdate(BaseModel):
    """Partial update of a patient record. Only supplied fields are changed."""

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    sex: Literal["M", "F", "U"] | None = None
    date_of_birth: str | None = Field(
        default=None, min_length=10, max_length=10, pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    ward: str | None = Field(default=None, min_length=1, max_length=80)
    bed: str | None = Field(default=None, max_length=20)


class PatientResponse(BaseModel):
    patient_id: str
    display_name: str
    sex: str
    date_of_birth: str | None
    ward: str
    bed: str
    active: bool
    created_at: str
    updated_at: str
    demo_only: Literal[True] = True
