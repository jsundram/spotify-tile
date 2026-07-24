"""SVG serialization with stable element order and embedded metadata."""

from __future__ import annotations

import json
from xml.sax.saxutils import escape

from .config import RenderConfig
from .geometry import Scene, Shape
from .models import TrackData

LAYER_ORDER = ("background", "cell_bg", "motifs", "displaced", "dots")


def _fmt(v: float) -> str:
    if isinstance(v, float):
        s = f"{v:.2f}".rstrip("0").rstrip(".")
        return s if s else "0"
    return str(v)


def _shape_svg(shape: Shape, clip_ids: dict[tuple, str]) -> str:
    clip_attr = ""
    if shape.clip is not None:
        clip_attr = f' clip-path="url(#{clip_ids[shape.clip]})"'
    a = shape.attrs
    if shape.kind == "rect":
        return (
            f'<rect x="{_fmt(a["x"])}" y="{_fmt(a["y"])}" width="{_fmt(a["w"])}" '
            f'height="{_fmt(a["h"])}" fill="{shape.fill}"{clip_attr}/>'
        )
    if shape.kind == "ellipse":
        return (
            f'<ellipse cx="{_fmt(a["cx"])}" cy="{_fmt(a["cy"])}" rx="{_fmt(a["rx"])}" '
            f'ry="{_fmt(a["ry"])}" fill="{shape.fill}"{clip_attr}/>'
        )
    if shape.kind == "polygon":
        pts = " ".join(f"{_fmt(x)},{_fmt(y)}" for x, y in a["points"])
        return f'<polygon points="{pts}" fill="{shape.fill}"{clip_attr}/>'
    raise ValueError(f"Unknown shape kind {shape.kind!r}")


def _collect_clips(scene: Scene) -> dict[tuple, str]:
    clip_ids: dict[tuple, str] = {}
    for layer in LAYER_ORDER:
        for shape in scene.layers[layer]:
            if shape.clip is not None and shape.clip not in clip_ids:
                clip_ids[shape.clip] = f"clip{len(clip_ids)}"
    return clip_ids


def _caption(scene: Scene, config: RenderConfig) -> list[str]:
    p = scene.params
    bg = scene.bg_square
    out: list[str] = ['<g id="caption">']
    if config.caption_style == "annotated":
        strip_w = config.swatch_width * len(scene.palette.colors)
        x1 = bg.x + bg.w  # strip ends flush with the background square
        y0 = bg.y + bg.h + config.caption_offset
        label_x = x1 - strip_w - config.caption_gap
        out.append(
            f'<text x="{_fmt(label_x)}" y="{_fmt(y0 + config.swatch_height * 0.72)}" '
            f'text-anchor="end" font-family="{escape(config.caption_font_family)}" '
            f'font-size="{config.caption_font_size}" fill="{config.caption_color}">'
            f"key = {p.key}</text>"
        )
        for i, color in enumerate(scene.palette.colors):
            x = x1 - strip_w + i * config.swatch_width
            out.append(
                f'<rect x="{_fmt(x)}" y="{_fmt(y0)}" width="{config.swatch_width}" '
                f'height="{config.swatch_height}" fill="{color}"/>'
            )
    else:
        f = p.features
        lines = [
            (
                f"mode = {p.mode} ({'major' if p.mode else 'minor'}); key = {p.key} ({p.pitch}); "
                f"danceability = {f['danceability']}; speechiness = {f['speechiness']};"
            ),
            (
                f"energy = {f['energy']}; track_id = \"{p.track_id[:4]}\" "
                f"({', '.join(str(b) for b in p.flags)})"
            ),
        ]
        y = bg.y + bg.h + config.caption_offset + config.caption_font_size
        for line in lines:
            out.append(
                f'<text x="{_fmt(bg.x)}" y="{_fmt(y)}" '
                f'font-family="{escape(config.caption_font_family)}" '
                f'font-size="{config.caption_font_size}" fill="{config.caption_color}">'
                f"{escape(line)}</text>"
            )
            y += config.caption_font_size * 1.35
    out.append("</g>")
    return out


def _debug_overlay(scene: Scene, config: RenderConfig) -> list[str]:
    out = ['<g id="debug" fill="none" stroke="#ff00ff" stroke-width="2">']
    g = scene.grid
    out.append(
        f'<rect x="{_fmt(g.x)}" y="{_fmt(g.y)}" width="{_fmt(g.w)}" height="{_fmt(g.h)}"/>'
    )
    for cell in scene.cells:
        r = cell.rect
        out.append(
            f'<rect x="{_fmt(r.x)}" y="{_fmt(r.y)}" width="{_fmt(r.w)}" height="{_fmt(r.h)}"/>'
        )
        out.append(
            f'<text x="{_fmt(r.x + 8)}" y="{_fmt(r.y + 30)}" fill="#ff00ff" stroke="none" '
            f'font-size="26">{cell.index}{"B" if cell.big else ""}</text>'
        )
    p = scene.params
    out.append(
        f'<text x="20" y="40" fill="#ff00ff" stroke="none" font-size="30">'
        f"{escape(p.track_id)} x_scale={p.x_scale:.3f} y_scale={p.y_scale:.3f} "
        f"radius={p.radius_frac:.3f} displaced={p.displaced}</text>"
    )
    out.append("</g>")
    return out


def render_svg(
    scene: Scene,
    data: TrackData,
    config: RenderConfig,
    *,
    cache_fetched_at: str | None = None,
    debug_overlay: bool = False,
) -> str:
    w, h = scene.artboard
    p = scene.params
    metadata = {
        "generator": "geomusic",
        "renderer_version": p.renderer_version,
        "config_version": p.config_version,
        "track_id": p.track_id,
        "spotify_url": data.track.spotify_url,
        "track": data.track.model_dump(),
        "audio_features": data.features.model_dump(),
        "cache_fetched_at": cache_fetched_at,
        "parameters": p.model_dump(),
    }
    clip_ids = _collect_clips(scene)

    out = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}">'
        ),
        f"<metadata>{escape(json.dumps(metadata, sort_keys=True))}</metadata>",
        "<defs>",
    ]
    for clip, cid in clip_ids.items():
        x, y, cw, ch = clip
        out.append(
            f'<clipPath id="{cid}"><rect x="{_fmt(x)}" y="{_fmt(y)}" '
            f'width="{_fmt(cw)}" height="{_fmt(ch)}"/></clipPath>'
        )
    out.append("</defs>")
    for layer in LAYER_ORDER:
        out.append(f'<g id="{layer}">')
        out.extend(_shape_svg(s, clip_ids) for s in scene.layers[layer])
        out.append("</g>")
    out.extend(_caption(scene, config))
    if debug_overlay:
        out.extend(_debug_overlay(scene, config))
    out.append("</svg>")
    return "\n".join(out)
