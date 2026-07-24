"""Visual-regression checks against the downloaded reference posters.

Stage A (topology: composition format, cell counts, grid placement) is
asserted strictly.  Full-image similarity is asserted against a coarse floor
so regressions surface without requiring the undisclosed per-cell motif
choices to match; scripts/compare_reference_set.py provides the detailed
ranked report used for tuning.
"""

import json
from pathlib import Path

import pytest

from geomusic.compare import compare_images
from geomusic.config import DEFAULT_CONFIG
from geomusic.geometry import build_scene
from geomusic.models import TrackData
from geomusic.normalize import derive
from geomusic.render_png import svg_to_png
from geomusic.render_svg import render_svg

ROOT = Path(__file__).parent.parent
MANIFEST = ROOT / "references" / "reference-manifest.json"
FIXTURES = Path(__file__).parent / "fixtures" / "spotify"

ENTRIES = json.loads(MANIFEST.read_text())["entries"] if MANIFEST.exists() else []

EXPECTED_TOPOLOGY = {
    "lover-you-shouldve-come-over": ("square", 10),
    "real-love-baby": ("square", 13),
    "judas": ("rect", 4),
    "vienna": ("square", 13),
    "holocene": ("square", 10),
    "bohemian-rhapsody": ("rect", 4),
    "sunset": ("square", 13),
    "the-adults-are-talking": ("square", 7),
}

SIMILARITY_FLOOR = 0.70


def _entry_ids():
    return [e["slug"] for e in ENTRIES]


@pytest.mark.parametrize("slug", _entry_ids())
def test_topology(slug):
    fixture = FIXTURES / f"{slug}.json"
    if not fixture.exists():
        pytest.skip("fixture missing; run scripts/fetch_reference_tracks.py")
    data = TrackData.from_cache_doc(json.loads(fixture.read_text()))
    params = derive(data, DEFAULT_CONFIG)
    composition, cells = EXPECTED_TOPOLOGY[slug]
    assert params.composition == composition
    assert params.cell_count == cells


@pytest.mark.parametrize("slug", _entry_ids())
def test_similarity_floor(slug, tmp_path):
    entry = next(e for e in ENTRIES if e["slug"] == slug)
    fixture = FIXTURES / f"{slug}.json"
    reference = ROOT / entry["reference"]
    if not fixture.exists() or not reference.exists():
        pytest.skip("fixture or reference image missing")
    data = TrackData.from_cache_doc(json.loads(fixture.read_text()))
    params = derive(data, DEFAULT_CONFIG)
    scene = build_scene(data, params, DEFAULT_CONFIG)
    svg = render_svg(scene, data, DEFAULT_CONFIG)
    png = tmp_path / f"{slug}.png"
    svg_to_png(svg, png)
    metrics = compare_images(png, reference)
    assert metrics["similarity"] >= SIMILARITY_FLOOR, metrics
