"""Shared download registry — tracks previously downloaded URLs to skip re-downloads.

Not a stage: this module holds cross-run persistent state (a small JSON
database keyed by URL), which stage contracts explicitly forbid ("no shared
mutable state"). Pipelines own the database file path and lifecycle — pass
it in explicitly, same as ``output_dir``/``config_path``.

Self-cleaning: entries older than ``max_age_days`` are dropped whenever the
registry is read (via :func:`filter_new`). There is no separate prune
schedule — pruning happens lazily on read.

Storage format (JSON):
    {
      "url1": {"downloaded_at": "2026-08-31T12:00:00+00:00", "title": "..."},
      "url2": {"downloaded_at": "...", ...}
    }

Typical pipeline usage:
    from shared import download_registry as registry

    urls = fetch_youtube_playlist.run(playlist_url)["video_urls"]
    new_urls = registry.filter_new(urls, db_path, max_age_days=60)

    for url in new_urls:
        download_youtube_media.run(url, output_path)
        registry.record(url, db_path, metadata={"title": "..."})

    # Or batch (single load/save):
    registry.record_many({url: {"title": "..."} for url in new_urls}, db_path)
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_MAX_AGE_DAYS = 60


# ---------------------------------------------------------------------------
# Internal load/save/prune
# ---------------------------------------------------------------------------


def _load(db_path: Path | str) -> dict[str, dict]:
    """Load the registry from *db_path*. Returns empty dict if missing/corrupt."""
    path = Path(db_path)
    if not path.exists():
        return {}
    try:
        with path.open() as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(db_path: Path | str, entries: dict[str, dict]) -> None:
    """Persist *entries* to *db_path*, creating parent directories as needed."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(entries, f, indent=2, sort_keys=True)


def _prune(entries: dict[str, dict], max_age_days: float) -> dict[str, dict]:
    """Return a new dict with entries older than *max_age_days* removed.

    Entries with a missing or unparsable ``downloaded_at`` are dropped
    (treated as expired) rather than kept indefinitely.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    kept: dict[str, dict] = {}
    for url, meta in entries.items():
        raw = meta.get("downloaded_at") if isinstance(meta, dict) else None
        try:
            downloaded_at = datetime.fromisoformat(raw) if raw else None
        except ValueError:
            downloaded_at = None
        if downloaded_at is not None and downloaded_at >= cutoff:
            kept[url] = meta
    return kept


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def filter_new(
    urls: list[str],
    db_path: Path | str,
    *,
    max_age_days: float = DEFAULT_MAX_AGE_DAYS,
) -> list[str]:
    """Return the subset of *urls* not present in the (pruned) registry.

    Prunes expired entries and persists the pruned registry as a side
    effect, so the database self-cleans on every filter call. Order of
    *urls* is preserved.
    """
    entries = _prune(_load(db_path), max_age_days)
    _save(db_path, entries)
    return [url for url in urls if url not in entries]


def record(url: str, db_path: Path | str, *, metadata: dict | None = None) -> None:
    """Record *url* as downloaded now, merging in optional *metadata*.

    For multiple URLs, prefer :func:`record_many` — one load/save instead
    of one per call.
    """
    record_many({url: metadata}, db_path)


def record_many(urls: dict[str, dict | None], db_path: Path | str) -> None:
    """Record multiple URLs as downloaded now in a single load/save.

    Args:
        urls: mapping of url -> optional metadata dict (merged per entry).
        db_path: registry file path.
    """
    entries = _load(db_path)
    now = datetime.now(timezone.utc).isoformat()
    for url, metadata in urls.items():
        entries[url] = {"downloaded_at": now, **(metadata or {})}
    _save(db_path, entries)


def is_known(url: str, db_path: Path | str, *, max_age_days: float = DEFAULT_MAX_AGE_DAYS) -> bool:
    """Return True if *url* has a non-expired entry in the registry."""
    entries = _prune(_load(db_path), max_age_days)
    return url in entries


def forget(url: str, db_path: Path | str) -> bool:
    """Remove *url* from the registry, if present.

    Idempotent: removing a URL not in the registry is a no-op, not an
    error. Returns True if an entry was removed, False otherwise.
    """
    entries = _load(db_path)
    if url not in entries:
        return False
    del entries[url]
    _save(db_path, entries)
    return True
