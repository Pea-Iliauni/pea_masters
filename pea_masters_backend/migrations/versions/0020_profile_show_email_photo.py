"""Whether a profile shows its owner's email address and photo to colleagues (Settings → Privacy).

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-23
"""

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("alter table profiles add column show_email boolean not null default true")
    op.execute("alter table profiles add column show_photo boolean not null default true")


def downgrade() -> None:
    op.execute("alter table profiles drop column show_photo")
    op.execute("alter table profiles drop column show_email")
