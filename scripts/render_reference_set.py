"""Render every reference track from its local fixture (no network)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from geomusic.config import load_config
from geomusic.geometry import build_scene
from geomusic.models import TrackData
from geomusic.normalize import derive
from geomusic.render_png import svg_to_png
from geomusic.render_svg import render_svg

MANIFEST = ROOT / "references" / "reference-manifest.json"
FIXTURES = ROOT / "tests" / "fixtures" / "spotify"
OUT = ROOT / "references" / "processed" / "renders"


def main() -> None:
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    config = load_config(config_path)
    OUT.mkdir(parents=True, exist_ok=True)
    entries = json.loads(MANIFEST.read_text())["entries"]
    for entry in entries:
        slug = entry["slug"]
        fixture = FIXTURES / f"{slug}.json"
        if not fixture.exists():
            print(f"{slug:28s} SKIP (no fixture; run fetch_reference_tracks.py)")
            continue
        doc = json.loads(fixture.read_text())
        data = TrackData.from_cache_doc(doc)
        params = derive(data, config)
        scene = build_scene(data, params, config)
        svg = render_svg(scene, data, config, cache_fetched_at=doc.get("fetched_at"))
        (OUT / f"{slug}.svg").write_text(svg)
        svg_to_png(svg, OUT / f"{slug}.png")
        print(f"{slug:28s} {params.composition:6s} cells={params.cell_count:2d} "
              f"key={params.key:2d} -> {OUT / (slug + '.png')}")


if __name__ == "__main__":
    main()
