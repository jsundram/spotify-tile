"""Extract the twelve key palettes from the source Grasshopper screenshot.

The screenshot ``references/source/key/4_key_script.png`` shows twelve purple
group panels (3 rows x 4 columns), one per Spotify key 0..11, each containing
a vertical column of Colour Swatch nodes.  This script:

1. verifies the SHA-256 of the source screenshot;
2. finds every swatch chip as a uniform-fill connected component;
3. clusters chips into the twelve panels and orders them top-to-bottom;
4. writes  references/palette-crops.json   (panel crop rectangles + chip boxes)
   and     src/geomusic/data/palettes.json (the palette constants).

Backgrounds: for keys with a measured reference poster the background color is
the palette entry closest to the measured poster background; for the remaining
keys the first (topmost) swatch is used, marked provisional.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "references" / "source" / "key" / "4_key_script.png"
CROPS_OUT = ROOT / "references" / "palette-crops.json"
PALETTES_OUT = ROOT / "src" / "geomusic" / "data" / "palettes.json"
MEASUREMENTS = ROOT / "references" / "processed" / "measurements.json"

PITCHES = ["C", "C#/Db", "D", "D#/Eb", "E", "F", "F#/Gb", "G", "G#/Ab", "A", "Bb", "B"]

# Reference posters with known keys, used to pick each palette's background.
KEY_EVIDENCE = {
    0: "bohemian-rhapsody",  # key 0, mode 0
    1: "holocene",  # key 1
    2: "lover",  # key 2
    5: "the-adults-are-talking",  # key 5
    7: "real-love-baby",  # key 7
    10: "vienna",  # key 10 (same strip as judas)
}

MIN_AREA, MAX_AREA = 120, 2600
MAX_STD = 13.0  # per-channel std dev inside the blob (uniform fill)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_page(c) -> bool:  # white page background
    return c[0] >= 245 and c[1] >= 245 and c[2] >= 245


def is_panel(c) -> bool:  # lavender group panel (two shades appear)
    r, g, b = c
    return b > r > g and b >= 200 and r >= 160 and b - g >= 20


def is_node_gray(c) -> bool:
    """Grasshopper component chrome: cool gray #9797a6..#9b9baa family."""
    r, g, b = c
    return abs(r - g) <= 4 and 10 <= b - r <= 20 and 120 <= r <= 180


def find_panels(img: Image.Image) -> list[list[int]]:
    """Bounding boxes of the twelve lavender group panels."""
    w, h = img.size
    px = img.load()
    seen = [[False] * w for _ in range(h)]
    boxes = []
    for y0 in range(0, h, 2):
        for x0 in range(0, w, 2):
            if seen[y0][x0] or not is_panel(px[x0, y0]):
                continue
            stack = [(x0, y0)]
            seen[y0][x0] = True
            xs_min = xs_max = x0
            ys_min = ys_max = y0
            count = 0
            while stack:
                x, y = stack.pop()
                count += 1
                xs_min, xs_max = min(xs_min, x), max(xs_max, x)
                ys_min, ys_max = min(ys_min, y), max(ys_max, y)
                for nx, ny in ((x + 2, y), (x - 2, y), (x, y + 2), (x, y - 2)):
                    if 0 <= nx < w and 0 <= ny < h and not seen[ny][nx] and is_panel(px[nx, ny]):
                        seen[ny][nx] = True
                        stack.append((nx, ny))
            if count * 4 >= 15000:  # panels are large; ignore stray tints
                boxes.append([xs_min, ys_min, xs_max, ys_max])
    # Merge boxes that overlap or nearly touch (nested/split panel shades).
    merged = True
    while merged:
        merged = False
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i], boxes[j]
                if a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]:
                    boxes[i] = [
                        min(a[0], b[0]),
                        min(a[1], b[1]),
                        max(a[2], b[2]),
                        max(a[3], b[3]),
                    ]
                    del boxes[j]
                    merged = True
                    break
            if merged:
                break
    return boxes


