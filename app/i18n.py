"""All Russian wording that cannot live in a template: enum labels and the
location snapshots written into the movement log."""

from app.models.enums import (
    ItemStatus,
    LocationKind,
    MovementReason,
    StoragePlaceKind,
    UserRole,
)

STATUS_LABELS = {
    ItemStatus.IN_USE: "В работе",
    ItemStatus.RESERVE: "В резерве",
    ItemStatus.INCOMPLETE: "Некомплект",
    ItemStatus.DONOR: "На разбор",
    ItemStatus.REPAIR: "В ремонте",
    ItemStatus.WRITTEN_OFF: "Списана",
}

LOCATION_KIND_LABELS = {
    LocationKind.INSIDE: "Внутри другой единицы",
    LocationKind.STORAGE: "На складе",
    LocationKind.PERSON: "У сотрудника",
    LocationKind.ROOM: "В кабинете",
    LocationKind.EXTERNAL: "Передано за пределы отдела",
    LocationKind.WRITTEN_OFF: "Списано",
}

LOCATION_KIND_ICONS = {
    LocationKind.INSIDE: "📦",
    LocationKind.STORAGE: "🗄",
    LocationKind.PERSON: "👤",
    LocationKind.ROOM: "🚪",
    LocationKind.EXTERNAL: "↗",
    LocationKind.WRITTEN_OFF: "✕",
}

# how a location is rendered into the immutable snapshot stored on a movement
LOCATION_SNAPSHOT_TEMPLATES = {
    LocationKind.INSIDE: "внутри {target}",
    LocationKind.STORAGE: "склад · {target}",
    LocationKind.PERSON: "{target}",
    LocationKind.ROOM: "кабинет {target}",
    LocationKind.EXTERNAL: "передано: {target}",
    LocationKind.WRITTEN_OFF: "списано",
}

MOVEMENT_REASON_LABELS = {
    MovementReason.REGISTER: "Постановка на учёт",
    MovementReason.ISSUE: "Выдача",
    MovementReason.RETURN: "Возврат",
    MovementReason.INSTALL: "Установка в состав",
    MovementReason.UNINSTALL: "Изъятие из состава",
    MovementReason.TO_STORAGE: "Перемещение на склад",
    MovementReason.TRANSFER_OUT: "Передача в другой отдел",
    MovementReason.REPAIR: "Ремонт",
    MovementReason.WRITE_OFF: "Списание",
}

ROLE_LABELS = {
    UserRole.ADMIN: "администратор",
    UserRole.EDITOR: "редактор",
    UserRole.VIEWER: "просмотр",
}

STORAGE_KIND_LABELS = {
    StoragePlaceKind.CABINET: "Шкаф",
    StoragePlaceKind.SHELF: "Полка",
    StoragePlaceKind.CELL: "Ячейка",
    StoragePlaceKind.ROOM: "Помещение",
}


def status_label(value: ItemStatus | str) -> str:
    return STATUS_LABELS.get(ItemStatus(value), str(value))


def location_kind_label(value: LocationKind | str) -> str:
    return LOCATION_KIND_LABELS.get(LocationKind(value), str(value))


def location_kind_icon(value: LocationKind | str) -> str:
    return LOCATION_KIND_ICONS.get(LocationKind(value), "•")


def reason_label(value: MovementReason | str) -> str:
    return MOVEMENT_REASON_LABELS.get(MovementReason(value), str(value))


def role_label(value: UserRole | str) -> str:
    return ROLE_LABELS.get(UserRole(value), str(value))


def storage_kind_label(value: StoragePlaceKind | str) -> str:
    return STORAGE_KIND_LABELS.get(StoragePlaceKind(value), str(value))
