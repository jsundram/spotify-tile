"""Scene construction: cells, motifs, displacement, caption.

Published rules are applied literally (see spec 11.x); undisclosed choices
(motif variety, colors per cell, which cells displace) are seeded
deterministically from SHA-256(track_id + renderer_version + cell_index) so
identical inputs always produce identical scenes.

The motif vocabulary reconstructs the forms observed across the eight
reference posters: diamonds, squares, frames, nested squares, circles
(solid / split / ringed / dotted), semicircle pairs, hourglasses, bars,
H-motifs, and corner triangles.  See reconstruction_notes.md.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .config import RenderConfig
from .models import TrackData
from .normalize import RenderParams, cell_seed
from .palettes import Palette, get_palette
from .subdivision import Cell, Rect, rect_strip, subdivide_square


@dataclass
class Shape:
    kind: str  # rect | ellipse | polygon
    fill: str
    attrs: dict = field(default_factory=dict)
    clip: tuple[float, float, float, float] | None = None


@dataclass
class Scene:
    artboard: tuple[int, int]
    bg_square: Rect
    grid: Rect
    cells: list[Cell]
    layers: dict[str, list[Shape]]  # background, cell_bg, motifs, displaced, dots
    palette: Palette
    params: RenderParams


# Motif weights reconstructed from frequency in the reference posters.
MOTIFS = ("diamond", "square", "circle", "hourglass", "semis", "bar", "hmotif", "triangle")
MOTIF_WEIGHTS = (0.22, 0.18, 0.30, 0.08, 0.08, 0.05, 0.05, 0.04)
BIG_MOTIFS = ("diamond", "circle", "hourglass", "semis")
BIG_MOTIF_WEIGHTS = (0.25, 0.35, 0.25, 0.15)


def _grid_rect(params: RenderParams, config: RenderConfig) -> tuple[Rect, Rect]:
    w, h = config.artboard_width, config.artboard_height
    margin = round(w * config.bg_margin_frac)
    bg = Rect(margin, margin, w - 2 * margin, h - 2 * margin)
    if params.composition == "square":
        sx = sy = config.square_scale
    else:
        sx, sy = config.rect_scale_x, config.rect_scale_y
    gw, gh = bg.w * sx, bg.h * sy
    return bg, Rect(bg.cx - gw / 2, bg.cy - gh / 2, gw, gh)


def _cells(params: RenderParams, grid: Rect, config: RenderConfig) -> list[Cell]:
    if params.composition == "square":
        return subdivide_square(grid, params.flags)
    return rect_strip(grid, config.rect_cell_heights)


def _ellipse(cx, cy, rx, ry, fill, clip=None) -> Shape:
    return Shape("ellipse", fill, {"cx": cx, "cy": cy, "rx": rx, "ry": ry}, clip)


def _rect(x, y, w, h, fill, clip=None) -> Shape:
    return Shape("rect", fill, {"x": x, "y": y, "w": w, "h": h}, clip)


def _poly(points, fill, clip=None) -> Shape:
    return Shape("polygon", fill, {"points": points}, clip)


def _diamond_points(cx, cy, rx, ry):
    return [(cx, cy - ry), (cx + rx, cy), (cx, cy + ry), (cx - rx, cy)]


class _CellPainter:
    """Builds the shapes for one cell with a dedicated deterministic RNG."""

    def __init__(
        self,
        cell: Cell,
        rng: random.Random,
        palette: Palette,
        params: RenderParams,
        config: RenderConfig,
        grid: Rect,
    ) -> None:
        self.cell = cell
        self.rng = rng
        self.palette = palette
        self.params = params
        self.config = config
        self.grid = grid
        self.r = cell.rect
        self.bg = rng.choice(palette.colors)
        self.motifs: list[Shape] = []
        self.displaced: list[Shape] = []
        self.dots: list[Shape] = []

    # -- helpers --------------------------------------------------------
    def pick(self, *exclude: str) -> str:
        options = [c for c in self.palette.colors if c not in exclude]
        return self.rng.choice(options or self.palette.colors)

    @property
    def cell_clip(self) -> tuple:
        r = self.r
        return (r.x, r.y, r.w, r.h)

    @property
    def grid_clip(self) -> tuple:
        g = self.grid
        return (g.x, g.y, g.w, g.h)

    def radii(self) -> tuple[float, float]:
        """11.3-11.5: speechiness radius scaled non-uniformly by loudness/tempo.

        Sized per axis so motifs fill non-square cells the way the reference
        strips do; a seeded per-cell jitter reproduces the observed size
        variety (0.55-0.95 of the cell) that the published rules leave open.
        """
        lo, hi = (1.02, 1.18) if self.cell.big else (0.9, 1.1)
        jitter = self.rng.uniform(lo, hi)
        f = self.params.radius_frac * jitter
        return (
            f * self.params.x_scale * self.r.w / 2,
            f * self.params.y_scale * self.r.h / 2,
        )

    # -- motif builders -------------------------------------------------
    def paint(self) -> None:
        motifs: tuple[str, ...]
        weights: tuple[float, ...]
        if self.cell.big:
            motifs, weights = BIG_MOTIFS, BIG_MOTIF_WEIGHTS
        elif self.r.w / self.r.h > 1.5:  # wide strip cells favor rectilinear motifs
            motifs, weights = MOTIFS, (0.08, 0.30, 0.10, 0.04, 0.08, 0.22, 0.10, 0.08)
        else:
            motifs, weights = MOTIFS, MOTIF_WEIGHTS
        kind = self.rng.choices(motifs, weights=weights)[0]

        displaced_cell = (
            self.params.displaced
            and kind == "circle"
            and self.rng.random() < self.config.displacement_probability
        )
        dy = 0.0
        if displaced_cell:
            dy = self.r.h * self.config.displacement_frac * self.rng.choice((-1.0, 1.0))

        target = self.displaced if displaced_cell else self.motifs
        clip = self.grid_clip if displaced_cell else self.cell_clip
        getattr(self, f"_{kind}")(target, clip, dy)

        # 11.6: instrumental tracks gain a small circular "dot" element.
        if self.params.displaced and self.rng.random() < self.config.dot_probability:
            r = self.r
            dot_r = self.config.dot_radius_frac * min(r.w, r.h)
            px = r.x + self.rng.choice((0.25, 0.5, 0.75)) * r.w
            py = r.y + self.rng.choice((0.25, 0.5, 0.75)) * r.h
            self.dots.append(_ellipse(px, py, dot_r, dot_r, self.pick(self.bg), self.cell_clip))

    def _diamond(self, out: list[Shape], clip, dy) -> None:
        r = self.r
        rx, ry = self.radii()
        cx, cy = r.cx, r.cy + dy
        c1 = self.pick(self.bg)
        out.append(_poly(_diamond_points(cx, cy, rx, ry), c1, clip))
        roll = self.rng.random()
        if roll < 0.35:  # inner diamond
            out.append(_poly(_diamond_points(cx, cy, rx * 0.5, ry * 0.5),
                             self.pick(self.bg, c1), clip))
        elif roll < 0.55:  # center dot
            d = min(rx, ry) * 0.3
            out.append(_ellipse(cx, cy, d, d, self.pick(self.bg, c1), clip))

    def _square(self, out: list[Shape], clip, dy) -> None:
        r = self.r
        rx, ry = self.radii()
        cx, cy = r.cx, r.cy + dy
        c1 = self.pick(self.bg)
        out.append(_rect(cx - rx, cy - ry, 2 * rx, 2 * ry, c1, clip))
        roll = self.rng.random()
        if roll < 0.40:  # frame: inner square in another color
            c2 = self.pick(self.bg, c1)
            out.append(_rect(cx - rx * 0.62, cy - ry * 0.62, 2 * rx * 0.62, 2 * ry * 0.62,
                             c2, clip))
            if self.rng.random() < 0.5:  # nested cascade
                out.append(_rect(cx - rx * 0.3, cy - ry * 0.3, 2 * rx * 0.3, 2 * ry * 0.3,
                                 self.pick(self.bg, c2), clip))

    def _circle(self, out: list[Shape], clip, dy) -> None:
        r = self.r
        rx, ry = self.radii()
        # The reference posters render circular forms round even when the
        # loudness/tempo scale is anisotropic; only rectilinear motifs show
        # the stretch clearly.
        rx = ry = min(rx, ry)
        cx, cy = r.cx, r.cy + dy
        roll = self.rng.random()
        if roll < 0.30:  # two-color split halves
            c1 = self.pick(self.bg)
            c2 = self.pick(self.bg, c1)
            gx0, gy0, gw, gh = clip
            if self.rng.random() < 0.5:  # vertical split
                left = (gx0, gy0, max(0.0, cx - gx0), gh)
                right = (cx, gy0, max(0.0, gx0 + gw - cx), gh)
                out.append(_ellipse(cx, cy, rx, ry, c1, left))
                out.append(_ellipse(cx, cy, rx, ry, c2, right))
            else:  # horizontal split
                top = (gx0, gy0, gw, max(0.0, cy - gy0))
                bottom = (gx0, cy, gw, max(0.0, gy0 + gh - cy))
                out.append(_ellipse(cx, cy, rx, ry, c1, top))
                out.append(_ellipse(cx, cy, rx, ry, c2, bottom))
        elif roll < 0.55:  # ring: circle, inner circle, optional dot
            c1 = self.pick(self.bg)
            c2 = self.pick(self.bg, c1)
            out.append(_ellipse(cx, cy, rx, ry, c1, clip))
            out.append(_ellipse(cx, cy, rx * 0.72, ry * 0.72, c2, clip))
            if self.rng.random() < 0.6:
                d = min(rx, ry) * 0.18
                out.append(_ellipse(cx, cy, d, d, self.pick(c2), clip))
        else:  # solid circle
            out.append(_ellipse(cx, cy, rx, ry, self.pick(self.bg), clip))

    def _hourglass(self, out: list[Shape], clip, dy) -> None:
        # Two triangles, apexes meeting at the cell center (vertical bowtie);
        # observed in Lover, Holocene, Sunset, Real Love Baby.
        r = self.r
        c1 = self.pick(self.bg)
        inset = (1 - self.params.x_scale * self.params.radius_frac) / 2
        x0, x1 = r.x + r.w * max(0.0, inset), r.x + r.w * min(1.0, 1 - inset)
        out.append(_poly([(x0, r.y), (x1, r.y), (r.cx, r.cy)], c1, clip))
        out.append(_poly([(x0, r.y + r.h), (x1, r.y + r.h), (r.cx, r.cy)], c1, clip))

    def _semis(self, out: list[Shape], clip, dy) -> None:
        # Two semicircles anchored on opposite edges, facing the center.
        r = self.r
        rx, ry = self.radii()
        c1 = self.pick(self.bg)
        c2 = c1 if self.rng.random() < 0.5 else self.pick(self.bg, c1)
        rr = min(rx, ry)
        if self.rng.random() < 0.5:  # anchored top / bottom
            out.append(_ellipse(r.cx, r.y, rr, rr, c1, self.cell_clip))
            out.append(_ellipse(r.cx, r.y + r.h, rr, rr, c2, self.cell_clip))
        else:  # anchored left / right
            out.append(_ellipse(r.x, r.cy, rr, rr, c1, self.cell_clip))
            out.append(_ellipse(r.x + r.w, r.cy, rr, rr, c2, self.cell_clip))

    def _bar(self, out: list[Shape], clip, dy) -> None:
        r = self.r
        c1 = self.pick(self.bg)
        bar_h = r.h * self.rng.uniform(0.22, 0.38)
        by = r.cy + dy - bar_h / 2 + r.h * self.rng.uniform(-0.18, 0.18)
        inset = r.w * (1 - self.params.x_scale * self.params.radius_frac) / 2
        out.append(_rect(r.x + max(0.0, inset), by, r.w - 2 * max(0.0, inset), bar_h, c1, clip))
        if self.rng.random() < 0.4:  # second, full-bleed bar
            c2 = self.pick(self.bg, c1)
            bar2 = r.h * 0.18
            out.append(_rect(r.x, r.y + r.h - bar2 * 2.2, r.w, bar2, c2, clip))

    def _hmotif(self, out: list[Shape], clip, dy) -> None:
        # Two vertical bars joined by a center bar, with oval accents
        # (Lover row 3, Sunset bottom row, Holocene bottom row).
        r = self.r
        c1 = self.pick(self.bg)
        w = r.w * self.params.radius_frac * self.params.x_scale
        h = r.h * self.params.radius_frac * self.params.y_scale
        bar_w = w * 0.32
        x0, x1 = r.cx - w / 2, r.cx + w / 2 - bar_w
        y0 = r.cy - h / 2
        out.append(_rect(x0, y0, bar_w, h, c1, clip))
        out.append(_rect(x1, y0, bar_w, h, c1, clip))
        out.append(_rect(x0, r.cy - h * 0.16, w, h * 0.32, c1, clip))
        if self.rng.random() < 0.6:
            c2 = self.pick(self.bg, c1)
            ry = h * 0.18
            out.append(_ellipse(r.cx, y0, w * 0.16, ry, c2, clip))
            out.append(_ellipse(r.cx, y0 + h, w * 0.16, ry, c2, clip))

    def _triangle(self, out: list[Shape], clip, dy) -> None:
        # Half-cell diagonal triangle (Real Love Baby, Vienna, Sunset).
        r = self.r
        c1 = self.pick(self.bg)
        corners = [
            (r.x, r.y), (r.x + r.w, r.y), (r.x + r.w, r.y + r.h), (r.x, r.y + r.h),
        ]
        start = self.rng.randrange(4)
        tri = [corners[start], corners[(start + 1) % 4], corners[(start + 2) % 4]]
        out.append(_poly(tri, c1, clip))
        if self.rng.random() < 0.4:  # small dot accent in the open half
            d = min(r.w, r.h) * 0.08
            ox, oy = corners[(start + 3) % 4]
            px = ox + (r.cx - ox) * 0.5
            py = oy + (r.cy - oy) * 0.5
            out.append(_ellipse(px, py, d, d, self.pick(self.bg, c1), clip))


def build_scene(
    data: TrackData,
    params: RenderParams,
    config: RenderConfig,
    seed_override: str | None = None,
) -> Scene:
    palette = get_palette(params.key)
    bg_square, grid = _grid_rect(params, config)
    cells = _cells(params, grid, config)

    seed_base = seed_override if seed_override is not None else params.track_id

    layers: dict[str, list[Shape]] = {
        "background": [
            _rect(0, 0, config.artboard_width, config.artboard_height, "#ffffff"),
            _rect(bg_square.x, bg_square.y, bg_square.w, bg_square.h, palette.background),
        ],
        "cell_bg": [],
        "motifs": [],
        "displaced": [],
        "dots": [],
    }

    def touches(a: Rect, b: Rect) -> bool:
        h_edge = abs(a.y + a.h - b.y) < 1 or abs(b.y + b.h - a.y) < 1
        v_edge = abs(a.x + a.w - b.x) < 1 or abs(b.x + b.w - a.x) < 1
        x_overlap = min(a.x + a.w, b.x + b.w) - max(a.x, b.x) > 1
        y_overlap = min(a.y + a.h, b.y + b.h) - max(a.y, b.y) > 1
        return (h_edge and x_overlap) or (v_edge and y_overlap)

    painted: list[tuple[Rect, str]] = []
    for cell in cells:
        rng = random.Random(cell_seed(seed_base, cell.index))
        painter = _CellPainter(cell, rng, palette, params, config, grid)
        # PROVISIONAL: avoid repeating the background of any already-painted
        # edge-neighbor (the reference posters read as a checker of distinct
        # fields).
        neighbor_bgs = {bg for r0, bg in painted if touches(cell.rect, r0)}
        if painter.bg in neighbor_bgs:
            painter.bg = painter.pick(*neighbor_bgs)
        painted.append((cell.rect, painter.bg))
        painter.paint()
        r = cell.rect
        layers["cell_bg"].append(_rect(r.x, r.y, r.w, r.h, painter.bg))
        layers["motifs"].extend(painter.motifs)
        layers["displaced"].extend(painter.displaced)
        layers["dots"].extend(painter.dots)

    return Scene(
        artboard=(config.artboard_width, config.artboard_height),
        bg_square=bg_square,
        grid=grid,
        cells=cells,
        layers=layers,
        palette=palette,
        params=params,
    )
