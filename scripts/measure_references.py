"""Measure layout geometry from the reference posters.

Writes references/processed/measurements.json with, per image:
  - the background-square color and bounding box;
  - the composition-grid bounding box;
  - caption swatch strip geometry and colors (annotated posters only).

These measurements calibrate the constants in src/geomusic/config.py.
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "references" / "source"
OUT = ROOT / "references" / "processed" / "measurements.json"

IMAGES = {
    "lover": SRC / "final" / "Lover-You-Should-ve-Come-Over_annotated.jpg",
    "real-love-baby": SRC / "final" / "Real-Love-Baby_annotated.jpg",
    "judas": SRC / "final" / "Judas_annotated.jpg",
    "vienna": SRC / "final" / "Vienna_annotated.jpg",
    "holocene": SRC / "mode" / "Holocene.jpg",
    "bohemian-rhapsody": SRC / "mode" / "Bohemian-Rhapsody.jpg",
    "the-adults-are-talking": SRC / "track-id" / "The-Adults-are-Talking.jpg",
    "sunset": SRC / "track-id" / "Sunset-The-xx.jpg",
}

WHITE_T = 242  # channels above this = white artboard
TOL = 26  # color distance tolerance for "same as background"


def close(c1, c2, tol=TOL):
    return all(abs(a - b) <= tol for a, b in zip(c1, c2))


def is_white(c):
    return all(ch >= WHITE_T for ch in c)


def measure(path: Path) -> dict:
    img = Image.open(path).convert("RGB")
    w, h = img.size
    px = img.load()

    bg_color = px[w // 2, int(h * 0.14)]

    # Background square bbox from edge scanlines: the square is contiguous and
    # its edge bands (x=off / y=off inside the square) contain no grid pixels.
    off = 220
    ys = [y for y in range(h) if close(px[off, y], bg_color)]
    xs = [x for x in range(w) if close(px[x, off], bg_color)]
    bg_bbox = [min(xs), min(ys), max(xs), max(ys)]

    # Grid bbox via density histograms so overflowing (displaced) motifs and
    # JPEG noise do not skew the frame bounds.
    x0, y0, x1, y1 = bg_bbox
    inset = 8
    col_counts = [0] * w
    row_counts = [0] * h
    for y in range(y0 + inset, y1 - inset):
        for x in range(x0 + inset, x1 - inset):
            c = px[x, y]
            if not close(c, bg_color) and not is_white(c):
                col_counts[x] += 1
                row_counts[y] += 1
    grid_bbox = None
    if max(col_counts) > 0:
        ct = 0.35 * max(col_counts)
        rt = 0.35 * max(row_counts)
        gxs = [x for x, n in enumerate(col_counts) if n >= ct]
        gys = [y for y, n in enumerate(row_counts) if n >= rt]
        grid_bbox = [min(gxs), min(gys), max(gxs), max(gys)]

    # Caption strip: non-white content below the bg square.
    strip = None
    band_ys = range(bg_bbox[3] + 8, h - 4)
    sx, sy = [], []
    for y in band_ys:
        for x in range(0, w, 2):
            c = px[x, y]
            if not is_white(c):
                sx.append(x)
                sy.append(y)
    if sx:
        s_bbox = [min(sx), min(sy), max(sx), max(sy)]
        mid_y = (s_bbox[1] + s_bbox[3]) // 2
        # Collapse the midline into color runs to enumerate swatches.
        runs = []
        cur = None
        for x in range(s_bbox[0], s_bbox[2] + 1):
            c = px[x, mid_y]
            if is_white(c):
                cur = None
                continue
            if cur is not None and close(c, cur[2], 14):
                cur[1] = x
            else:
                cur = [x, x, c]
                runs.append(cur)
        swatches = [
            {"x0": r[0], "x1": r[1], "color": "#%02x%02x%02x" % tuple(r[2])}
            for r in runs
            if r[1] - r[0] >= 8  # drop text glyph fragments
        ]
        strip = {"bbox": s_bbox, "swatches": swatches}

    return {
        "file": str(path.relative_to(ROOT)),
        "size": [w, h],
        "bg_color": "#%02x%02x%02x" % bg_color,
        "bg_bbox": bg_bbox,
        "grid_bbox": grid_bbox,
        "grid_size": [grid_bbox[2] - grid_bbox[0] + 1, grid_bbox[3] - grid_bbox[1] + 1]
        if grid_bbox
        else None,
        "caption": strip,
    }


def main() -> None:
    out = {}
    for name, path in IMAGES.items():
        out[name] = measure(path)
        g = out[name]["grid_size"]
        print(f"{name:24s} bg={out[name]['bg_color']} bg_bbox={out[name]['bg_bbox']} grid={g}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
