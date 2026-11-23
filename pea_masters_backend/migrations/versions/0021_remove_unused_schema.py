"""Removes tables and columns from the original schema that PEA never used.

Checked on 2026-11-23 against the code and the live database (293 people): every one is empty there and nothing in
the app reads it.
- password_credentials, identity_providers (and auth_identities.identity_provider_id): PEA signs in with Google
  only, configured in the server's settings.
- profiles.public_slug, positions.category, organization_domains.verified_by, organization_units.code,
  organization_memberships.joined_on, audit_log.request_id (not part of the audit hash): never set or shown.
- deleted_by / deletion_reason on users, organizations and organization_units, and files.deletion_reason: nothing
  deletes those (people are deactivated; files.deleted_by is kept, replaced photos set it).
- files.scan_status (and its type): there's no virus scanner, so it said "pending" or "clean" without meaning.
- users.preferred_locale: the interface language is kept in the browser; this was always "ka".

Kept on purpose, although empty: organization_memberships.employee_number (to match people with an HR system)
and audit_log.agent_run_id (for actions taken by AI agents), should those come.

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-23
"""

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        drop table password_credentials;
        alter table auth_identities drop column identity_provider_id;
        drop table identity_providers;

        alter table profiles drop column public_slug;
        alter table positions drop column category;
        alter table organization_domains drop column verified_by;
        alter table organization_units drop column code;
        alter table organization_memberships drop column joined_on;
        alter table audit_log drop column request_id;

        alter table users drop column deleted_by, drop column deletion_reason;
        alter table organizations drop column deleted_by, drop column deletion_reason;
        alter table organization_units drop column deleted_by, drop column deletion_reason;
        alter table files drop column deletion_reason;

        alter table files drop column scan_status;
        drop type scan_status;

        alter table users drop column preferred_locale;
    """)


def downgrade() -> None:
    # As the original schema created them (sql/0001_identity_up.sql, sql/0002_structure_up.sql, 0004); emptied data
    # can't come back, but nothing was stored in any of them.
    op.execute("""
        alter table users add column preferred_locale text not null default 'ka';

        create type scan_status as enum ('pending', 'clean', 'infected', 'failed');
        alter table files add column scan_status scan_status not null default 'pending';

        alter table files add column deletion_reason text;
        alter table organization_units add column deleted_by uuid, add column deletion_reason text;
        alter table organization_units add constraint organization_units_deleted_by_fkey
          foreign key (deleted_by) references users (id) on delete restrict;
        create index organization_units_deleted_by_idx on organization_units (deleted_by);
        alter table organizations add column deleted_by uuid, add column deletion_reason text;
        alter table organizations add constraint organizations_deleted_by_fkey
          foreign key (deleted_by) references users (id) on delete restrict;
        create index organizations_deleted_by_idx on organizations (deleted_by);
        alter table users add column deleted_by uuid, add column deletion_reason text;
        alter table users add constraint users_deleted_by_fkey
          foreign key (deleted_by) references users (id) on delete restrict;
        create index users_deleted_by_idx on users (deleted_by);

        alter table audit_log add column request_id uuid;
        alter table organization_memberships add column joined_on date;
        alter table organization_units add column code text;
        create unique index organization_units_organization_id_code_key
          on organization_units (organization_id, code) where code is not null and deleted_at is null;
        alter table organization_domains add column verified_by uuid;
        alter table organization_domains add constraint organization_domains_verified_by_fkey
          foreign key (verified_by) references users (id) on delete restrict;
        create index organization_domains_verified_by_idx on organization_domains (verified_by);
        alter table positions add column category text;
        alter table profiles add column public_slug text unique;

        create table identity_providers (
          id uuid primary key default gen_random_uuid(),
          organization_id uuid not null references organizations (id) on delete restrict,
          kind auth_provider not null,
          display_name text not null,
          issuer text,
          client_id text,
          client_secret_ref text,
          enabled boolean not null default true,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now()
        );
        create index identity_providers_organization_id_idx on identity_providers (organization_id);
        alter table auth_identities add column identity_provider_id uuid
          references identity_providers (id) on delete restrict;
        create index auth_identities_identity_provider_id_idx on auth_identities (identity_provider_id);
        create table password_credentials (
          user_id uuid primary key references users (id) on delete restrict,
          password_hash text not null,
          algorithm text not null default 'argon2id',
          changed_at timestamptz not null default now()
        );
    """)
