from enum import StrEnum


class ItemStatus(StrEnum):
    IN_USE = "in_use"
    RESERVE = "reserve"
    INCOMPLETE = "incomplete"
    DONOR = "donor"
    REPAIR = "repair"
    WRITTEN_OFF = "written_off"


class LocationKind(StrEnum):
    INSIDE = "inside"
    STORAGE = "storage"
    PERSON = "person"
    ROOM = "room"
    # travelled out with somebody: the target is a Trip, which knows who and where
    TRIP = "trip"
    EXTERNAL = "external"
    WRITTEN_OFF = "written_off"


class MovementReason(StrEnum):
    REGISTER = "register"
    ISSUE = "issue"
    RETURN = "return"
    INSTALL = "install"
    UNINSTALL = "uninstall"
    TO_STORAGE = "to_storage"
    TRANSFER_OUT = "transfer_out"
    TRIP_OUT = "trip_out"
    TRIP_RETURN = "trip_return"
    TRIP_LEFT = "trip_left"
    REPAIR = "repair"
    WRITE_OFF = "write_off"


class UserRole(StrEnum):
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"
    # an ordinary employee: sees their own cabinet, never the accounting screens
    EMPLOYEE = "employee"

    def at_least(self, other: "UserRole") -> bool:
        order = [UserRole.EMPLOYEE, UserRole.VIEWER, UserRole.EDITOR, UserRole.ADMIN]
        return order.index(self) >= order.index(other)

    @property
    def is_staff(self) -> bool:
        """Works in the department: gets the accounting screens, not just a cabinet."""
        return self is not UserRole.EMPLOYEE


class StoragePlaceKind(StrEnum):
    CABINET = "cabinet"
    SHELF = "shelf"
    CELL = "cell"
    ROOM = "room"


class ConsumableReason(StrEnum):
    RECEIPT = "receipt"
    ISSUE = "issue"
    ADJUST = "adjust"


class ProjectStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CLOSED = "closed"

    @property
    def is_open(self) -> bool:
        return self is not ProjectStatus.CLOSED


class TripStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
