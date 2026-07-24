"""ReccoBeats fallback for Spotify's deprecated /v1/audio-features endpoint.

ReccoBeats (https://reccobeats.com) mirrors the original Spotify audio-features
dataset and is keyed by Spotify track id. Spot checks against cached Spotify
responses show identical values. Two gaps: ``duration_ms`` (taken from the
Spotify track object instead) and ``time_signature`` (defaulted; unused by the
geomusic mapping).
"""

from __future__ import annotations

import time

import httpx

API_BASE = "https://api.reccobeats.com/v1"
BATCH = 40  # documented max ids per request

FEATURE_KEYS = (
    "acousticness", "danceability", "energy", "instrumentalness", "key",
    "liveness", "loudness", "mode", "speechiness", "tempo", "valence",
)


class ReccoBeatsError(RuntimeError):
    pass


def _get(client: httpx.Client, path: str, _retries: int = 2) -> dict:
    try:
        resp = client.get(f"{API_BASE}{path}")
    except httpx.HTTPError as exc:
        raise ReccoBeatsError(f"Network failure calling ReccoBeats: {exc}") from exc
    if resp.status_code == 429 and _retries > 0:
        time.sleep(float(resp.headers.get("Retry-After", "2")))
        return _get(client, path, _retries - 1)
    if resp.status_code != 200:
        raise ReccoBeatsError(f"ReccoBeats returned HTTP {resp.status_code} for {path}")
    return resp.json()


def fetch_audio_features(track_ids: list[str], *, timeout: float = 15.0) -> dict[str, dict]:
    """Map Spotify track ids to Spotify-shaped audio-features dicts.

    Ids unknown to ReccoBeats are simply absent from the result. Returned
    dicts contain FEATURE_KEYS only; callers must supply ``duration_ms`` and
    ``time_signature`` (see ``complete_features``).
    """
    result: dict[str, dict] = {}
    with httpx.Client(timeout=timeout) as client:
        uuid_to_spotify: dict[str, str] = {}
        for i in range(0, len(track_ids), BATCH):
            chunk = track_ids[i:i + BATCH]
            payload = _get(client, f"/track?ids={','.join(chunk)}")
            for item in payload.get("content", []):
                spotify_id = item.get("href", "").rstrip("/").rsplit("/", 1)[-1]
                if spotify_id in chunk:
                    uuid_to_spotify[item["id"]] = spotify_id
        uuids = list(uuid_to_spotify)
        for i in range(0, len(uuids), BATCH):
            chunk = uuids[i:i + BATCH]
            payload = _get(client, f"/audio-features?ids={','.join(chunk)}")
            for item in payload.get("content", []):
                spotify_id = uuid_to_spotify.get(item.get("id", ""))
                if spotify_id and all(item.get(k) is not None for k in FEATURE_KEYS):
                    result[spotify_id] = {k: item[k] for k in FEATURE_KEYS}
    return result


def complete_features(features: dict, raw_track: dict) -> dict:
    """Fill the fields ReccoBeats lacks so the dict satisfies AudioFeatures."""
    return {
        **features,
        "id": raw_track["id"],
        "duration_ms": raw_track.get("duration_ms", 0) or 1,
        "time_signature": 4,
        "source": "reccobeats",
    }
