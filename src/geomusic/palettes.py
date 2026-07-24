"""Key palettes extracted from the source Grasshopper screenshot.

The palette constants live in ``data/palettes.json``, produced by
``scripts/extract_palettes.py`` from the pinned source image.  They are
source-derived artistic constants — never retune them per song.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources

from pydantic import BaseModel

PITCH_NAMES = ["C", "C#/Db", "D", "D#/Eb", "E", "F", "F#/Gb", "G", "G#/Ab", "A", "Bb", "B"]


class Palette(BaseModel):
    key: int
    pitch: str
    background: str
    background_source: str
    colors: list[str]

    @property
    def foregrounds(self) -> list[str]:
        """Palette colors excluding the designated background."""
        remaining = [c for c in self.colors if c != self.background]
        return remaining or list(self.colors)


@lru_cache(maxsize=1)
def _load() -> dict:
    with resources.files("geomusic.data").joinpath("palettes.json").open() as fh:
        return json.load(fh)


def load_palettes() -> dict[int, Palette]:
    raw = _load()
    return {
        int(k): Palette(key=int(k), **v) for k, v in raw["palettes"].items()
    }


def palette_source_sha256() -> str:
    return _load()["source_sha256"]


def get_palette(key: int) -> Palette:
    palettes = load_palettes()
    if key not in palettes:
        raise KeyError(f"No palette for key {key}; expected 0..11.")
    return palettes[key]
