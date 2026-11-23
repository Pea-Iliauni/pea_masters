"""scripts/verify_audit.py finds audit entries that were changed or removed after they were written."""

from sqlalchemy import text

from app import audit
from app.db import engine
from scripts.verify_audit import main, verify


def write_entries(db, count=4):
    for n in range(count):
        audit.record(db, "test.entry", entity_type="test", entity_id=str(n), after={"n": n, "note": "ქართული"},
                     before={"n": n - 1} if n else None, acting_role="admin" if n % 2 else None, ip="10.0.0.1")
        db.commit()


def tamper(sql: str) -> None:
    """The table refuses changes (a trigger); only someone with the database owner's rights could do this"""
    with engine.begin() as conn:
        conn.execute(text("alter table audit_log disable trigger audit_log_append_only"))
        conn.execute(text(sql))
        conn.execute(text("alter table audit_log enable trigger audit_log_append_only"))


def test_an_untouched_log_verifies(db, capsys):
    write_entries(db)
    count, newest, problem = verify()
    assert (count, problem) == (4, None)
    assert main() == 0
    assert f"newest #{newest.id}" in capsys.readouterr().out


def test_a_changed_entry_is_found(db):
    write_entries(db)
    tamper("update audit_log set after = '{\"n\": 99}' where entity_id = '2'")
    count, _, problem = verify()
    assert count == 2 and "was changed after it was written" in problem
    assert main() == 1


def test_a_removed_entry_is_found(db):
    write_entries(db)
    tamper("delete from audit_log where entity_id = '1'")
    _, _, problem = verify()
    assert "doesn't link to the entry before it" in problem


def test_the_table_itself_refuses_changes(db):
    write_entries(db, 1)
    with engine.connect() as conn:
        try:
            conn.execute(text("update audit_log set reason = 'x'"))
            raise AssertionError("the update should have been refused")
        except Exception as refused:  # noqa: BLE001
            assert "append-only" in str(refused)
