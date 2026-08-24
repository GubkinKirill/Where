"""Consumables: the small stuff nobody numbers one by one — mice, patch cords,
adapters, power cables, small SD cards.

A separate mode of accounting on purpose, not a flavour of Item: here a position
has a quantity, not an identity, and its history is a ledger of pluses and minuses
rather than a chain of placements.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, enum_column, now
from app.models.directory import Employee, StoragePlace
from app.models.enums import ConsumableReason
from app.models.user import User

# Written only by services.consumables, which is enforced by services/stock_guard.py.
QUANTITY_COLUMN = "quantity"


class ConsumableStock(Base, TimestampMixin):
    __tablename__ = "consumable_stock"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), index=True)
    category: Mapped[str] = mapped_column(String(60), default="", index=True)
    unit: Mapped[str] = mapped_column(String(16), default="шт.")
    # a cache of the ledger below: every change goes through a ConsumableMovement
    quantity: Mapped[int] = mapped_column(default=0)
    # warn when the stock drops to this; 0 means «do not warn»
    min_quantity: Mapped[int] = mapped_column(default=0)
    storage_place_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("storage_places.id"), index=True, default=None
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, default=None)
    is_active: Mapped[bool] = mapped_column(default=True)

    storage_place: Mapped[Optional[StoragePlace]] = relationship(lazy="joined")

    @property
    def is_out(self) -> bool:
        return self.quantity <= 0

    @property
    def is_low(self) -> bool:
        return self.min_quantity > 0 and self.quantity <= self.min_quantity

    def __str__(self) -> str:
        return self.name


class ConsumableMovement(Base):
    """Append-only ledger: receipts, issues and recount corrections.

    `quantity_after` is a snapshot taken at the time of the record, so the page reads
    like a bank statement without replaying the whole history.
    """

    __tablename__ = "consumable_movements"

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(
        ForeignKey("consumable_stock.id", ondelete="CASCADE"), index=True
    )
    happened_at: Mapped[datetime] = mapped_column(default=now, index=True)
    reason: Mapped[ConsumableReason] = mapped_column(enum_column(ConsumableReason))
    # + on a receipt, − on an issue, the difference on a correction
    delta: Mapped[int] = mapped_column()
    quantity_after: Mapped[int] = mapped_column()
    employee_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("employees.id"), index=True, default=None
    )
    moved_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), default=None)
    comment: Mapped[Optional[str]] = mapped_column(Text, default=None)

    stock: Mapped[ConsumableStock] = relationship(lazy="joined")
    employee: Mapped[Optional[Employee]] = relationship(lazy="joined")
    moved_by: Mapped[Optional[User]] = relationship()
