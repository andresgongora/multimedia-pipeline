"""Tests: shared/download_registry.py — filter_new, record, record_many, is_known, forget.

Usage:
    uv run test/shared/download_registry.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from shared import download_registry as reg

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {detail}")


def _tmp_db() -> Path:
    """Return a path inside a fresh temp dir; file itself does not yet exist."""
    d = tempfile.mkdtemp()
    return Path(d) / "registry.json"


# ---------------------------------------------------------------------------
# Single URL
# ---------------------------------------------------------------------------


def test_record_single_url() -> None:
    print("\n--- test_record_single_url ---")
    db = _tmp_db()
    reg.record("https://youtu.be/a", db)
    check("known after record", reg.is_known("https://youtu.be/a", db))
    check("filtered out after record", reg.filter_new(["https://youtu.be/a"], db) == [])


def test_record_single_url_with_metadata() -> None:
    print("\n--- test_record_single_url_with_metadata ---")
    db = _tmp_db()
    reg.record("https://youtu.be/a", db, metadata={"title": "Song A"})
    data = json.loads(db.read_text())
    check("metadata persisted", data["https://youtu.be/a"]["title"] == "Song A")
    check("timestamp present", "downloaded_at" in data["https://youtu.be/a"])


# ---------------------------------------------------------------------------
# Multi URL
# ---------------------------------------------------------------------------


def test_record_many_urls() -> None:
    print("\n--- test_record_many_urls ---")
    db = _tmp_db()
    reg.record_many(
        {"https://youtu.be/a": {"title": "A"}, "https://youtu.be/b": None},
        db,
    )
    check("a known", reg.is_known("https://youtu.be/a", db))
    check("b known", reg.is_known("https://youtu.be/b", db))
    new = reg.filter_new(["https://youtu.be/a", "https://youtu.be/b", "https://youtu.be/c"], db)
    check("only c is new", new == ["https://youtu.be/c"], str(new))


def test_filter_new_preserves_order() -> None:
    print("\n--- test_filter_new_preserves_order ---")
    db = _tmp_db()
    reg.record("https://youtu.be/b", db)
    urls = ["https://youtu.be/c", "https://youtu.be/a", "https://youtu.be/b"]
    new = reg.filter_new(urls, db)
    check("order preserved, b dropped", new == ["https://youtu.be/c", "https://youtu.be/a"], str(new))


def test_record_many_single_load_save() -> None:
    print("\n--- test_record_many_single_load_save ---")
    # Behavioral proxy: after record_many with N urls, all N are known and
    # the file contains exactly N entries (no partial/duplicate writes).
    db = _tmp_db()
    urls: dict[str, dict | None] = {f"https://youtu.be/{i}": None for i in range(5)}
    reg.record_many(urls, db)
    data = json.loads(db.read_text())
    check("all 5 entries present", len(data) == 5, str(len(data)))


# ---------------------------------------------------------------------------
# Missing DB file
# ---------------------------------------------------------------------------


def test_filter_new_missing_db_file() -> None:
    print("\n--- test_filter_new_missing_db_file ---")
    db = _tmp_db()
    check("db file does not exist yet", not db.exists())
    new = reg.filter_new(["https://youtu.be/a", "https://youtu.be/b"], db)
    check(
        "all urls treated as new",
        new == ["https://youtu.be/a", "https://youtu.be/b"],
        str(new),
    )
    check("db file created after filter_new", db.exists())


def test_is_known_missing_db_file() -> None:
    print("\n--- test_is_known_missing_db_file ---")
    db = _tmp_db()
    check("unknown when db absent", not reg.is_known("https://youtu.be/a", db))


# ---------------------------------------------------------------------------
# Deleting a URL not in the DB
# ---------------------------------------------------------------------------


def test_forget_url_not_in_db() -> None:
    print("\n--- test_forget_url_not_in_db ---")
    db = _tmp_db()
    reg.record("https://youtu.be/a", db)
    result = reg.forget("https://youtu.be/does-not-exist", db)
    check("forget returns False for unknown url", result is False)
    check("existing entry untouched", reg.is_known("https://youtu.be/a", db))


def test_forget_url_not_in_db_missing_file() -> None:
    print("\n--- test_forget_url_not_in_db_missing_file ---")
    db = _tmp_db()
    check("db file does not exist yet", not db.exists())
    result = reg.forget("https://youtu.be/a", db)
    check("forget is a no-op, no crash", result is False)


def test_forget_url_present() -> None:
    print("\n--- test_forget_url_present ---")
    db = _tmp_db()
    reg.record("https://youtu.be/a", db)
    result = reg.forget("https://youtu.be/a", db)
    check("forget returns True for known url", result is True)
    check("url no longer known", not reg.is_known("https://youtu.be/a", db))


# ---------------------------------------------------------------------------
# Other tests: expiry / self-clean, corrupt file, metadata overwrite
# ---------------------------------------------------------------------------


def test_expired_entry_treated_as_new() -> None:
    print("\n--- test_expired_entry_treated_as_new ---")
    db = _tmp_db()
    reg.record("https://youtu.be/a", db)
    # max_age_days=0 -> cutoff is "now", any real timestamp is older than "now"
    new = reg.filter_new(["https://youtu.be/a"], db, max_age_days=0)
    check("expired entry re-surfaces as new", new == ["https://youtu.be/a"], str(new))


def test_default_retains_old_entry() -> None:
    print("\n--- test_default_retains_old_entry ---")
    db = _tmp_db()
    old_ts = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_text(json.dumps({"https://youtu.be/a": {"downloaded_at": old_ts}}))
    new = reg.filter_new(["https://youtu.be/a"], db)
    check("old entry remains known by default", new == [], str(new))
    data = json.loads(db.read_text())
    check("old entry remains persisted", "https://youtu.be/a" in data, str(data))


def test_expired_entry_pruned_from_file() -> None:
    print("\n--- test_expired_entry_pruned_from_file ---")
    db = _tmp_db()
    old_ts = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_text(json.dumps({"https://youtu.be/a": {"downloaded_at": old_ts}}))
    reg.filter_new(["https://youtu.be/a"], db, max_age_days=60)
    data = json.loads(db.read_text())
    check("expired entry removed from persisted file", "https://youtu.be/a" not in data, str(data))


def test_entry_missing_timestamp_treated_as_invalid() -> None:
    print("\n--- test_entry_missing_timestamp_treated_as_invalid ---")
    db = _tmp_db()
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_text(json.dumps({"https://youtu.be/a": {"title": "no timestamp"}}))
    check("treated as unknown/invalid", not reg.is_known("https://youtu.be/a", db))


def test_corrupt_db_file_treated_as_empty() -> None:
    print("\n--- test_corrupt_db_file_treated_as_empty ---")
    db = _tmp_db()
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_text("{not valid json")
    new = reg.filter_new(["https://youtu.be/a"], db)
    check("corrupt file treated as empty registry, no crash", new == ["https://youtu.be/a"], str(new))


def test_record_overwrites_existing_metadata() -> None:
    print("\n--- test_record_overwrites_existing_metadata ---")
    db = _tmp_db()
    reg.record("https://youtu.be/a", db, metadata={"title": "Old"})
    reg.record("https://youtu.be/a", db, metadata={"title": "New"})
    data = json.loads(db.read_text())
    check("metadata overwritten, not merged", data["https://youtu.be/a"]["title"] == "New")


if __name__ == "__main__":
    test_record_single_url()
    test_record_single_url_with_metadata()
    test_record_many_urls()
    test_filter_new_preserves_order()
    test_record_many_single_load_save()
    test_filter_new_missing_db_file()
    test_is_known_missing_db_file()
    test_forget_url_not_in_db()
    test_forget_url_not_in_db_missing_file()
    test_forget_url_present()
    test_expired_entry_treated_as_new()
    test_default_retains_old_entry()
    test_expired_entry_pruned_from_file()
    test_entry_missing_timestamp_treated_as_invalid()
    test_corrupt_db_file_treated_as_empty()
    test_record_overwrites_existing_metadata()

    print(f"\n{'=' * 40}")
    print(f"Results: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
