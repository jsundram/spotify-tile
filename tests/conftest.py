import json
from pathlib import Path

import pytest

from geomusic.models import TrackData

FIXTURES = Path(__file__).parent / "fixtures" / "spotify"


def fixture_doc(slug: str) -> dict:
    return json.loads((FIXTURES / f"{slug}.json").read_text())


@pytest.fixture
def lover_doc() -> dict:
    return fixture_doc("lover-you-shouldve-come-over")


@pytest.fixture
def lover(lover_doc) -> TrackData:
    return TrackData.from_cache_doc(lover_doc)


@pytest.fixture
def judas() -> TrackData:
    return TrackData.from_cache_doc(fixture_doc("judas"))
