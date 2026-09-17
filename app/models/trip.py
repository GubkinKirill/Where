"""A person went somewhere and took equipment with them.

While away, a unit is not «у Петрова» — it is out of the building, and the trip
record is what says who took it and where to. That is why a trip is a placement
target of its own rather than a note on a handover: the list of what is physically
on site answers correctly, and a thing cannot quietly stay «at the office» while
it is two thousand kilometres away.

A trip closes only when every unit that left with it has been accounted for:
came back, was left on site, or was written off there.
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, enum_column
from app.models.directory import Employee
from app.models.enums import TripStatus
from app.models.project import Project


class Trip(Base, TimestampMixin):
    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    destination: Mapped[str] = mapped_column(String(200))
    purpose: Mapped[Optional[str]] = mapped_column(String(300), default=None)
    # trips are usually made for a project; the field is a hint, not a rule
    project_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("projects.id"), index=True, default=None
    )
    departs_on: Mapped[date] = mapped_column()
    returns_on: Mapped[Optional[date]] = mapped_column(default=None)
    status: Mapped[TripStatus] = mapped_column(
        enum_column(TripStatus), default=TripStatus.OPEN, index=True
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(default=None)
    notes: Mapped[Optional[str]] = mapped_column(Text, default=None)

    employee: Mapped[Employee] = relationship(lazy="joined")
    project: Mapped[Optional[Project]] = relationship(lazy="joined")

    @property
    def is_open(self) -> bool:
        return self.status is TripStatus.OPEN

    @property
    def is_overdue(self) -> bool:
        """Should have been back by now and still has things out."""
        return (
            self.is_open
            and self.returns_on is not None
            and self.returns_on < date.today()
        )

    def __str__(self) -> str:
        return f"{self.code} · {self.destination}"
