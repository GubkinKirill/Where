"""Importing this package registers the placement guard on every ORM session."""

from app.services import location_guard  # noqa: F401  (side effect: event listener)

__all__ = ["location_guard"]
