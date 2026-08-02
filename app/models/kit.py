from typing import Optional

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.item import ItemType


class KitTemplate(Base, TimestampMixin):
    """What a kit is supposed to contain — the list you check a delivery against."""

    __tablename__ = "kit_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[Optional[str]] = mapped_column(String(400), default=None)
    is_active: Mapped[bool] = mapped_column(default=True)

    lines: Mapped[list["KitTemplateLine"]] = relationship(
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="KitTemplateLine.id",
    )

    @property
    def total_required(self) -> int:
        return sum(line.quantity for line in self.lines)

    def __str__(self) -> str:
        return self.name


class KitTemplateLine(Base):
    """One position of the checklist: this type, this many."""

    __tablename__ = "kit_template_lines"
    __table_args__ = (UniqueConstraint("template_id", "item_type_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("kit_templates.id", ondelete="CASCADE")
    )
    item_type_id: Mapped[int] = mapped_column(ForeignKey("item_types.id"))
    quantity: Mapped[int] = mapped_column(default=1)
    note: Mapped[Optional[str]] = mapped_column(String(200), default=None)

    template: Mapped[KitTemplate] = relationship(back_populates="lines")
    item_type: Mapped[ItemType] = relationship(lazy="joined")
