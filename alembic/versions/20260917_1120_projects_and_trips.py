"""projects and trips

Two things the books could not say before: whose a unit is, and that it left the
building with somebody.

`projects` and `items.project_id` are belonging — a plain nullable column, empty
meaning «on the books of the enterprise». `trips`, `items.loc_trip_id` and the two
columns on `movements` are placement, so the shape check on `items` has to be
rebuilt to admit the new kind; SQLite cannot alter a check in place, and the batch
below recreates the table from the old definition spelled out here, which is what
`copy_from` wants.

Revision ID: 4c7a1de0b3f2
Revises: 859834afb8ef
Create Date: 2026-09-17 11:20:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "4c7a1de0b3f2"
down_revision: Union[str, None] = "859834afb8ef"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OLD_SHAPE = """
(loc_kind = 'inside'
    AND loc_parent_item_id IS NOT NULL AND loc_storage_place_id IS NULL
    AND loc_employee_id IS NULL AND loc_room_id IS NULL AND loc_external_note IS NULL)
OR (loc_kind = 'storage'
    AND loc_parent_item_id IS NULL AND loc_storage_place_id IS NOT NULL
    AND loc_employee_id IS NULL AND loc_room_id IS NULL AND loc_external_note IS NULL)
OR (loc_kind = 'person'
    AND loc_parent_item_id IS NULL AND loc_storage_place_id IS NULL
    AND loc_employee_id IS NOT NULL AND loc_external_note IS NULL)
OR (loc_kind = 'room'
    AND loc_parent_item_id IS NULL AND loc_storage_place_id IS NULL
    AND loc_employee_id IS NULL AND loc_room_id IS NOT NULL AND loc_external_note IS NULL)
OR (loc_kind = 'external'
    AND loc_parent_item_id IS NULL AND loc_storage_place_id IS NULL
    AND loc_employee_id IS NULL AND loc_room_id IS NULL AND loc_external_note IS NOT NULL)
OR (loc_kind = 'written_off'
    AND loc_parent_item_id IS NULL AND loc_storage_place_id IS NULL
    AND loc_employee_id IS NULL AND loc_room_id IS NULL AND loc_external_note IS NULL)
"""

NEW_SHAPE = """
(loc_kind = 'inside'
    AND loc_parent_item_id IS NOT NULL AND loc_storage_place_id IS NULL
    AND loc_employee_id IS NULL AND loc_room_id IS NULL AND loc_trip_id IS NULL
    AND loc_external_note IS NULL)
OR (loc_kind = 'storage'
    AND loc_parent_item_id IS NULL AND loc_storage_place_id IS NOT NULL
    AND loc_employee_id IS NULL AND loc_room_id IS NULL AND loc_trip_id IS NULL
    AND loc_external_note IS NULL)
OR (loc_kind = 'person'
    AND loc_parent_item_id IS NULL AND loc_storage_place_id IS NULL
    AND loc_employee_id IS NOT NULL AND loc_trip_id IS NULL
    AND loc_external_note IS NULL)
OR (loc_kind = 'room'
    AND loc_parent_item_id IS NULL AND loc_storage_place_id IS NULL
    AND loc_employee_id IS NULL AND loc_room_id IS NOT NULL AND loc_trip_id IS NULL
    AND loc_external_note IS NULL)
OR (loc_kind = 'trip'
    AND loc_parent_item_id IS NULL AND loc_storage_place_id IS NULL
    AND loc_employee_id IS NULL AND loc_room_id IS NULL AND loc_trip_id IS NOT NULL
    AND loc_external_note IS NULL)
OR (loc_kind = 'external'
    AND loc_parent_item_id IS NULL AND loc_storage_place_id IS NULL
    AND loc_employee_id IS NULL AND loc_room_id IS NULL AND loc_trip_id IS NULL
    AND loc_external_note IS NOT NULL)
OR (loc_kind = 'written_off'
    AND loc_parent_item_id IS NULL AND loc_storage_place_id IS NULL
    AND loc_employee_id IS NULL AND loc_room_id IS NULL AND loc_trip_id IS NULL
    AND loc_external_note IS NULL)
