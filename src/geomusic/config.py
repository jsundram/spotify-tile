"""Centralized rendering configuration.

Every tuneable constant used to reconstruct the (Geo) Musical Configurations
system lives here.  Values marked CALIBRATED were measured from the reference
images under ``references/source`` (see ``scripts/measure_references.py`` and
``reconstruction_notes.md``); values marked PROVISIONAL are deterministic
choices for behavior the source material does not disclose.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path

CONFIG_VERSION = "2"


@dataclass(frozen=True)
class RenderConfig:
    # --- Artboard ------------------------------------------------------
    # CALIBRATED: every reference poster is 2400x2400: white border, colored
    # background square inset 212 px on each side (212/2400 = 0.08833).
    artboard_width: int = 2400
    artboard_height: int = 2400
    bg_margin_frac: float = 0.08833

    # --- Composition grid ----------------------------------------------
    # CALIBRATED from mode/1_GH-script.png ("mode = composition"): the grid
    # starts as the background square and is scaled about its center by
    # 0.535 (square comp) or (0.263, 0.8) (rectangular comp).  Measured grid
    # boxes confirm: 1976 * 0.535 = 1057 px; 1976 * (0.263, 0.8) = 520 x 1581.
    square_scale: float = 0.535
    rect_scale_x: float = 0.263
    rect_scale_y: float = 0.8

    # CALIBRATED from Judas / Bohemian Rhapsody: the rectangular composition
    # is a single vertical stack with relative cell heights 1, 1, 0.5, 0.5.
    rect_cell_heights: tuple[float, ...] = (1.0, 1.0, 0.5, 0.5)

    # --- Feature scaling -----------------------------------------------
    # 11.3/11.4 CALIBRATED from scaling/3_gh-script.png: loudness remaps from
    # domain [-60, 0] and tempo from [50, 250] to non-uniform x/y scale
    # factors applied to each cell's polygon.  The Grasshopper target domain
    # upper bound is 1.25 x radius ("if polygon is scaled beyond the
    # rectangle, there is Region Difference"); the lower bounds are 0.2.
    loudness_domain: tuple[float, float] = (-60.0, 0.0)
    x_scale_range: tuple[float, float] = (0.6, 1.15)
    tempo_domain: tuple[float, float] = (50.0, 250.0)
    y_scale_range: tuple[float, float] = (0.6, 1.2)

    # 11.5 CALIBRATED from instrumentalness/3_gh-script2.png ("speechiness =
    # radius of polygon"): speechiness remaps from domain [0, 0.1] to a
    # radius between 0.4 and 1.0 of the cell half-size.
    speechiness_domain: tuple[float, float] = (0.0, 0.1)
    speech_radius_range: tuple[float, float] = (0.62, 1.05)

    # 11.6 instrumentalness > 0 -> move polygons (vertically; the source
    # wiring moves along the Y unit vector) and add a circular "dot" element
    # with radius = cell / 8.  PROVISIONAL: displacement magnitude is half
    # the cell height (Lover, instrumentalness = 1.1e-5, shows motifs moved
    # all the way to the cell edge, so the magnitude is not proportional to
    # the feature value); which cells are displaced is a seeded choice.
    displacement_frac: float = 0.5
    displacement_probability: float = 0.45  # PROVISIONAL, per-cell seeded gate
    dot_radius_frac: float = 0.125  # CALIBRATED: circle R = cell length / 8
    dot_probability: float = 0.5  # PROVISIONAL, per-cell seeded gate

    # --- Motif reconstruction (PROVISIONAL seeded choices) --------------
    # The per-cell shape variety (square / diamond / circle, nesting, splits)
    # is not disclosed; weights approximate the observed frequency in the
    # eight reference posters.  See reconstruction_notes.md.
    shape_weights: tuple[float, float, float] = (0.30, 0.28, 0.42)  # square, diamond, circle
    nested_probability: float = 0.40
    split_probability: float = 0.30
    nested_scale: float = 0.5

    # --- Caption -------------------------------------------------------
    # CALIBRATED from the annotated posters: 8 swatches of ~69 x 44 px ending
    # flush with the background square's right edge, 58 px below it; gray
    # "key = N" label to the left.
    caption_style: str = "annotated"  # "annotated" (key + swatches) or "text"
    caption_font_family: str = "Roboto, 'Helvetica Neue', Arial, sans-serif"
    caption_font_size: int = 34
    caption_color: str = "#8a8a8a"
    swatch_width: int = 69
    swatch_height: int = 44
    caption_gap: int = 30  # gap between the label text and the swatch strip
    caption_offset: int = 58  # vertical gap between bg square and caption row


DEFAULT_CONFIG = RenderConfig()


def load_config(path: str | Path | None = None) -> RenderConfig:
    """Load a RenderConfig, optionally overridden by a JSON file."""
    if path is None:
        return DEFAULT_CONFIG
    data = json.loads(Path(path).read_text())
    known = {f.name for f in fields(RenderConfig)}
    unknown = set(data) - known
    if unknown:
        raise ValueError(f"Unknown config keys: {sorted(unknown)}")
    for f in fields(RenderConfig):
        if f.name in data and isinstance(data[f.name], list):
            data[f.name] = tuple(data[f.name])
    return replace(DEFAULT_CONFIG, **data)


def config_dict(config: RenderConfig) -> dict:
    return asdict(config)
