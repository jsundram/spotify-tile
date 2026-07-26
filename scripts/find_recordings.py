#!/usr/bin/env python3
"""Find recordings of a composer's works, newest first, with a "most-listened" flag.

Discovery aid for choosing what to render/post next. It follows the repo's
"build the list from a keyless source, resolve on Spotify later" plan and keeps
the two popularity signals independent so neither is load-bearing:

  1. MusicBrainz (keyless) -> the canonical recording list, one row per
     release-group, sorted by first-release-date descending (newest first).
  2. For each recording, resolve it to a Spotify album (client-credentials)
     and rank its movements by two independent signals -- Spotify track
     ``popularity`` and Last.fm ``playcount`` -- to flag a candidate movement.

Optionally diff against a rendered-playlist ``manifest.json`` (written by
``render_playlist.py``) so recordings you already have are marked KNOWN; pass
``--new-only`` to hide them.

Nothing here touches the deterministic render pipeline -- it only helps decide
what to feed it. This script is network-bound; it cannot run in an environment
whose egress policy blocks musicbrainz.org / api.spotify.com / last.fm.

Usage:
    uv run python scripts/find_recordings.py                       # Boccherini quartets
    uv run python scripts/find_recordings.py --composer Haydn --work quartet
    uv run python scripts/find_recordings.py --manifest output/playlists/<id>/manifest.json --new-only
    uv run python scripts/find_recordings.py --limit 15 --json out.json

Credentials (env / .env, all optional -- the tool degrades gracefully):
    SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET   Spotify popularity + album links
    LASTFM_API_KEY                             Last.fm playcount signal
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from geomusic.spotify import CredentialsMissingError, SpotifyClient, SpotifyError

MB_BASE = "https://musicbrainz.org/ws/2"
# MusicBrainz asks for a descriptive User-Agent and <= 1 request/second.
MB_USER_AGENT = "geomusic-find-recordings/0.1 (https://github.com/jsundram/spotify-tile)"
LASTFM_BASE = "https://ws.audioscrobbler.com/2.0/"

# Synonyms so the MusicBrainz free-text query catches non-English release titles.
WORK_SYNONYMS = {
    "quartet": ["quartet", "quartets", "streichquartett", "streichquartette", "quatuor", "cuarteto"],
    "quintet": ["quintet", "quintets", "streichquintett", "quintetto", "quinteto"],
}


# --------------------------------------------------------------------------- MusicBrainz


def _lucene_or(terms: list[str]) -> str:
    return "(" + " OR ".join(terms) + ")"


def build_mb_query(composer: str, work: str) -> str:
    """A Lucene query for release-groups of ``composer``'s ``work`` (quartets, etc.)."""
    include = _lucene_or(WORK_SYNONYMS.get(work.lower(), [work]))
    clauses = [composer, include, "primarytype:Album"]
    # Boccherini's quintets swamp his quartets on streaming; exclude the other form.
    for other, syns in WORK_SYNONYMS.items():
        if other != work.lower():
            clauses.append("NOT " + _lucene_or(syns))
    return " AND ".join(clauses)


def _mb_date_key(date: str) -> tuple[int, int, int]:
    """Sortable key from a partial MusicBrainz date; missing/blank sorts oldest."""
    parts = (date or "").split("-")
    nums = [int(p) for p in parts if p.isdigit()]
    nums += [0] * (3 - len(nums))
    return (nums[0], nums[1], nums[2])


def fetch_musicbrainz(composer: str, work: str, limit: int) -> list[dict[str, Any]]:
    """Release-groups for ``composer``'s ``work``, newest first (by first-release-date)."""
    query = build_mb_query(composer, work)
    with httpx.Client(timeout=30.0, headers={"User-Agent": MB_USER_AGENT}) as http:
        resp = http.get(
            f"{MB_BASE}/release-group",
            params={"query": query, "fmt": "json", "limit": max(limit * 3, 25)},
        )
    resp.raise_for_status()
    groups = resp.json().get("release-groups", [])
    rows: list[dict[str, Any]] = []
    for g in groups:
        performers = ", ".join(ac.get("name", "") for ac in g.get("artist-credit", []))
        rows.append(
            {
                "mbid": g.get("id", ""),
                "title": g.get("title", ""),
                "date": g.get("first-release-date", ""),
                "performers": performers.replace(" ,", "").strip(),
            }
        )
    rows.sort(key=lambda r: _mb_date_key(r["date"]), reverse=True)
    return rows[:limit]


