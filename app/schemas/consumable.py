from typing import Optional

from pydantic import BaseModel, Field, field_validator


def _blank_to_none(value):
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


class ConsumableForm(BaseModel):
    """A consumable position: everything except the quantity, which the ledger owns."""

    name: str = Field(min_length=1, max_length=150)
    category: Optional[str] = Field(default=None, max_length=60)
    unit: Optional[str] = Field(default=None, max_length=16)
    min_quantity: int = 0
    storage_place_id: Optional[int] = None
    notes: Optional[str] = None
    is_active: bool = True

    @field_validator("category", "unit", "notes", "storage_place_id", mode="before")
    @classmethod
    def empty_string_is_none(cls, value):
        return _blank_to_none(value)

    @field_validator("min_quantity", mode="before")
    @classmethod
    def empty_number_is_zero(cls, value):
        if value in (None, "", "None"):
            return 0
        return value

    @field_validator("min_quantity")
    @classmethod
    def not_negative(cls, value):
        if value < 0:
            raise ValueError("Порог не может быть отрицательным")
        return value

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class ConsumableFilter(BaseModel):
    q: Optional[str] = None
    category: Optional[str] = None
    storage_place_id: Optional[int] = None
    low_only: bool = False
    include_inactive: bool = False

    @field_validator("q", "category", "storage_place_id", mode="before")
    @classmethod
    def empty_choice_is_none(cls, value):
        return _blank_to_none(value)

    @field_validator("low_only", "include_inactive", mode="before")
    @classmethod
    def checkbox(cls, value):
        if isinstance(value, str):
            return value.lower() not in ("", "0", "false", "off", "нет")
        return bool(value)
