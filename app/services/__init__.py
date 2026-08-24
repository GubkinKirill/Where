"""Importing this package registers the write guards on every ORM session."""

from app.services import location_guard  # noqa: F401  (side effect: event listener)
from app.services import stock_guard  # noqa: F401  (side effect: event listener)

__all__ = ["location_guard", "stock_guard"]