# --------------------------------------------------------------------------- Spotify


def resolve_on_spotify(client: SpotifyClient, composer: str, row: dict[str, Any]) -> dict | None:
    """Best-effort match of a MusicBrainz recording to a Spotify album (top hit)."""
    # Title often already reads "Boccherini: String Quartets ..."; add the composer
    # surname and performer to disambiguate when it does not.
    surname = composer.split()[-1]
    query = f"{row['title']} {surname} {row['performers']}".strip()
    try:
        hits = client.search_album(query, limit=5)
    except SpotifyError:
        return None
    return hits[0] if hits else None


def rank_movements(client: SpotifyClient, album_id: str) -> list[dict[str, Any]]:
    """Album tracks with Spotify popularity, in track order (popularity may be absent)."""
    album = client.get_album(album_id)
    ids = [t["id"] for t in album.get("tracks", {}).get("items", []) if t.get("id")]
    if not ids:
        return []
    tracks = client.get_tracks(ids)
    return [
        {
            "id": t.get("id", ""),
            "name": t.get("name", ""),
            "url": (t.get("external_urls") or {}).get("spotify", ""),
            "popularity": t.get("popularity"),
            "artists": [a.get("name", "") for a in t.get("artists", [])],
        }
        for t in tracks
    ]


# --------------------------------------------------------------------------- Last.fm


def lastfm_playcount(http: httpx.Client, api_key: str, artist: str, track: str) -> int | None:
    """Global scrobble count for a track, or None when Last.fm has no data for it."""
    try:
        resp = http.get(
            LASTFM_BASE,
            params={
                "method": "track.getInfo",
                "api_key": api_key,
                "artist": artist,
                "track": track,
                "autocorrect": "1",
                "format": "json",
            },
        )
        payload = resp.json()
    except (httpx.HTTPError, json.JSONDecodeError):
        return None
    info = payload.get("track")
    if not isinstance(info, dict):
        return None
    raw = info.get("playcount")
    return int(raw) if isinstance(raw, str) and raw.isdigit() else None


def add_lastfm(
    movements: list[dict[str, Any]], composer: str, api_key: str, delay: float = 0.25
) -> None:
    """Attach a ``playcount`` to each movement, keyed on its performing artist."""
    surname = composer.split()[-1].lower()
    with httpx.Client(timeout=20.0) as http:
        for m in movements:
            performers = [a for a in m["artists"] if surname not in a.lower()]
            artist = (performers or m["artists"] or [composer])[0]
            m["playcount"] = lastfm_playcount(http, api_key, artist, m["name"])
            time.sleep(delay)


# --------------------------------------------------------------------------- ranking


def _ranks(values: list[Any]) -> list[int | None]:
    """Dense rank (0 = largest) over the present numbers; None stays None."""
    order = sorted((v for v in values if v is not None), reverse=True)
    lookup = {v: i for i, v in enumerate(order)}
    return [lookup[v] if v is not None else None for v in values]


