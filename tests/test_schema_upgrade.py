import sqlite3
import subprocess
import sys
from contextlib import closing

import pytest

from kdrx.runtime.store import SQLiteStore


def test_kill_during_schema_upgrade_rolls_back_ddl_and_reopens(tmp_path):
    path = tmp_path / "db"
    old_database(path)
    script = """
import os,sys
from contextlib import contextmanager
from pathlib import Path
from kdrx.runtime.store import SQLiteStore
original=SQLiteStore.connect
class Interrupted:
    def __init__(self,db): self.db=db
    def __getattr__(self,name): return getattr(self.db,name)
    def executescript(self,sql):
        self.db.executescript(sql.split('PRAGMA user_version=3;')[0])
        os._exit(94)
@contextmanager
def connect(self):
    with original(self) as db: yield Interrupted(db)
SQLiteStore.connect=connect
SQLiteStore(Path(sys.argv[1]))
"""
    child = subprocess.run(
        [sys.executable, "-c", script, str(path)], capture_output=True
    )
    assert child.returncode == 94, child.stderr
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='notifications'"
        ).fetchone()
    assert SQLiteStore(path).events("r")[0]["kind"] == "before_upgrade"


def old_database(path):
    store = SQLiteStore(path)
    store.append_event("r", {"kind": "before_upgrade"})
    with store.transaction() as db:
        for table in (
            "coordination_policies",
            "coordination_messages",
            "subscriptions",
            "notifications",
            "notification_inbox",
            "resource_locks",
        ):
            db.execute(f"DROP TABLE {table}")
        db.execute("PRAGMA user_version=2")


def test_upgrade_preserves_state_and_leaves_read_only_preupgrade_backup(tmp_path):
    path = tmp_path / "db"
    old_database(path)
    store = SQLiteStore(path)
    assert store.integrity_check()
    assert [e["kind"] for e in store.events("r")] == ["before_upgrade"]
    assert store.migration_backup.is_file()
    with closing(
        sqlite3.connect(store.migration_backup.as_uri() + "?mode=ro", uri=True)
    ) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
        with pytest.raises(sqlite3.OperationalError):
            db.execute("DELETE FROM events")
    assert SQLiteStore(path).migration_backup is None


def test_failed_backup_leaves_database_at_previous_version(tmp_path, monkeypatch):
    path = tmp_path / "db"
    old_database(path)

    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr(SQLiteStore, "backup", fail)
    with pytest.raises(OSError):
        SQLiteStore(path)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
        assert not db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='notifications'"
        ).fetchone()
