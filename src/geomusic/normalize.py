"""Derivation of rendering parameters from raw track data."""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel

from . import RENDERER_VERSION
from .config import CONFIG_VERSION, RenderConfig
from .inputs import id_flags
from .models import TrackData
from .palettes import PITCH_NAMES


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def remap(value: float, domain: tuple[float, float], target: tuple[float, float]) -> float:
    """Linear remap with clamping to the source domain."""
    d0, d1 = domain
    t0, t1 = target
    if d1 == d0:
        return t0
    t = (clamp(value, min(d0, d1), max(d0, d1)) - d0) / (d1 - d0)
    return t0 + t * (t1 - t0)


class RenderParams(BaseModel):
    track_id: str
    composition: Literal["square", "rect"]
    flags: tuple[bool, bool, bool, bool]
    cell_count: int
    key: int
    pitch: str
    mode: int
    x_scale: float
    y_scale: float
    radius_frac: float
    displaced: bool
    renderer_version: str
    config_version: str
    features: dict


def derive(data: TrackData, config: RenderConfig) -> RenderParams:
    f = data.features
    flags = id_flags(data.track.id)
    return RenderParams(
        track_id=data.track.id,
        composition="square" if f.mode != 0 else "rect",
        flags=flags,
        cell_count=4 + 3 * sum(flags) if f.mode != 0 else len(config.rect_cell_heights),
        key=f.key,
        pitch=PITCH_NAMES[f.key],
        mode=f.mode,
        x_scale=remap(f.loudness, config.loudness_domain, config.x_scale_range),
        y_scale=remap(f.tempo, config.tempo_domain, config.y_scale_range),
        radius_frac=remap(f.speechiness, config.speechiness_domain, config.speech_radius_range),
        displaced=f.instrumentalness > 0,
        renderer_version=RENDERER_VERSION,
        config_version=CONFIG_VERSION,
        features=f.model_dump(),
    )


def cell_seed(track_id: str, cell_index: int, purpose: str = "") -> int:
    """Deterministic per-cell seed: SHA-256(track_id + renderer_version + cell)."""
    payload = f"{track_id}:{RENDERER_VERSION}:{cell_index}:{purpose}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")
