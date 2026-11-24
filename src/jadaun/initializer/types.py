from __future__ import annotations

from pydantic import BaseModel, Field


class ModuleConfigDescriptionType(BaseModel):
    allowed: list[str] = Field(default_factory=list)
    default: str
    deprecated: list[str] = Field(default_factory=list)
    sunset_date: dict[str, str] = Field(default_factory=dict)
    submodules: dict[str, ModuleConfigDescriptionType] = Field(default_factory=dict)
