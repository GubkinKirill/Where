from datetime import date
from typing import Optional

from pydantic import BaseModel, field_validator

from app.models.enums import MovementReason


def _blank_to_none(value):
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


class MovementFilter(BaseModel):
    """Журнал целиком нечитаем: за год это тысячи строк. Фильтры отвечают на
    вопросы, ради которых в него заходят — «что было с этой вещью», «что
    выдавали этому человеку», «что происходило на прошлой неделе»."""

    q: Optional[str] = None
    reason: Optional[MovementReason] = None
    employee_id: Optional[int] = None
    trip_id: Optional[int] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    limit: int = 200

    @field_validator(
        "q", "reason", "employee_id", "trip_id", "date_from", "date_to", mode="before"
    )
    @classmethod
    def empty_is_none(cls, value):
        return _blank_to_none(value)

    @property
    def is_empty(self) -> bool:
        return not any(
            [self.q, self.reason, self.employee_id, self.trip_id, self.date_from, self.date_to]
        )
