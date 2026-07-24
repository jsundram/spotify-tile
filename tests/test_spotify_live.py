"""Opt-in live API tests: uv run pytest -m spotify_live"""

import os

import pytest
from dotenv import load_dotenv

from geomusic.spotify import SpotifyClient

load_dotenv()

pytestmark = [
    pytest.mark.spotify_live,
    pytest.mark.skipif(
        not (os.environ.get("SPOTIFY_CLIENT_ID") and os.environ.get("SPOTIFY_CLIENT_SECRET")),
        reason="no Spotify credentials in environment",
    ),
]


def test_live_track_and_features():
    with SpotifyClient() as client:
        track = client.get_track("6Jv7kjGkhY2fT4yuBF3aTz")
        assert "Lover" in track["name"]
        features = client.get_audio_features("6Jv7kjGkhY2fT4yuBF3aTz")
        assert features["key"] == 2
        assert features["mode"] == 1
