import hashlib
import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from geomusic.config import DEFAULT_CONFIG
from geomusic.geometry import build_scene
from geomusic.normalize import derive
from geomusic.palettes import get_palette, palette_source_sha256
from geomusic.render_svg import render_svg

SVG_NS = "{http://www.w3.org/2000/svg}"
ROOT = Path(__file__).parent.parent


def render(data):
    params = derive(data, DEFAULT_CONFIG)
    scene = build_scene(data, params, DEFAULT_CONFIG)
    return render_svg(scene, data, DEFAULT_CONFIG), scene


def test_canvas_dimensions(lover):
    svg, _ = render(lover)
    root = ET.fromstring(svg)
    assert root.get("width") == "2400"
    assert root.get("height") == "2400"


def test_cell_count_and_layer_order(lover):
    svg, _scene = render(lover)
    root = ET.fromstring(svg)
    groups = [g.get("id") for g in root.findall(f"{SVG_NS}g")]
    assert groups[:5] == ["background", "cell_bg", "motifs", "displaced", "dots"]
    assert groups[-1] == "caption"
    cell_rects = root.findall(f"{SVG_NS}g[@id='cell_bg']/{SVG_NS}rect")
    assert len(cell_rects) == 10  # 6Jv7 -> TFFT -> 10 cells


def test_palette_membership(lover):
    svg, _scene = render(lover)
    palette = set(get_palette(2).colors) | {"#ffffff", DEFAULT_CONFIG.caption_color}
    fills = set(re.findall(r'fill="(#[0-9a-f]{6})"', svg))
    assert fills <= palette


def test_no_invalid_coordinates(lover):
    svg, _ = render(lover)
    for num in re.findall(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', svg):
        value = float(num)
        assert math.isfinite(value)
    assert "nan" not in svg.lower().replace("annotated", "")
    assert "inf" not in svg.lower()


def test_shapes_within_bleed(lover):
    _, scene = render(lover)
    w, h = scene.artboard
    for layer in scene.layers.values():
        for shape in layer:
            a = shape.attrs
            if shape.kind == "rect":
                xs = [a["x"], a["x"] + a["w"]]
                ys = [a["y"], a["y"] + a["h"]]
            elif shape.kind == "ellipse":
                xs = [a["cx"] - a["rx"], a["cx"] + a["rx"]]
                ys = [a["cy"] - a["ry"], a["cy"] + a["ry"]]
            else:
                xs = [p[0] for p in a["points"]]
                ys = [p[1] for p in a["points"]]
            # Clipped shapes may exceed their clip box but never the artboard.
            assert min(xs) >= -w and max(xs) <= 2 * w
            assert min(ys) >= -h and max(ys) <= 2 * h
            if shape.clip is None:
                assert min(xs) >= 0 and max(xs) <= w
                assert min(ys) >= 0 and max(ys) <= h


def test_metadata_contains_track_and_no_secrets(lover):
    svg, _ = render(lover)
    meta = ET.fromstring(svg).find(f"{SVG_NS}metadata")
    payload = json.loads(meta.text)
    assert payload["track_id"] == "6Jv7kjGkhY2fT4yuBF3aTz"
    assert payload["audio_features"]["key"] == 2
    assert "client" not in json.dumps(payload).lower()
    assert "secret" not in svg.lower()
    assert "SPOTIFY_" not in svg


def test_caption_contains_key(lover):
    svg, _ = render(lover)
    assert ">key = 2</text>" in svg


def test_deterministic_output(lover):
    svg1, _ = render(lover)
    svg2, _ = render(lover)
    assert svg1 == svg2


def test_rect_composition(judas):
    _svg, scene = render(judas)
    assert len(scene.cells) == 4
    heights = [c.rect.h for c in scene.cells]
    assert heights[0] == pytest.approx(heights[1])
    assert heights[0] == pytest.approx(2 * heights[2])
    assert heights[0] == pytest.approx(2 * heights[3])


def test_palette_source_hash_pinned():
    source = ROOT / "references" / "source" / "key" / "4_key_script.png"
    if not source.exists():
        pytest.skip("source screenshot not downloaded")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    assert digest == palette_source_sha256(), (
        "palette source image changed; re-verify extraction before accepting"
    )


def test_crop_manifest_covers_all_keys():
    crops = json.loads((ROOT / "references" / "palette-crops.json").read_text())
    assert sorted(int(k) for k in crops["panels"]) == list(range(12))
    for panel in crops["panels"].values():
        assert len(panel["chips"]) == 8
