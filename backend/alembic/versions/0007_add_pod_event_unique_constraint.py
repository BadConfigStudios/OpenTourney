"""add pod event unique constraint

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-02

"""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_pod_event", "pods", ["event_id"])


def downgrade() -> None:
    op.drop_constraint("uq_pod_event", "pods", type_="unique")
