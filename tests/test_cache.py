import json
from datetime import UTC, datetime, timedelta

import pytest

from geomusic import cache


@pytest.fixture(autouse=True)
def tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOMUSIC_CACHE_DIR", str(tmp_path / "cache"))
    return tmp_path / "cache"


def make_doc(fetched_at=None):
    doc = cache.make_doc({"id": "x" * 22, "name": "T"}, {"tempo": 120})
    if fetched_at is not None:
        doc["fetched_at"] = fetched_at
    return doc


def test_miss_returns_none():
    assert cache.load("a" * 22) is None


def test_offline_miss_raises():
    with pytest.raises(cache.CacheMissError):
        cache.load("a" * 22, offline=True)


def test_save_and_hit():
    doc = make_doc()
    path = cache.save("a" * 22, doc)
    assert path.exists()
    assert cache.load("a" * 22) == doc


def test_expired_by_ttl_but_usable_offline():
    old = (datetime.now(UTC) - timedelta(days=45)).strftime("%Y-%m-%dT%H:%M:%SZ")
    cache.save("a" * 22, make_doc(old))
    assert cache.load("a" * 22) is None  # online: stale
    assert cache.load("a" * 22, offline=True) is not None  # offline: indefinite


def test_corrupt_file(tmp_cache):
    path = cache.cache_path("a" * 22)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json")
    assert cache.load("a" * 22) is None
    with pytest.raises(cache.CacheMissError):
        cache.load("a" * 22, offline=True)


def test_incomplete_doc_is_a_miss():
    doc = make_doc()
    del doc["audio_features"]
    path = cache.cache_path("a" * 22)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc))
    assert cache.load("a" * 22) is None


def test_atomic_write_leaves_no_partials(tmp_cache):
    cache.save("a" * 22, make_doc())
    leftovers = list(tmp_cache.glob("*.part"))
    assert leftovers == []
