"""add completed_at to pods

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-03

"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pods", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("pods", "completed_at")
