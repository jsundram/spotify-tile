"""Repair audio features for tracks absent from the ReccoBeats dataset.

For each failed track in a playlist manifest:
  1. scrape the 30s preview URL from Spotify's embed page,
  2. submit the preview to ReccoBeats' analysis endpoint
     (returns loudness, tempo, speechiness, ... but NOT key/mode),
  3. parse key and mode from the track title (reliable for classical
     repertoire: "String Quartet in E-Flat Major" -> key=3, mode=1),
  4. write a cache document so render_playlist.py picks it up on rerun.

Usage:
    uv run python scripts/analyze_missing.py <playlist-id>
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from geomusic import cache

PITCH = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
KEY_RE = re.compile(
    r"\bin ([A-G])[ -]?(flat|sharp|b|#|♭|♯)?[ .]*(major|minor)", re.IGNORECASE
)
NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.DOTALL
)


def parse_key_mode(title: str) -> tuple[int, int] | None:
    m = KEY_RE.search(title)
    if not m:
        return None
    key = PITCH[m.group(1).upper()]
    accidental = (m.group(2) or "").lower()
    if accidental in {"flat", "b", "♭"}:
        key -= 1
    elif accidental in {"sharp", "#", "♯"}:
        key += 1
    mode = 1 if m.group(3).lower() == "major" else 0
    return key % 12, mode


def preview_url(client: httpx.Client, track_id: str) -> str | None:
    resp = client.get(
        f"https://open.spotify.com/embed/track/{track_id}",
        headers={"User-Agent": "Mozilla/5.0"},
        follow_redirects=True,
    )
    m = NEXT_DATA_RE.search(resp.text)
    if not m:
        return None
    def find(obj: object):
        if isinstance(obj, dict):
            if "audioPreview" in obj:
                yield obj["audioPreview"]
            for v in obj.values():
                yield from find(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from find(v)
    preview = next(find(json.loads(m.group(1))), None)
    return (preview or {}).get("url")


def analyze(client: httpx.Client, audio: bytes) -> dict | None:
    resp = client.post(
        "https://api.reccobeats.com/v1/analysis/audio-features",
        files={"audioFile": ("preview.mp3", audio, "audio/mpeg")},
    )
    if resp.status_code != 200:
        print(f"    analysis HTTP {resp.status_code}: {resp.text[:120]}")
        return None
    return resp.json()


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
            track_id, name = t["id"], t["name"]
            print(f"  {name[:60]}")
            key_mode = parse_key_mode(name)
            if key_mode is None:
                print("    SKIP: no key/mode in title")
                continue
            url = preview_url(client, track_id)
            if not url:
                print("    SKIP: no preview available")
                continue
            audio = client.get(url).content
            features = analyze(client, audio)
            if not features:
                continue
            key, mode = key_mode
            raw_features = {
                **features,
                "id": track_id,
                "key": key,
                "mode": mode,
                "duration_ms": t.get("duration_ms") or 1,
                "time_signature": 4,
                "source": "reccobeats-analysis+title-key",
            }
            # Rebuild the raw track object from the manifest entry (enough for
            # TrackMetadata.from_api and the story script's needs).
            raw_track = {
                "id": track_id,
                "name": name,
                "artists": [{"name": a} for a in t["artists"]],
                "album": {
                    "name": t["album"],
                    "release_date": t["album_release_date"],
                    "images": (
                        [{"url": t["album_art_url"]}] if t.get("album_art_url") else []
                    ),
                },
                "duration_ms": t.get("duration_ms"),
                "explicit": t.get("explicit", False),
                "external_urls": {"spotify": t["spotify_url"]},
            }
            cache.save(track_id, cache.make_doc(raw_track, raw_features))
            print(f"    ok: key={key} mode={mode} tempo={features.get('tempo'):.0f}")
            repaired += 1

    print(f"\nrepaired {repaired}/{len(failed)}; now rerun render_playlist.py")


if __name__ == "__main__":
    main()
