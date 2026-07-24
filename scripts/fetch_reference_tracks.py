"""Fetch Spotify fixtures for the reference tracks.

Writes cache-format JSON documents to tests/fixtures/spotify/<slug>.json so
tests and reference renders run without network access.  Track ids come from
the source data screenshots where available; otherwise the track is located
via search and verified by name/artist.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

from geomusic import cache
from geomusic.spotify import SpotifyClient, SpotifyError

FIXTURES = ROOT / "tests" / "fixtures" / "spotify"

# slug -> (track_id or None, search query, expected name substring)
TRACKS = {
    "lover-you-shouldve-come-over": (
        "6Jv7kjGkhY2fT4yuBF3aTz",  # data/Screenshot-of-Excel.png
        None,
        "Lover, You Should've Come Over",
    ),
    "vienna": ("4U45aEWtQhrm8A5mxPaFZ7", None, "Vienna"),  # Screenshot-of-Excel.png
    "bohemian-rhapsody": ("1AhDOtG9vPSOmsWgNW0BEY", None, "Bohemian Rhapsody"),
    "real-love-baby": ("0Z57YWES04xGh3AImDz6Qr", None, "Real Love Baby"),
    "holocene": (None, "Holocene Bon Iver", "Holocene"),  # id transcription ambiguous
    "judas": (None, "Judas Lady Gaga", "Judas"),
    "sunset": (None, "Sunset The xx", "Sunset"),
    "the-adults-are-talking": (
        None,
        "The Adults Are Talking The Strokes",
        "The Adults Are Talking",
    ),
}


def slim(track: dict) -> dict:
    """Drop the noisy market lists; keep everything else verbatim."""
    track = dict(track)
    track.pop("available_markets", None)
    if isinstance(track.get("album"), dict):
        track["album"] = dict(track["album"])
        track["album"].pop("available_markets", None)
    return track


def main() -> None:
    load_dotenv(ROOT / ".env")
    FIXTURES.mkdir(parents=True, exist_ok=True)
    failures = []
    with SpotifyClient() as client:
        for slug, (track_id, query, expect) in TRACKS.items():
            out = FIXTURES / f"{slug}.json"
            try:
                if track_id is None:
                    hits = client.search_track(query)
                    match = next(
                        (t for t in hits if expect.lower() in t["name"].lower()), None
                    )
                    if match is None:
                        raise SpotifyError(f"no search hit for {query!r}")
                    track_id = match["id"]
                raw_track = client.get_track(track_id)
                if expect.lower() not in raw_track["name"].lower():
                    raise SpotifyError(
                        f"{slug}: expected name containing {expect!r}, got "
                        f"{raw_track['name']!r}"
                    )
                raw_features = client.get_audio_features(track_id)
                doc = cache.make_doc(slim(raw_track), raw_features)
                out.write_text(json.dumps(doc, indent=2))
                first4 = track_id[:4]
                flags = tuple(c.isdigit() for c in first4)
                print(
                    f"{slug:28s} {track_id} '{first4}' {flags} "
                    f"key={raw_features['key']} mode={raw_features['mode']} "
                    f"loud={raw_features['loudness']} tempo={raw_features['tempo']}"
                )
            except (SpotifyError, KeyError) as exc:
                failures.append(slug)
                print(f"{slug:28s} FAILED: {exc}")
    if failures:
        sys.exit(f"failed: {', '.join(failures)}")


if __name__ == "__main__":
    main()
