"""Checks that the audit log hasn't been changed: every entry's hash is recomputed (app/audit.py) and must link to the
entry before it, so an edited or removed entry is found.

    uv run python -m scripts.verify_audit                       # on a developer's computer
    docker compose exec -T api python -m scripts.verify_audit   # on the server (deploy/backup.sh runs it nightly)

Prints the number of entries and the newest entry's hash. Keep that line (the nightly backup log does): if entries
are later removed from the end, the newest hash no longer matches what was printed before. Exits with 1 when the
chain is broken. Gaps in the entry numbers are normal: a change that was checked but not saved uses up a number.
"""

import hashlib
import json
import sys
from datetime import UTC

from sqlalchemy import select

from app.db import SessionLocal
from app.models import AuditLog


def expected_hashes(entry: AuditLog, prev_hash: str | None) -> list[str]:
    """The hash app/audit.py computes for this entry, and for entries from before 12 November 2026 (commit 55c7ad5)
    also the original version's, which didn't cover acting_role and before (both always empty then)."""
    row = {
        "occurred_at": entry.occurred_at.astimezone(UTC).isoformat(),
        "actor_kind": entry.actor_kind,
        "actor_user_id": str(entry.actor_user_id) if entry.actor_user_id else None,
        "acting_role": entry.acting_role,
        "organization_id": str(entry.organization_id) if entry.organization_id else None,
        "action": entry.action,
        "entity_type": entry.entity_type,
        "entity_id": entry.entity_id,
        "before": entry.before,
        "after": entry.after,
        "reason": entry.reason,
        "ip": str(entry.ip) if entry.ip is not None else None,
    }
    rows = [row]
    if entry.acting_role is None and entry.before is None:
        rows.append({key: value for key, value in row.items() if key not in ("acting_role", "before")})
    return [hashlib.sha256(((prev_hash or "") + json.dumps(one, sort_keys=True, default=str)).encode()).hexdigest()
            for one in rows]


def verify() -> tuple[int, AuditLog | None, str | None]:
    """(entries checked, the newest entry, a problem or None)"""
    count = 0
    previous: AuditLog | None = None
    with SessionLocal() as db:
        for entry in db.scalars(select(AuditLog).order_by(AuditLog.id).execution_options(yield_per=1000)):
            linked = previous.row_hash if previous else None
            if entry.prev_hash != linked:
                return count, previous, (f"entry #{entry.id} doesn't link to the entry before it "
                                         f"(#{previous.id if previous else 'none'}): an entry was removed or changed")
            if entry.row_hash not in expected_hashes(entry, entry.prev_hash):
                return count, previous, f"entry #{entry.id} ({entry.action}) was changed after it was written"
            count += 1
            previous = entry
    return count, previous, None


def main() -> int:
    count, newest, problem = verify()
    if problem:
        print(f"AUDIT LOG BROKEN after {count} good entries: {problem}")
        return 1
    if newest is None:
        print("Audit log: empty")
    else:
        when = f"{newest.occurred_at.astimezone(UTC):%Y-%m-%d %H:%M} UTC"
        print(f"Audit log intact: {count} entries; newest #{newest.id} at {when}, hash {newest.row_hash}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
