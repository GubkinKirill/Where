"""All Russian wording that cannot live in a template: enum labels and the
location snapshots written into the movement log."""

from app.models.enums import (
    ConsumableReason,
    ItemStatus,
    LocationKind,
    MovementReason,
    ProjectStatus,
    StoragePlaceKind,
    TripStatus,
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
    LocationKind.TRIP: "В командировке",
    LocationKind.EXTERNAL: "Передано за пределы отдела",
    LocationKind.WRITTEN_OFF: "Списано",
}

LOCATION_KIND_ICONS = {
    LocationKind.INSIDE: "📦",
    LocationKind.STORAGE: "🗄",
    LocationKind.PERSON: "👤",
    LocationKind.ROOM: "🚪",
    LocationKind.TRIP: "🧳",
    LocationKind.EXTERNAL: "↗",
    LocationKind.WRITTEN_OFF: "✕",
}

# how a location is rendered into the immutable snapshot stored on a movement
LOCATION_SNAPSHOT_TEMPLATES = {
    LocationKind.INSIDE: "внутри {target}",
    LocationKind.STORAGE: "склад · {target}",
    LocationKind.PERSON: "{target}",
    LocationKind.ROOM: "кабинет {target}",
    LocationKind.TRIP: "командировка · {target}",
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
    MovementReason.TRIP_OUT: "Взято в командировку",
    MovementReason.TRIP_RETURN: "Возврат из командировки",
    MovementReason.TRIP_LEFT: "Оставлено на месте командировки",
    MovementReason.REPAIR: "Ремонт",
    MovementReason.WRITE_OFF: "Списание",
}

ROLE_LABELS = {
    UserRole.ADMIN: "администратор",
    UserRole.EDITOR: "редактор",
    UserRole.VIEWER: "просмотр",
    UserRole.EMPLOYEE: "сотрудник",
}

ROLE_HINTS = {
    UserRole.ADMIN: "всё, включая справочники и учётные записи",
    UserRole.EDITOR: "ведёт учёт: единицы, перемещения, выдачи",
    UserRole.VIEWER: "смотрит списки и карточки, ничего не меняет",
    UserRole.EMPLOYEE: "только личный кабинет: своя техника и коллеги",
}

CONSUMABLE_REASON_LABELS = {
    ConsumableReason.RECEIPT: "Приход",
    ConsumableReason.ISSUE: "Расход",
    ConsumableReason.ADJUST: "Корректировка",
}

STORAGE_KIND_LABELS = {
    StoragePlaceKind.CABINET: "Шкаф",
    StoragePlaceKind.SHELF: "Полка",
    StoragePlaceKind.CELL: "Ячейка",
    StoragePlaceKind.ROOM: "Помещение",
}

PROJECT_STATUS_LABELS = {
    ProjectStatus.ACTIVE: "Идёт",
    ProjectStatus.SUSPENDED: "Приостановлен",
    ProjectStatus.CLOSED: "Закрыт",
}

TRIP_STATUS_LABELS = {
    TripStatus.OPEN: "Открыта",
    TripStatus.CLOSED: "Закрыта",
}

# what happened to a unit that left with a trip; drawn in the trip card
TRIP_OUTCOME_LABELS = {
    "away": "в командировке",
    "returned": "вернулась",
    "left": "оставлена на месте",
    "written_off": "списана там",
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


def role_hint(value: UserRole | str) -> str:
    return ROLE_HINTS.get(UserRole(value), "")


def consumable_reason_label(value: ConsumableReason | str) -> str:
    return CONSUMABLE_REASON_LABELS.get(ConsumableReason(value), str(value))


def storage_kind_label(value: StoragePlaceKind | str) -> str:
    return STORAGE_KIND_LABELS.get(StoragePlaceKind(value), str(value))


def project_status_label(value: ProjectStatus | str) -> str:
    return PROJECT_STATUS_LABELS.get(ProjectStatus(value), str(value))


def trip_status_label(value: TripStatus | str) -> str:
    return TRIP_STATUS_LABELS.get(TripStatus(value), str(value))


def trip_outcome_label(value: str) -> str:
    return TRIP_OUTCOME_LABELS.get(value, value)