"""

LOCATION_KINDS = ("inside", "storage", "person", "room", "trip", "external", "written_off")

# the same convention the models use, so constraint names come out identical
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def _old_items_table() -> sa.Table:
    """The `items` table as it stands before this migration — batch mode copies
    from this instead of reflecting, so nothing depends on how SQLite echoes DDL."""
    return sa.Table(
        "items",
        sa.MetaData(naming_convention=NAMING_CONVENTION),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("inv_number", sa.String(length=16), nullable=False),
        sa.Column("legacy_number", sa.String(length=32), nullable=True),
        sa.Column("type_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("manufacturer", sa.String(length=100), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("serial_number", sa.String(length=100), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "in_use",
                "reserve",
                "incomplete",
                "donor",
                "repair",
                "written_off",
                name="itemstatus",
                native_enum=False,
                length=24,
            ),
            nullable=False,
        ),
        sa.Column("condition_note", sa.Text(), nullable=True),
        sa.Column("purchase_date", sa.Date(), nullable=True),
        sa.Column("warranty_until", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("auto_data", sa.JSON(), nullable=True),
        sa.Column("kit_template_id", sa.Integer(), nullable=True),
        sa.Column(
            "loc_kind",
            sa.Enum(
                "inside",
                "storage",
                "person",
                "room",
                "external",
                "written_off",
                name="locationkind",
                native_enum=False,
                length=24,
            ),
            nullable=False,
        ),
        sa.Column("loc_parent_item_id", sa.Integer(), nullable=True),
        sa.Column("loc_storage_place_id", sa.Integer(), nullable=True),
        sa.Column("loc_employee_id", sa.Integer(), nullable=True),
        sa.Column("loc_room_id", sa.Integer(), nullable=True),
        sa.Column("loc_external_note", sa.String(length=200), nullable=True),
        sa.Column("loc_since", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_items"),
        sa.ForeignKeyConstraint(
            ["kit_template_id"], ["kit_templates.id"], name="fk_items_kit_template_id_kit_templates"
        ),
        sa.ForeignKeyConstraint(
            ["loc_employee_id"], ["employees.id"], name="fk_items_loc_employee_id_employees"
        ),
        sa.ForeignKeyConstraint(
            ["loc_parent_item_id"], ["items.id"], name="fk_items_loc_parent_item_id_items"
        ),
        sa.ForeignKeyConstraint(["loc_room_id"], ["rooms.id"], name="fk_items_loc_room_id_rooms"),
        sa.ForeignKeyConstraint(
            ["loc_storage_place_id"],
            ["storage_places.id"],
            name="fk_items_loc_storage_place_id_storage_places",
        ),
        sa.ForeignKeyConstraint(["type_id"], ["item_types.id"], name="fk_items_type_id_item_types"),
        sa.CheckConstraint(OLD_SHAPE, name="location_shape"),
        sa.CheckConstraint(
            "loc_parent_item_id IS NULL OR loc_parent_item_id <> id",
            name="not_inside_itself",
        ),
        # spelled out because the batch recreates the table: an index left out here
        # would be dropped with the old table and never come back
        sa.Index("ix_items_inv_number", "inv_number", unique=True),
        sa.Index("ix_items_legacy_number", "legacy_number"),
        sa.Index("ix_items_serial_number", "serial_number"),
        sa.Index("ix_items_status", "status"),
        sa.Index("ix_items_loc_kind", "loc_kind"),
        sa.Index("ix_items_loc_parent_item_id", "loc_parent_item_id"),
        sa.Index("ix_items_loc_storage_place_id", "loc_storage_place_id"),
        sa.Index("ix_items_loc_employee_id", "loc_employee_id"),
        sa.Index("ix_items_loc_room_id", "loc_room_id"),
    )


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=24), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("customer", sa.String(length=160), nullable=True),
        sa.Column("starts_on", sa.Date(), nullable=True),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "active",
                "suspended",
                "closed",
                name="projectstatus",
                native_enum=False,
                length=24,
            ),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
        sa.UniqueConstraint("code", name=op.f("uq_projects_code")),
    )
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_projects_status"), ["status"], unique=False)

    op.create_table(
        "trips",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("destination", sa.String(length=200), nullable=False),
        sa.Column("purpose", sa.String(length=300), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("departs_on", sa.Date(), nullable=False),
        sa.Column("returns_on", sa.Date(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("open", "closed", name="tripstatus", native_enum=False, length=24),
            nullable=False,
        ),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employees.id"], name=op.f("fk_trips_employee_id_employees")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_trips_project_id_projects")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trips")),
    )
    with op.batch_alter_table("trips", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_trips_code"), ["code"], unique=True)
        batch_op.create_index(batch_op.f("ix_trips_employee_id"), ["employee_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_trips_project_id"), ["project_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_trips_status"), ["status"], unique=False)

    # items: belonging, the trip placement target, and the widened shape check
    with op.batch_alter_table(
        "items", schema=None, copy_from=_old_items_table()
    ) as batch_op:
        batch_op.add_column(sa.Column("project_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("loc_trip_id", sa.Integer(), nullable=True))
        batch_op.alter_column(
            "loc_kind",
            existing_type=sa.String(length=24),
            type_=sa.Enum(
                *LOCATION_KINDS, name="locationkind", native_enum=False, length=24
            ),
            existing_nullable=False,
        )
        batch_op.drop_constraint("location_shape", type_="check")
        batch_op.create_check_constraint("location_shape", NEW_SHAPE)
        batch_op.create_foreign_key(
            op.f("fk_items_project_id_projects"), "projects", ["project_id"], ["id"]
        )
        batch_op.create_foreign_key(
            op.f("fk_items_loc_trip_id_trips"), "trips", ["loc_trip_id"], ["id"]
        )
        batch_op.create_index(batch_op.f("ix_items_project_id"), ["project_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_items_loc_trip_id"), ["loc_trip_id"], unique=False)

    with op.batch_alter_table("movements", schema=None) as batch_op:
        batch_op.add_column(sa.Column("from_trip_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("to_trip_id", sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f("ix_movements_from_trip_id"), ["from_trip_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_movements_to_trip_id"), ["to_trip_id"], unique=False)
        batch_op.create_foreign_key(
            op.f("fk_movements_from_trip_id_trips"), "trips", ["from_trip_id"], ["id"]
        )
        batch_op.create_foreign_key(
            op.f("fk_movements_to_trip_id_trips"), "trips", ["to_trip_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("movements", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("fk_movements_to_trip_id_trips"), type_="foreignkey")
        batch_op.drop_constraint(op.f("fk_movements_from_trip_id_trips"), type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_movements_to_trip_id"))
        batch_op.drop_index(batch_op.f("ix_movements_from_trip_id"))
        batch_op.drop_column("to_trip_id")
        batch_op.drop_column("from_trip_id")

    # anything still travelling would violate the narrower check; put it on the
    # books as «handed outside the department», which is what a trip is without
    # the trips table to explain it
    op.execute(
        "UPDATE items SET loc_kind = 'external', "
        "loc_external_note = COALESCE("
        "  (SELECT 'командировка: ' || t.destination FROM trips t WHERE t.id = items.loc_trip_id),"
        "  'командировка'), "
        "loc_trip_id = NULL "
        "WHERE loc_kind = 'trip'"
    )

    with op.batch_alter_table("items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_items_loc_trip_id"))
        batch_op.drop_index(batch_op.f("ix_items_project_id"))
        batch_op.drop_constraint(op.f("fk_items_loc_trip_id_trips"), type_="foreignkey")
        batch_op.drop_constraint(op.f("fk_items_project_id_projects"), type_="foreignkey")
        batch_op.drop_constraint("location_shape", type_="check")
        batch_op.create_check_constraint("location_shape", OLD_SHAPE)
        batch_op.drop_column("loc_trip_id")
        batch_op.drop_column("project_id")

    with op.batch_alter_table("trips", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_trips_status"))
        batch_op.drop_index(batch_op.f("ix_trips_project_id"))
        batch_op.drop_index(batch_op.f("ix_trips_employee_id"))
        batch_op.drop_index(batch_op.f("ix_trips_code"))
    op.drop_table("trips")

    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_projects_status"))
    op.drop_table("projects")
