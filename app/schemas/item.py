from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.models.enums import ItemStatus, LocationKind


def _blank_to_none(value):
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


class ItemForm(BaseModel):
    """Everything about an item except its placement, which only movements change."""

    type_id: int
    name: str = Field(min_length=1, max_length=200)
    legacy_number: Optional[str] = Field(default=None, max_length=32)
    manufacturer: Optional[str] = Field(default=None, max_length=100)
    model: Optional[str] = Field(default=None, max_length=100)
    serial_number: Optional[str] = Field(default=None, max_length=100)
    status: ItemStatus = ItemStatus.RESERVE
    condition_note: Optional[str] = None
    purchase_date: Optional[date] = None
    warranty_until: Optional[date] = None
    notes: Optional[str] = None
    kit_template_id: Optional[int] = None

    @field_validator("kit_template_id", mode="before")
    @classmethod
    def empty_template_is_none(cls, value):
        return _blank_to_none(value)

    @field_validator(
        "legacy_number",
        "manufacturer",
        "model",
        "serial_number",
        "condition_note",
        "notes",
        "purchase_date",
        "warranty_until",
        mode="before",
    )
    @classmethod
    def empty_string_is_none(cls, value):
        return _blank_to_none(value)

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class ItemFilter(BaseModel):
    q: Optional[str] = None
    type_id: Optional[int] = None
    status: Optional[ItemStatus] = None
    loc_kind: Optional[LocationKind] = None
    room_id: Optional[int] = None
    department_id: Optional[int] = None
    employee_id: Optional[int] = None
    storage_place_id: Optional[int] = None
    parent_item_id: Optional[int] = None
    include_written_off: bool = False
    limit: int = 300

    @field_validator("q", mode="before")
    @classmethod
    def clean_query(cls, value):
        return _blank_to_none(value)

    @field_validator(
        "type_id",
        "room_id",
        "department_id",
        "employee_id",
        "storage_place_id",
        "parent_item_id",
        "status",
        "loc_kind",
        mode="before",
    )
    @classmethod
    def empty_choice_is_none(cls, value):
        return _blank_to_none(value)

    @property
    def is_empty(self) -> bool:
        return not any(
            [
                self.q,
                self.type_id,
                self.status,
                self.loc_kind,
                self.room_id,
                self.department_id,
                self.employee_id,
                self.storage_place_id,
                self.parent_item_id,
                self.include_written_off,
            ]
        )