def chips_in_panel(img: Image.Image, box: list[int]) -> list[dict]:
    """Find swatch chips in one panel via per-row uniform color runs.

    Chips live in the left part of each panel as small rounded rects whose
    color segment produces ~15 consecutive rows of uniform horizontal runs
    with a stable x extent.  Wires, text, and chrome never stack that way.
    """
    raw = img.load()
    x0, y0, x1, y1 = box
    x_hi = min(x0 + 130, x1)

    # Horizontal 5-px median filter: wires crossing a chip are thin, so the
    # median restores the chip's flat fill underneath them.
    sm: list[list[tuple[int, int, int]]] = []
    for y in range(y0, y1 + 1):
        row = []
        for x in range(x0, x_hi):
            window = [raw[min(max(x + d, x0), x_hi - 1), y] for d in (-2, -1, 0, 1, 2)]
            row.append(tuple(sorted(c[i] for c in window)[2] for i in range(3)))
        sm.append(row)

    def px(x, y):
        return sm[y - y0][x - x0]

    rows: list[tuple[int, int, int, tuple[int, int, int]]] = []  # y, xs, xe, color
    for y in range(y0, y1 + 1):
        x = x0 + 3
        while x < x_hi:
            c0 = px(x, y)
            xe = x
            while xe + 1 < x_hi and all(abs(px(xe + 1, y)[i] - c0[i]) <= 12 for i in range(3)):
                xe += 1
            if xe - x + 1 >= 12:
                # White page never appears inside a panel, so pure white here
                # is a genuine swatch chip; exclude only panel bg and chrome.
                mid = px((x + xe) // 2, y)
                if not (is_panel(mid) or is_node_gray(mid)):
                    rows.append((y, x, xe, mid))
            x = xe + 1

    # Stack rows with overlapping x extents on consecutive y into chips.
    chips: list[dict] = []
    groups: list[dict] = []
    for y, xs, xe, color in rows:
        placed = False
        for g in groups:
            if (
                y - g["last_y"] <= 2
                and min(xe, g["xe"]) - max(xs, g["xs"]) + 1 >= 9
                and all(abs(color[i] - g["rows"][-1][3][i]) <= 14 for i in range(3))
            ):
                g["rows"].append((y, xs, xe, color))
                g["last_y"] = y
                g["xs"], g["xe"] = min(xs, g["xs"]), max(xe, g["xe"])
                placed = True
                break
        if not placed:
            groups.append({"rows": [(y, xs, xe, color)], "last_y": y, "xs": xs, "xe": xe})
    # Post-merge: rejoin fragments of one chip split by a wide occluding wire
    # (same x extent, same color, small vertical gap).
    merged = True
    while merged:
        merged = False
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                a, b = groups[i], groups[j]
                ca, cb = a["rows"][-1][3], b["rows"][0][3]
                if (
                    0 < b["rows"][0][0] - a["rows"][-1][0] <= 4
                    and min(a["xe"], b["xe"]) - max(a["xs"], b["xs"]) + 1 >= 12
                    and all(abs(ca[k] - cb[k]) <= 10 for k in range(3))
                ):
                    a["rows"].extend(b["rows"])
                    a["xs"], a["xe"] = min(a["xs"], b["xs"]), max(a["xe"], b["xe"])
                    a["last_y"] = b["last_y"]
                    del groups[j]
                    merged = True
                    break
            if merged:
                break

    for g in groups:
        if len(g["rows"]) < 5:
            continue
        # Chips sit in a left-aligned column of bounded width; reject drifting
        # wire-bundle artifacts that stack elsewhere in the panel.
        if g["xs"] > x0 + 80 or (g["xe"] - g["xs"] + 1) > 70:
            continue
        colors = [r[3] for r in g["rows"]]
        med = tuple(sorted(ch[i] for ch in colors)[len(colors) // 2] for i in range(3))
        ys = [r[0] for r in g["rows"]]
        chips.append(
            {
                "bbox": [g["xs"], min(ys), g["xe"], max(ys)],
                "color": "#%02x%02x%02x" % med,
                "area": sum(r[2] - r[1] + 1 for r in g["rows"]),
            }
        )
    chips.sort(key=lambda c: c["bbox"][1])
    return chips



def order_panels(panels: list[list[int]]) -> dict[int, list[int]]:
    """Order the twelve panels row-major (3 rows x 4 cols) -> key 0..11."""
    if len(panels) != 12:
        raise SystemExit(f"expected 12 group panels, found {len(panels)}: {panels}")
    panels = sorted(panels, key=lambda b: (b[1] + b[3]) / 2)
    ordered: list[list[int]] = []
    for row in (panels[0:4], panels[4:8], panels[8:12]):
        ordered.extend(sorted(row, key=lambda b: (b[0] + b[2]) / 2))
    return {i: box for i, box in enumerate(ordered)}


def hex_to_rgb(s: str) -> tuple[int, int, int]:
    return tuple(int(s[i : i + 2], 16) for i in (1, 3, 5))


def dist(a, b) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def main() -> None:
    digest = sha256(SOURCE)
    img = Image.open(SOURCE).convert("RGB")
    panel_boxes = order_panels(find_panels(img))
    groups = {key: chips_in_panel(img, box) for key, box in panel_boxes.items()}

    measured = json.loads(MEASUREMENTS.read_text()) if MEASUREMENTS.exists() else {}

    crops = {"source": SOURCE.name, "source_sha256": digest, "panels": {}}
    palettes = {"source": SOURCE.name, "source_sha256": digest, "palettes": {}}

    for key in sorted(groups):
        chip_list = groups[key]
        x0, y0, x1, y1 = panel_boxes[key]
        crops["panels"][str(key)] = {
            "x": x0,
            "y": y0,
            "width": x1 - x0 + 1,
            "height": y1 - y0 + 1,
            "chips": [c["bbox"] for c in chip_list],
        }
        colors = [c["color"] for c in chip_list]

        background = colors[0]
        bg_source = "provisional-first-swatch"
        ev = KEY_EVIDENCE.get(key)
        if ev and ev in measured:
            target = hex_to_rgb(measured[ev]["bg_color"])
            background = min(colors, key=lambda c: dist(hex_to_rgb(c), target))
            bg_source = f"matched-to-{ev}"

        palettes["palettes"][str(key)] = {
            "pitch": PITCHES[key],
            "background": background,
            "background_source": bg_source,
            "colors": colors,
        }
        print(f"key {key:2d} ({PITCHES[key]:5s}) bg={background} [{bg_source}] {colors}")

    CROPS_OUT.write_text(json.dumps(crops, indent=2))
    PALETTES_OUT.parent.mkdir(parents=True, exist_ok=True)
    PALETTES_OUT.write_text(json.dumps(palettes, indent=2))
    print(f"wrote {CROPS_OUT}")
    print(f"wrote {PALETTES_OUT}")


if __name__ == "__main__":
    main()
