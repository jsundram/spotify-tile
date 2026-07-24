"""QuadSub-style grid subdivision.

Evidence (references/source/track-id/2_square-subdivisions.png): Grasshopper's
QuadSub takes four boolean toggles B1..B4.  The examples show

    F,F,F,F -> 4 cells        T,F,F,F -> 7 cells (bottom-left split)
    T,T,F,F -> 10 cells (both bottom quadrants split)
    T,T,T,T -> 16 cells

so each True splits its quadrant once into 2x2, and the toggle order is the
Rhino (y-up) quadrant order: B1=bottom-left, B2=bottom-right, B3=top-right,
B4=top-left.  This is confirmed by the final posters: Sunset ("76G5" ->
T,T,F,T) leaves exactly the top-right quadrant whole, and Lover ("6Jv7" ->
T,F,F,T) leaves top-right and bottom-right whole.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    w: float
    h: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


@dataclass(frozen=True)
class Cell:
    rect: Rect
    index: int  # stable enumeration index (used for seeding)
    quadrant: int  # 0=BL, 1=BR, 2=TR, 3=TL for squares; row index for strips
    big: bool  # True when the cell is a whole (unsubdivided) quadrant


# Screen-space (top-left origin) offsets of each quadrant, in flag order
# B1=bottom-left, B2=bottom-right, B3=top-right, B4=top-left.
_QUADRANT_OFFSETS = ((0.0, 0.5), (0.5, 0.5), (0.5, 0.0), (0.0, 0.0))


def subdivide_square(bounds: Rect, flags: tuple[bool, bool, bool, bool]) -> list[Cell]:
    """Split ``bounds`` into 4 quadrants, splitting flagged quadrants 2x2.

    Cell count: 4 + 3 * count(True).
    """
    cells: list[Cell] = []
    half_w, half_h = bounds.w / 2, bounds.h / 2
    index = 0
    for quadrant, ((fx, fy), flag) in enumerate(zip(_QUADRANT_OFFSETS, flags)):
        qx, qy = bounds.x + fx * bounds.w, bounds.y + fy * bounds.h
        if flag:
            for sy in (0.0, 0.5):
                for sx in (0.0, 0.5):
                    cells.append(
                        Cell(
                            Rect(qx + sx * half_w, qy + sy * half_h, half_w / 2, half_h / 2),
                            index,
                            quadrant,
                            big=False,
                        )
                    )
                    index += 1
        else:
            cells.append(Cell(Rect(qx, qy, half_w, half_h), index, quadrant, big=True))
            index += 1
    return cells


def rect_strip(bounds: Rect, heights: tuple[float, ...]) -> list[Cell]:
    """Rectangular-composition template: a vertical strip of stacked cells.

    ``bounds`` is the strip; ``heights`` are relative cell heights top-to-bottom
    (calibrated to (1, 1, 0.5, 0.5) from Judas / Bohemian Rhapsody).
    """
    total = sum(heights)
    cells = []
    y = bounds.y
    for i, h_rel in enumerate(heights):
        h = bounds.h * h_rel / total
        # Full-height cells count as "big" so they receive large motifs.
        cells.append(Cell(Rect(bounds.x, y, bounds.w, h), i, i, big=h_rel >= 1.0))
        y += h
    return cells
