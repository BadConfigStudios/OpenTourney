"""add table_number to matches

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-02

"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("matches", sa.Column("table_number", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("matches", "table_number")
