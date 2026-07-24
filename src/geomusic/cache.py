"""Disk cache of raw Spotify responses, one canonical JSON document per track."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from platformdirs import user_cache_dir

SCHEMA_VERSION = 1
DEFAULT_TTL = timedelta(days=30)


class CacheError(RuntimeError):
    pass


class CacheMissError(CacheError):
    pass


def cache_dir() -> Path:
    override = os.environ.get("GEOMUSIC_CACHE_DIR")
    if override:
        return Path(override)
    return Path(user_cache_dir("geomusic")) / "spotify"


def cache_path(track_id: str) -> Path:
    return cache_dir() / f"{track_id}.json"


def make_doc(track: dict, audio_features: dict) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "fetched_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "track": track,
        "audio_features": audio_features,
    }


def save(track_id: str, doc: dict) -> Path:
    """Atomically write the cache document (temp file + rename)."""
    path = cache_path(track_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".part")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(doc, fh, indent=2)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path


def load(track_id: str, *, offline: bool = False, ttl: timedelta = DEFAULT_TTL) -> dict | None:
    """Return a cached document, or None when a (re)fetch is needed.

    A complete cached response is usable indefinitely in offline mode; in
    online mode it goes stale after ``ttl`` (audio features are treated as
    immutable, but track metadata may change).
    """
    path = cache_path(track_id)
    if not path.exists():
        if offline:
            raise CacheMissError(
                f"No cached data for track {track_id} and --offline was given. "
                f"Expected cache file: {path}"
            )
        return None
    try:
        doc = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        if offline:
            raise CacheMissError(f"Cache file {path} is corrupt: {exc}") from exc
        return None
    if not _is_complete(doc):
        if offline:
            raise CacheMissError(f"Cache file {path} is incomplete.")
        return None
    if offline:
        return doc
    if _age(doc) > ttl:
        return None
    return doc


def _is_complete(doc: dict) -> bool:
    return (
        isinstance(doc, dict)
        and doc.get("schema_version") == SCHEMA_VERSION
        and isinstance(doc.get("track"), dict)
        and isinstance(doc.get("audio_features"), dict)
    )


def _age(doc: dict) -> timedelta:
    try:
        fetched = datetime.strptime(doc["fetched_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except (KeyError, ValueError):
        return timedelta.max
    return datetime.now(UTC) - fetched
