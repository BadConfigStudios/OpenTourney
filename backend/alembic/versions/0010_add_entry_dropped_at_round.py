"""add dropped_at_round to entries

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-11

"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("entries", sa.Column("dropped_at_round", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("entries", "dropped_at_round")
