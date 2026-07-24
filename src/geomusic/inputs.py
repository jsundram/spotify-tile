"""Parsing of Spotify track inputs and track-id derived booleans."""

from __future__ import annotations

import re
from urllib.parse import urlparse

TRACK_ID_RE = re.compile(r"^[0-9A-Za-z]{22}$")

_URI_RE = re.compile(r"^spotify:(?P<kind>[a-z]+):(?P<id>[0-9A-Za-z]+)$")


class InputError(ValueError):
    """A track input that cannot be parsed into a track id."""


def parse_track_input(value: str) -> str:
    """Parse a Spotify track URL, URI, or raw id into a 22-char track id."""
    value = value.strip()
    if not value:
        raise InputError("Empty input; expected a Spotify track URL, URI, or track id.")

    if TRACK_ID_RE.match(value):
        return value

    m = _URI_RE.match(value)
    if m:
        if m.group("kind") != "track":
            raise InputError(
                f"Spotify URI is a {m.group('kind')}, not a track. "
                "Only single tracks are supported."
            )
        return _check_id(m.group("id"))

    if value.startswith(("http://", "https://")):
        parsed = urlparse(value)
        if parsed.hostname not in {"open.spotify.com", "play.spotify.com"}:
            raise InputError(f"Unrecognized Spotify host: {parsed.hostname!r}")
        parts = [p for p in parsed.path.split("/") if p]
        # Allow locale prefixes such as /intl-de/track/<id>
        if parts and parts[0].startswith("intl-"):
            parts = parts[1:]
        if len(parts) >= 2 and parts[0] == "track":
            return _check_id(parts[1])
        if parts and parts[0] in {"album", "playlist", "artist", "show", "episode"}:
            raise InputError(
                f"This is a Spotify {parts[0]} URL. Only single tracks are supported."
            )
        raise InputError(f"Could not find a track id in URL path {parsed.path!r}")

    raise InputError(
        f"Unrecognized input {value!r}. Expected a track URL "
        "(https://open.spotify.com/track/...), a spotify:track:... URI, "
        "or a 22-character track id."
    )


def _check_id(track_id: str) -> str:
    if not TRACK_ID_RE.match(track_id):
        raise InputError(
            f"Malformed track id {track_id!r}: expected 22 base-62 characters."
        )
    return track_id


def id_flags(track_id: str) -> tuple[bool, bool, bool, bool]:
    """First four characters of the track id, classified digit / non-digit.

    Published rule (portfolio page): each of the first four characters of the
    track id is evaluated with ``isdigit`` and the resulting booleans drive
    quadrilateral subdivision.
    """
    if len(track_id) < 4:
        raise InputError(f"Track id {track_id!r} is too short for flag derivation.")
    return (
        track_id[0].isdigit(),
        track_id[1].isdigit(),
        track_id[2].isdigit(),
        track_id[3].isdigit(),
    )
