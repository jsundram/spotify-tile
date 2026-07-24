"""Render a contact sheet of the extracted palettes for visual comparison
against the source Grasshopper screenshot and the reference poster strips."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
PALETTES = ROOT / "src" / "geomusic" / "data" / "palettes.json"
OUT = ROOT / "references" / "processed" / "palette-contact-sheet.png"

SWATCH, PAD, LABEL_W = 64, 8, 120


def main() -> None:
    data = json.loads(PALETTES.read_text())["palettes"]
    n_cols = max(len(p["colors"]) for p in data.values())
    width = LABEL_W + n_cols * (SWATCH + PAD) + PAD
    height = 12 * (SWATCH + PAD) + PAD
    img = Image.new("RGB", (width, height), "#ffffff")
    d = ImageDraw.Draw(img)
    for key in range(12):
        p = data[str(key)]
        y = PAD + key * (SWATCH + PAD)
        d.text((PAD, y + SWATCH // 3), f"key {key} ({p['pitch']})", fill="#333333")
        for i, color in enumerate(p["colors"]):
            x = LABEL_W + PAD + i * (SWATCH + PAD)
            d.rectangle([x, y, x + SWATCH, y + SWATCH], fill=color, outline="#888888")
            if color == p["background"]:
                d.rectangle([x, y, x + SWATCH, y + SWATCH], outline="#000000", width=3)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT)
    print(f"wrote {OUT} (background swatches outlined in black)")


if __name__ == "__main__":
    main()
