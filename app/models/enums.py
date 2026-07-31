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
    REPAIR = "repair"
    WRITE_OFF = "write_off"


class UserRole(StrEnum):
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"

    def at_least(self, other: "UserRole") -> bool:
        order = [UserRole.VIEWER, UserRole.EDITOR, UserRole.ADMIN]
        return order.index(self) >= order.index(other)


class StoragePlaceKind(StrEnum):
    CABINET = "cabinet"
    SHELF = "shelf"
    CELL = "cell"
    ROOM = "room"
