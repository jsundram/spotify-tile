"""Raster export via CairoSVG (no browser dependency)."""

from __future__ import annotations

from pathlib import Path

import cairosvg


def svg_to_png(svg_text: str, out_path: str | Path, *, width: int | None = None) -> Path:
    out_path = Path(out_path)
    cairosvg.svg2png(
        bytestring=svg_text.encode("utf-8"),
        write_to=str(out_path),
        output_width=width,
    )
    return out_path
