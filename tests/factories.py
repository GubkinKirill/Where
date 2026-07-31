from app.models.item import Item, ItemType
from app.schemas.item import ItemForm
from app.services import items as items_service
from app.services.location import LocationRef


def make_item(db, item_type: ItemType, *, name: str = "Тестовая единица", at: LocationRef, actor=None) -> Item:
    return items_service.create_item(
        db,
        form=ItemForm(type_id=item_type.id, name=name),
        location=at,
        actor=actor,
    )
