"""add method to matches

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-05

"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "matches",
        sa.Column("method", sa.String(), nullable=False, server_default="manual_entry"),
    )


def downgrade() -> None:
    op.drop_column("matches", "method")
