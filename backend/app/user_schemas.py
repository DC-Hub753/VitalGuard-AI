"""Pydantic schemas for user and RBAC management."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

RoleType = Literal["admin", "clinician", "nurse"]


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=8, max_length=128)
    role: RoleType = "nurse"
    full_name: str = Field(default="", max_length=120)


class UserStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active: bool


class UserRoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: RoleType


class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    full_name: str
    active: bool
    created_at: str
    updated_at: str
    demo_only: Literal[True] = True
