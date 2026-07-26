"""Preview-based audio-feature extraction for tracks missing from ReccoBeats.

Third feature source, tried after Spotify's ``/v1/audio-features`` (403 for
post-2024 apps) and the ReccoBeats dataset (which lags new releases): scrape
the public 30-second preview URL from Spotify's embed page, submit the MP3 to
ReccoBeats' analysis endpoint, and parse key/mode from the key named in the
track title -- the analysis endpoint measures loudness, tempo, speechiness,
etc. but not key/mode. Title keys are reliable for classical repertoire
("String Quartet in E-Flat Major" -> key=3, mode=1; Spanish solfege "en Do
Menor" also handled).

Caveat: the title names the *work's* home key, so every movement inherits it
even when its music sits in another key -- unlike Spotify's per-track audio
estimate. Results are cached upstream like any other fetch (docs carry
``source="reccobeats-analysis+title-key"``), so re-renders stay deterministic.
"""

from __future__ import annotations

import json
import re
import time

import httpx

from .reccobeats import complete_features

ANALYSIS_URL = "https://api.reccobeats.com/v1/analysis/audio-features"
EMBED_URL = "https://open.spotify.com/embed/track/{track_id}"
SOURCE_TAG = "reccobeats-analysis+title-key"

_PITCH = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_SOLFEGE = {"do": "C", "re": "D", "mi": "E", "fa": "F", "sol": "G", "la": "A", "si": "B"}
_FLAT_WORDS = {"flat", "b", "♭", "bemol"}
_KEY_EN_RE = re.compile(
    r"\bin ([A-G])[ -]?(flat|sharp|b|#|♭|♯)?[ .]*(major|minor)", re.IGNORECASE
)
_KEY_ES_RE = re.compile(
    r"\ben (Do|Re|Mi|Fa|Sol|La|Si)(?:\s+(Bemol|Sostenido))?\s+(Mayor|Menor)", re.IGNORECASE
)
_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.DOTALL
)
_AUDIO_PREVIEW_RE = re.compile(r'audioPreview":\{"url":"([^"]+)"')


class PreviewAnalysisError(RuntimeError):
    """Preview-based extraction failed (no title key, no preview, or API error)."""


def parse_key_mode(title: str) -> tuple[int, int] | None:
    """(key, mode) from a key named in the title, English or Spanish, else None."""
    if m := _KEY_EN_RE.search(title):
        letter, accidental, quality = m.groups()
    elif m := _KEY_ES_RE.search(title):
        solfege, accidental, quality = m.groups()
        letter = _SOLFEGE[solfege.lower()]
    else:
        return None
    key = _PITCH[letter.upper()]
    if accidental:
        key += -1 if accidental.lower() in _FLAT_WORDS else 1
    mode = 1 if quality.lower() in ("major", "mayor") else 0
    return key % 12, mode


def preview_url(track_id: str, client: httpx.Client) -> str | None:
    """The 30s preview URL from the public embed page (absent for some tracks)."""
    try:
        resp = client.get(
            EMBED_URL.format(track_id=track_id),
            headers={"User-Agent": "Mozilla/5.0"},
            follow_redirects=True,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise PreviewAnalysisError(f"embed page fetch failed: {exc}") from exc
    if m := _NEXT_DATA_RE.search(resp.text):

        def find(obj: object) -> str | None:
            if isinstance(obj, dict):
                if isinstance(preview := obj.get("audioPreview"), dict):
                    return preview.get("url")
                for v in obj.values():
                    if (url := find(v)) is not None:
                        return url
            elif isinstance(obj, list):
                for v in obj:
                    if (url := find(v)) is not None:
                        return url
            return None

        if (url := find(json.loads(m.group(1)))) is not None:
            return url
    # Embed page structure changes over time; fall back to a raw text match.
    if m := _AUDIO_PREVIEW_RE.search(resp.text):
        # The capture is a JSON-escaped string (e.g. & for &); unescape it.
        try:
            url = json.loads(f'"{m.group(1)}"')
            return url if isinstance(url, str) else None
        except ValueError:
            return m.group(1)
    return None


def extract_features(audio: bytes, client: httpx.Client, *, retries: int = 2) -> dict:
    """Measured features (no key/mode) for an audio clip, via ReccoBeats analysis."""
    files = {"audioFile": ("preview.mp3", audio, "audio/mpeg")}
    try:
        resp = client.post(ANALYSIS_URL, files=files)
        while resp.status_code == 429 and retries > 0:
            time.sleep(float(resp.headers.get("Retry-After", "5")))
            resp = client.post(ANALYSIS_URL, files=files)
            retries -= 1
    except httpx.HTTPError as exc:
        raise PreviewAnalysisError(f"ReccoBeats analysis call failed: {exc}") from exc
    if resp.status_code != 200:
        raise PreviewAnalysisError(
            f"ReccoBeats analysis returned HTTP {resp.status_code}: {resp.text[:120]}"
        )
    try:
        return resp.json()
    except ValueError as exc:
        raise PreviewAnalysisError(f"ReccoBeats analysis returned invalid JSON: {exc}") from exc


def features_from_preview(
    track_id: str, raw_track: dict, *, client: httpx.Client | None = None, timeout: float = 30.0
) -> dict:
    """A complete Spotify-shaped audio-features dict from the track's 30s preview.

    Raises PreviewAnalysisError when the title names no key, the track has no
    public preview, or the analysis call fails.
    """
    if client is None:
        with httpx.Client(timeout=timeout) as owned:
            return features_from_preview(track_id, raw_track, client=owned)

    title = raw_track.get("name", "")
    key_mode = parse_key_mode(title)
    if key_mode is None:
        raise PreviewAnalysisError(f"no key/mode in title {title!r}")
    url = preview_url(track_id, client)
    if url is None:
        raise PreviewAnalysisError("no public 30s preview available")
    try:
        audio = client.get(url, follow_redirects=True).raise_for_status().content
    except httpx.HTTPError as exc:
        raise PreviewAnalysisError(f"preview download failed: {exc}") from exc
    features = extract_features(audio, client)
    features["key"], features["mode"] = key_mode
    completed = complete_features(features, raw_track)
    completed["source"] = SOURCE_TAG
    return completed
