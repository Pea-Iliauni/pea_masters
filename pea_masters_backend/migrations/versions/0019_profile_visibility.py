"""Profiles are visible to everyone at the university unless their owner makes them private.

profiles.is_public existed since 0004 but nothing used it, so every row still holds the old default (false); nobody
chose that. Profiles can now be viewed from the People page, and a person switches theirs to private in Settings.

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-23
"""

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("alter table profiles alter column is_public set default true")
    op.execute("update profiles set is_public = true")


def downgrade() -> None:
    op.execute("alter table profiles alter column is_public set default false")
    op.execute("update profiles set is_public = false")
