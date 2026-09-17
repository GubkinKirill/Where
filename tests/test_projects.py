"""Belonging: what came with a project and where it is now."""

from datetime import date

import pytest

from app.models.enums import ItemStatus, LocationKind, ProjectStatus
from app.models.project import Project
from app.schemas.item import ItemFilter, ItemForm
from app.services import items as items_service
from app.services import movements as movements_service
from app.services import projects as projects_service
from app.services import trips as trips_service
from app.services.location import LocationRef
from tests.factories import make_item


@pytest.fixture
def project(db) -> Project:
    record = Project(
        code="PRJ-04",
        name="Северный узел",
        customer="ООО «Связь»",
        starts_on=date(2026, 3, 1),
    )
    db.add(record)
    db.flush()
    return record


def make_project_item(db, item_type, project, *, at, actor=None, name="Единица проекта"):
    return items_service.create_item(
        db,
        form=ItemForm(type_id=item_type.id, name=name, project_id=project.id),
        location=at,
        actor=actor,
    )


def test_an_item_without_a_project_belongs_to_the_enterprise(db, types, shelf, actor):
    item = make_item(db, types["PC"], at=LocationRef.storage(shelf.id), actor=actor)

    assert item.project_id is None
    assert projects_service.company_owned_count(db) == 1
    assert projects_service.project_owned_count(db) == 0


def test_project_equipment_is_listed_with_the_project(db, types, shelf, project, actor):
    own = make_item(db, types["PC"], at=LocationRef.storage(shelf.id), actor=actor)
    theirs = make_project_item(db, types["MON"], project, at=LocationRef.storage(shelf.id), actor=actor)

    listed = projects_service.items_of(db, project)

    assert [item.id for item in listed] == [theirs.id]
    assert own.id not in {item.id for item in listed}
    assert projects_service.item_counts(db)[project.id] == 1


def test_belonging_survives_every_move(db, types, shelf, employee, project, actor):
    item = make_project_item(db, types["MON"], project, at=LocationRef.storage(shelf.id), actor=actor)

    movements_service.issue_item(db, item=item, employee_id=employee.id, actor=actor)

    assert item.project_id == project.id
    assert projects_service.items_of(db, project)[0].loc_kind is LocationKind.PERSON


def test_summary_counts_by_placement_and_keeps_written_off_apart(
    db, types, shelf, room, project, actor
):
    on_shelf = make_project_item(db, types["PC"], project, at=LocationRef.storage(shelf.id), actor=actor)
    make_project_item(db, types["MON"], project, at=LocationRef.room(room.id), actor=actor)
    dead = make_project_item(db, types["RAM"], project, at=LocationRef.storage(shelf.id), actor=actor)
    movements_service.write_off_item(db, item=dead, actor=actor)

    summary = projects_service.summary(db, project)

    assert summary.total == 2
    assert summary.by_location[LocationKind.STORAGE] == 1
    assert summary.by_location[LocationKind.ROOM] == 1
    assert summary.written_off == 1
    assert on_shelf.status is not ItemStatus.WRITTEN_OFF


def test_filter_by_owner_splits_company_from_project(db, types, shelf, project, actor):
    own = make_item(db, types["PC"], at=LocationRef.storage(shelf.id), actor=actor)
    theirs = make_project_item(db, types["MON"], project, at=LocationRef.storage(shelf.id), actor=actor)

    company = items_service.search_items(db, ItemFilter(owner="company"))
    of_project = items_service.search_items(db, ItemFilter(owner=str(project.id)))

    assert [item.id for item in company] == [own.id]
    assert [item.id for item in of_project] == [theirs.id]


def test_a_nonsense_owner_filter_is_ignored_rather_than_fatal(db, types, shelf, actor):
    make_item(db, types["PC"], at=LocationRef.storage(shelf.id), actor=actor)

    filters = ItemFilter(owner="; drop table items")

    assert filters.owner is None
    assert len(items_service.search_items(db, filters)) == 1


def test_belonging_can_be_changed_on_the_card(db, types, shelf, project, actor):
    item = make_item(db, types["PC"], at=LocationRef.storage(shelf.id), actor=actor)

    items_service.update_item(
        db,
        item=item,
        form=ItemForm(type_id=item.type_id, name=item.name, project_id=project.id),
    )

    assert item.project_id == project.id
    items_service.update_item(
        db, item=item, form=ItemForm(type_id=item.type_id, name=item.name, project_id=None)
    )
    assert item.project_id is None


def test_trips_of_a_project_are_listed(db, employee, project):
    trip = trips_service.create_trip(
        db,
        employee=employee,
        destination="Новосибирск",
        departs_on=date.today(),
        project_id=project.id,
    )

    assert [record.id for record in projects_service.trips_of(db, project)] == [trip.id]


def test_closed_projects_can_be_hidden(db, project):
    project.status = ProjectStatus.CLOSED
    db.flush()

    assert projects_service.list_projects(db, include_closed=True) == [project]
    assert projects_service.list_projects(db, include_closed=False) == []
