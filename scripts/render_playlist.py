"""Render a poster for every track in a Spotify playlist.

Usage:
    uv run python scripts/render_playlist.py <playlist URL | URI | id> [--refresh]

Output goes to output/playlists/<playlist-id>/:
    manifest.json           playlist + per-track metadata, params, file paths
    contact-sheet.html      quick visual review of the whole run
    NNN-<track-id>/         track.json, parameters.json, composition.svg/.png

manifest.json is the machine-readable index for downstream scripts (e.g.
Instagram story generation): each entry carries track name, artists, album
title, album art URL, release date, duration, the derived rendering
parameters, and relative paths to the rendered graphics.
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

from geomusic import cache
from geomusic.config import config_dict, load_config
from geomusic.geometry import build_scene
from geomusic.models import TrackData
from geomusic.normalize import derive
from geomusic.reccobeats import ReccoBeatsError, complete_features, fetch_audio_features
from geomusic.render_png import svg_to_png
from geomusic.render_svg import render_svg
from geomusic.spotify import ForbiddenError, SpotifyClient, SpotifyError

PLAYLIST_ID_RE = re.compile(r"^[0-9A-Za-z]{22}$")


def parse_playlist_input(value: str) -> str:
    value = value.strip()
    if PLAYLIST_ID_RE.match(value):
        return value
    m = re.match(r"^spotify:playlist:([0-9A-Za-z]{22})$", value)
    if m:
        return m.group(1)
    if value.startswith(("http://", "https://")):
        parts = [p for p in urlparse(value).path.split("/") if p]
        if parts and parts[0].startswith("intl-"):
            parts = parts[1:]
        if len(parts) >= 2 and parts[0] == "playlist" and PLAYLIST_ID_RE.match(parts[1]):
            return parts[1]
    raise SystemExit(f"error: could not parse a playlist id from {value!r}")


def track_summary(raw: dict) -> dict:
    """Metadata a downstream (e.g. Instagram story) script needs, from the raw track."""
    album = raw.get("album") or {}
    images = album.get("images") or []
    return {
        "id": raw["id"],
        "name": raw["name"],
        "artists": [a["name"] for a in raw.get("artists", [])],
        "album": album.get("name", ""),
        "album_release_date": album.get("release_date", ""),
        "album_art_url": images[0]["url"] if images else None,
        "duration_ms": raw.get("duration_ms"),
        "explicit": raw.get("explicit", False),
        "spotify_url": (raw.get("external_urls") or {}).get(
            "spotify", f"https://open.spotify.com/track/{raw['id']}"
        ),
    }


class FeatureSource:
    """Audio features from Spotify, falling back to ReccoBeats on 403.

    Spotify's /v1/audio-features is deprecated; when the app loses access the
    whole run switches to ReccoBeats, batch-prefetching every remaining track.
    """

    def __init__(self, client: SpotifyClient, all_tracks: list[dict]) -> None:
        self._client = client
        self._all_tracks = all_tracks
        self._recco: dict[str, dict] | None = None  # None until Spotify 403s

    def features_for(self, raw_track: dict) -> dict:
        track_id = raw_track["id"]
        if self._recco is None:
            try:
                return self._client.get_audio_features(track_id)
            except ForbiddenError:
                print("  (Spotify audio-features returned 403; "
                      "switching to ReccoBeats for all tracks)")
                self._recco = {}  # never retry Spotify, even if the batch fails
                self._recco = fetch_audio_features([t["id"] for t in self._all_tracks])
        features = self._recco.get(track_id)
        if features is None:
            raise ValueError("track is not in the ReccoBeats dataset")
        return complete_features(features, raw_track)


def load_or_fetch(source: FeatureSource, raw_track: dict, *, refresh: bool) -> dict:
    """Return the cached track document, fetching audio features when needed."""
    track_id = raw_track["id"]
    doc = None if refresh else cache.load(track_id)
    if doc is None:
        raw_features = source.features_for(raw_track)
        doc = cache.make_doc(raw_track, raw_features)
        cache.save(track_id, doc)
    return doc


def write_contact_sheet(out_dir: Path, playlist: dict, entries: list[dict]) -> Path:
    cells = []
    for e in entries:
        title = html.escape(f"{e['index']:02d}. {e['name']}")
        sub = html.escape(f"{', '.join(e['artists'])} — {e['album']}")
        if e["status"] == "ok":
            img = f'<img src="{e["files"]["png"]}" loading="lazy" alt="{title}">'
            note = ""
        else:
            img = '<div class="missing">not rendered</div>'
            note = f'<p class="err">{html.escape(e.get("error", ""))}</p>'
        cells.append(
            f'<figure><a href="{e["spotify_url"]}">{img}</a>'
            f"<figcaption><strong>{title}</strong><br>{sub}</figcaption>{note}</figure>"
        )
    doc = f"""<!doctype html>
