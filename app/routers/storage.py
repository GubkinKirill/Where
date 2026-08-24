"""The warehouse seen as places: what is on which shelf, units and consumables both."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.auth.deps import DbSession, ViewerUser
from app.services import consumables as consumables_service
from app.services import storage as storage_service
from app.templating import render

router = APIRouter()


@router.get("/storage", response_class=HTMLResponse)
def storage_index(request: Request, db: DbSession, user: ViewerUser) -> HTMLResponse:
    return render(
        request,
        "storage/index.html",
        {
            "user": user,
            "places": storage_service.tree(db),
            "positions": consumables_service.total_positions(db),
            "low": consumables_service.low_stock(db),
        },
    )


@router.get("/storage/{place_id}", response_class=HTMLResponse)
def storage_place(place_id: int, request: Request, db: DbSession, user: ViewerUser):
    place = storage_service.get_place(db, place_id)
    if place is None:
        return render(request, "not_found.html", {"user": user}, status_code=404)
    return render(
        request,
        "storage/place.html",
        {
            "user": user,
            "place": place,
            "children": storage_service.children_of(db, place),
            "items": storage_service.items_on(db, place),
            "stocks": consumables_service.on_place(db, place.id),
        },
    )
