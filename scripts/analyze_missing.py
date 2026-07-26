"""Repair audio features for tracks absent from the ReccoBeats dataset.

For each failed track in a playlist manifest, run the shared preview-based
extraction (``geomusic.preview_features``: embed-page 30s preview ->
ReccoBeats analysis endpoint -> key/mode parsed from the title) and write a
cache document so render_playlist.py picks it up on rerun.

Usage:
    uv run python scripts/analyze_missing.py <playlist-id>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from geomusic import cache
from geomusic.preview_features import PreviewAnalysisError, features_from_preview


def raw_track_from_manifest(t: dict) -> dict:
    """Rebuild a raw track object from a manifest entry (enough for
    TrackMetadata.from_api and the story script's needs)."""
    return {
        "id": t["id"],
        "name": t["name"],
        "artists": [{"name": a} for a in t["artists"]],
        "album": {
            "name": t["album"],
            "release_date": t["album_release_date"],
            "images": [{"url": t["album_art_url"]}] if t.get("album_art_url") else [],
        },
        "duration_ms": t.get("duration_ms"),
        "explicit": t.get("explicit", False),
        "external_urls": {"spotify": t["spotify_url"]},
    }


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: analyze_missing.py <playlist-id>")
    manifest_path = ROOT / "output" / "playlists" / sys.argv[1] / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    failed = [t for t in manifest["tracks"] if t["status"] != "ok"]
    print(f"{len(failed)} tracks to repair")

    repaired = 0
    with httpx.Client(timeout=30.0) as client:
        for t in failed:
            print(f"  {t['name'][:60]}")
            raw_track = raw_track_from_manifest(t)
            try:
                raw_features = features_from_preview(t["id"], raw_track, client=client)
            except PreviewAnalysisError as exc:
                print(f"    SKIP: {exc}")
                continue
            cache.save(t["id"], cache.make_doc(raw_track, raw_features))
            print(
                f"    ok: key={raw_features['key']} mode={raw_features['mode']} "
                f"tempo={raw_features.get('tempo', 0):.0f}"
            )
            repaired += 1

    print(f"\nrepaired {repaired}/{len(failed)}; now rerun render_playlist.py")


if __name__ == "__main__":
    main()