<meta charset="utf-8">
<title>{html.escape(playlist["name"])} — geomusic contact sheet</title>
<style>
  body {{ font: 14px/1.4 system-ui, sans-serif; margin: 2rem; background: #fafafa; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 1.5rem; }}
  figure {{ margin: 0; }}
  img {{ width: 100%; height: auto; display: block; box-shadow: 0 1px 4px rgb(0 0 0 / .2); }}
  .missing {{ aspect-ratio: 1; display: grid; place-items: center; background: #eee; color: #999; }}
  .err {{ color: #b00; font-size: 12px; }}
  figcaption {{ margin-top: .5rem; }}
</style>
<h1>{html.escape(playlist["name"])}</h1>
<p>{len(entries)} tracks · rendered by geomusic</p>
<div class="grid">
{"".join(cells)}
</div>
"""
    path = out_dir / "contact-sheet.html"
    path.write_text(doc)
    return path


def main() -> None:
    load_dotenv()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    refresh = "--refresh" in sys.argv
    if len(args) != 1:
        raise SystemExit(__doc__.strip().splitlines()[2].strip())
    playlist_id = parse_playlist_input(args[0])

    config = load_config(None)
    out_dir = ROOT / "output" / "playlists" / playlist_id
    out_dir.mkdir(parents=True, exist_ok=True)

    with SpotifyClient() as client:
        playlist_raw = client.get_playlist(playlist_id)
        tracks = client.get_playlist_items(playlist_id)
        print(f"playlist: {playlist_raw['name']!r} — {len(tracks)} tracks\n")

        source = FeatureSource(client, tracks)
        entries: list[dict] = []
        for i, raw_track in enumerate(tracks, start=1):
            entry = track_summary(raw_track)
            entry["index"] = i
            slug = f"{i:03d}-{raw_track['id']}"
            track_dir = out_dir / slug
            label = f"{i:03d} {entry['name'][:40]:40s}"
            try:
                doc = load_or_fetch(source, raw_track, refresh=refresh)
                data = TrackData.from_cache_doc(doc)
                params = derive(data, config)
                scene = build_scene(data, params, config)
                svg = render_svg(scene, data, config, cache_fetched_at=doc.get("fetched_at"))

                track_dir.mkdir(parents=True, exist_ok=True)
                (track_dir / "track.json").write_text(json.dumps(doc, indent=2))
                payload = {"parameters": params.model_dump(), "config": config_dict(config)}
                (track_dir / "parameters.json").write_text(json.dumps(payload, indent=2))
                (track_dir / "composition.svg").write_text(svg)
                svg_to_png(svg, track_dir / "composition.png")

                entry.update(
                    status="ok",
                    files={
                        "dir": slug,
                        "svg": f"{slug}/composition.svg",
                        "png": f"{slug}/composition.png",
                        "track_json": f"{slug}/track.json",
                        "parameters_json": f"{slug}/parameters.json",
                    },
                    parameters=params.model_dump(),
                )
                print(f"{label} {params.composition:6s} key={params.key:2d} "
                      f"cells={params.cell_count:2d}")
            except (SpotifyError, ReccoBeatsError, ValueError, KeyError) as exc:
                entry.update(status="error", error=str(exc), files=None)
                print(f"{label} FAILED: {exc}")
            entries.append(entry)

    manifest = {
        "playlist": {
            "id": playlist_id,
            "name": playlist_raw.get("name", ""),
            "description": playlist_raw.get("description", ""),
            "owner": (playlist_raw.get("owner") or {}).get("display_name", ""),
            "url": (playlist_raw.get("external_urls") or {}).get("spotify", ""),
        },
        "config": config_dict(config),
        "tracks": entries,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    ok = sum(1 for e in entries if e["status"] == "ok")
    sheet = write_contact_sheet(out_dir, manifest["playlist"], entries)
    print(f"\n{ok}/{len(entries)} rendered -> {out_dir}")
    print(f"manifest: {out_dir / 'manifest.json'}")
    print(f"review:   {sheet}")


if __name__ == "__main__":
    main()