def top_movement(movements: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pick the movement that ranks best across whichever signals are present."""
    if not movements:
        return None
    pop_ranks = _ranks([m.get("popularity") for m in movements])
    play_ranks = _ranks([m.get("playcount") for m in movements])
    best, best_score = None, None
    for m, pr, plr in zip(movements, pop_ranks, play_ranks, strict=True):
        present = [r for r in (pr, plr) if r is not None]
        if not present:
            continue
        score = sum(present) / len(present)  # average rank; lower is better
        if best_score is None or score < best_score:
            best, best_score = m, score
    return best


# --------------------------------------------------------------------------- playlist diff


def load_known_track_ids(manifest_path: Path) -> set[str]:
    manifest = json.loads(manifest_path.read_text())
    return {t["id"] for t in manifest.get("tracks", []) if t.get("id")}


# --------------------------------------------------------------------------- output


def _fmt_int(n: int | None) -> str:
    return f"{n:,}" if isinstance(n, int) else "—"


def print_digest(rows: list[dict[str, Any]], *, new_only: bool) -> None:
    shown = 0
    for row in rows:
        if new_only and row.get("known"):
            continue
        shown += 1
        tag = "KNOWN" if row.get("known") else "new"
        date = row["date"] or "????"
        print(f"\n[{date:>10}] {row['title']}  ({tag})")
        if row["performers"]:
            print(f"             {row['performers']}")
        album = row.get("spotify_album")
        if album:
            print(f"             Spotify: {album['name']} - {album['url']}")
        elif row.get("resolved") is False:
            print("             Spotify: (no confident match found)")
        best = row.get("top_movement")
        if best:
            print(
                f"             ★ most-listened: {best['name']}\n"
                f"               popularity={_fmt_int(best.get('popularity'))}  "
                f"lastfm plays={_fmt_int(best.get('playcount'))}\n"
                f"               {best.get('url', '')}"
            )
    print(f"\n{shown} recording(s) shown"
          f"{' (new only)' if new_only else ''} of {len(rows)} found.")


# --------------------------------------------------------------------------- main


def build_rows(args: argparse.Namespace, known_ids: set[str]) -> list[dict[str, Any]]:
    rows = fetch_musicbrainz(args.composer, args.work, args.limit)
    print(f"MusicBrainz: {len(rows)} {args.composer} {args.work} recording(s).", file=sys.stderr)

    client: SpotifyClient | None = None
    try:
        client = SpotifyClient()
    except CredentialsMissingError:
        print("(no Spotify credentials; listing recordings without popularity/links)",
              file=sys.stderr)

    lastfm_key = args.lastfm_key
    for row in rows:
        row["known"] = False
        row["resolved"] = None
        if client is None:
            continue
        album = resolve_on_spotify(client, args.composer, row)
        row["resolved"] = album is not None
        if album is None:
            continue
        row["spotify_album"] = {
            "id": album.get("id", ""),
            "name": album.get("name", ""),
            "url": (album.get("external_urls") or {}).get("spotify", ""),
            "release_date": album.get("release_date", ""),
        }
        try:
            movements = rank_movements(client, album["id"])
        except SpotifyError as exc:
            print(f"  ({row['title']}: {exc})", file=sys.stderr)
            continue
        row["known"] = any(m["id"] in known_ids for m in movements)
        if lastfm_key:
            add_lastfm(movements, args.composer, lastfm_key)
        row["top_movement"] = top_movement(movements)
    if client is not None:
        client.close()
    return rows


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--composer", default="Boccherini", help="composer surname or full name")
    parser.add_argument("--work", default="quartet", help="work form: quartet, quintet, ...")
    parser.add_argument("--limit", type=int, default=12, help="max recordings to report")
    parser.add_argument("--manifest", type=Path, help="playlist manifest.json to mark KNOWN against")
    parser.add_argument("--new-only", action="store_true", help="hide recordings already in --manifest")
    parser.add_argument("--json", type=Path, dest="json_out", help="also write structured results here")
    parser.add_argument("--lastfm-key", default=os.environ.get("LASTFM_API_KEY", ""),
                        help="Last.fm API key (default: $LASTFM_API_KEY)")
    args = parser.parse_args()

    known_ids = load_known_track_ids(args.manifest) if args.manifest else set()
    rows = build_rows(args, known_ids)
    print_digest(rows, new_only=args.new_only)
    if args.json_out:
        args.json_out.write_text(json.dumps(rows, indent=2))
        print(f"wrote {args.json_out}", file=sys.stderr)


if __name__ == "__main__":
    main()
