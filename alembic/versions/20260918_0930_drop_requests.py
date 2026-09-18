"""drop requests

Заявки сняты с фронта: пока их не ведут, и таблица держала бы пустую сущность,
которую видно в схеме и не видно в приложении. Данных в ней нет — она была
частью демо-набора и снимается вместе с ним.

Возвращать: откатом коммита, который её убрал, и этой миграцией вниз — она
создаёт таблицу ровно такой, какой та была.

Revision ID: 9b2f4c7a61d8
Revises: 4c7a1de0b3f2
Create Date: 2026-09-18 09:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "9b2f4c7a61d8"
down_revision: Union[str, None] = "4c7a1de0b3f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("requests", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_requests_status"))
        batch_op.drop_index(batch_op.f("ix_requests_employee_id"))
    op.drop_table("requests")


def downgrade() -> None:
    op.create_table(
        "requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "need", "broken", "pickup", "other",
                name="requestkind", native_enum=False, length=24,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "new", "in_progress", "done", "rejected",
                name="requeststatus", native_enum=False, length=24,
            ),
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("closed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["closed_by_user_id"], ["users.id"], name=op.f("fk_requests_closed_by_user_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employees.id"], name=op.f("fk_requests_employee_id_employees")
        ),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], name=op.f("fk_requests_item_id_items")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_requests")),
    )
    with op.batch_alter_table("requests", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_requests_employee_id"), ["employee_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_requests_status"), ["status"], unique=False)
