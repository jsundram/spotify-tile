# Reconstruction notes

Log of evidence, decisions, and open questions for the Python reimplementation
of (Geo) Musical Configurations.  Constants live in `src/geomusic/config.py`.

## 2026-07-24 — QuadSub interpretation (CONFIRMED)

Evidence: `references/source/track-id/2_square-subdivisions.png` shows QuadSub
with toggles B1..B4 and the captions F,F,F,F = 4; T,F,F,F = 7 (bottom-left
quadrant split); T,T,F,F = 10 (both bottom quadrants); T,T,T,T = 16.  The
toggle order is therefore the Rhino y-up quadrant order **B1=bottom-left,
B2=bottom-right, B3=top-right, B4=top-left**, each True splitting its quadrant
once into 2×2 (4 + 3·n cells).

Cross-checks: Sunset (`76G5` → T,T,F,T) leaves exactly the top-right quadrant
whole; Lover (`6Jv7` → T,F,F,T) leaves bottom-right and top-right whole;
Vienna and Real Love Baby (both T,F,T,T) leave bottom-right whole; Holocene
(`35Ki` → T,T,F,F) leaves both top quadrants whole.  All match the posters.

Decision: implemented exactly in `subdivision.subdivide_square`.
Confidence: high.  Note: the spec's provisional reading-order interpretation
(TL,TR,BL,BR) is disproven by the reference images; cell counts are identical.

## 2026-07-24 — Artboard, background square, grid transform (CONFIRMED)

Evidence: all eight reference posters are 2400×2400 with the background square
inset 212 px on every side (`scripts/measure_references.py`).
`mode/1_GH-script.png` shows the mode filter feeding Scale NU components:
square comp scale **0.535**, rectangular comp scale **X=0.263, Y=0.8**.
Measured: square grids are 1058×1058 centered (1976·0.535 = 1057); rect strips
are 520×1582 (1976·0.263 = 520, 1976·0.8 = 1581).  Loudness/tempo do NOT
resize the outer grid (all square grids are identical despite loudness ranging
from −5.67 to −15.88).

Decision: grid = background square scaled about its center by the mode factor.
Confidence: high.

## 2026-07-24 — Rectangular template (CALIBRATED)

Evidence: Judas and Bohemian Rhapsody both show a single vertical stack of
four cells with relative heights 1, 1, 0.5, 0.5.  The strip is not a squeezed
QuadSub grid (Bohemian's flags T,F,F,F would produce visible columns).

Decision: fixed template `rect_cell_heights = (1, 1, 0.5, 0.5)`.
Confidence: medium-high (two examples).

## 2026-07-24 — Palettes (CONFIRMED, source-derived)

Extracted from `key/4_key_script.png` (SHA-256 pinned) by
`scripts/extract_palettes.py`: 12 panels row-major = keys 0..11, 8 swatches
each.  Validated against five independent sources: Judas/Vienna caption strips
(= key 10 chips exactly), Real Love Baby strip (key 7), Lover strip (key 2),
Holocene artwork (key 1), Bohemian artwork (key 0).

Backgrounds: each key has one fixed background color.  Evidence-backed for
keys 0, 1, 2, 5, 7, 10 (poster background color matches a chip).  For keys 1,
2, 5, 7, 10 the background is the **first (topmost) chip**; key 0 is the
exception (first chip is white; background is the 4th chip, dark purple).
Keys 3, 4, 6, 8, 9, 11 use the provisional first-chip rule.
Confidence: high for evidenced keys, medium for the rest.

## 2026-07-24 — Speechiness → radius (CALIBRATED domain)

Evidence: `instrumentalness/3_gh-script2.png` group "speechiness = radius of
polygon": ReMap with source domain **[0, 0.1]** (panels 0 / 0.1) and target
related to 0.4 and the cell half-length.  All reference tracks have
speechiness 0.03–0.07, producing large motifs, consistent with the narrow
domain.

Decision: `speechiness_domain = (0, 0.1)`, radius range tuned to (0.5, 1.05)
of the cell half-size against measured motif extents (0.55–0.95 of the cell).
Confidence: domain high; range tuned.

## 2026-07-24 — Loudness/tempo → non-uniform polygon scale (PARTIAL)

Evidence: `scaling/3_gh-script.png`: loudness ReMap domain [−60, 0], tempo
ReMap domain [50, 250], feeding Scale NU X and Y on the per-cell polygon;
oversized polygons are clipped ("if polygon is scaled beyond the rectangle,
there is Region Difference").

Open question: the exact target ranges.  Literal [0.2, 1.25] produced motif
aspect ratios ~2:1 for the reference tracks, which the posters do not show
(most motifs are near-symmetric).  Current ranges x (0.6, 1.15) /
y (0.6, 1.2) are tuned so reference-track motif extents match measurements.
Confidence: mapping direction high; ranges tuned, revisit with more examples.

## 2026-07-24 — Instrumentalness → displacement + circle (PARTIAL)

Evidence: published binary rule; the Grasshopper wiring moves polygons along
the **Y unit vector only** and adds a circle with radius = cell/8 (`A/B` with
8) plus a "dot".  Lover (instrumentalness = 0.000011) shows motifs moved all
the way to cell edges, so magnitude is NOT proportional to the value; Vienna
and Bohemian (instrumentalness = 0) show perfectly centered motifs.

Decision: literal binary gate (`> 0`); displaced cells move their motif by
±0.5·cell-height (seeded sign), clipped to the grid so they spill across
neighboring cells; dot elements radius cell/8.  Which cells displace is a
seeded per-cell gate (probability 0.45) — the original selection logic
(area-sort / list-split components) is not fully legible.
Confidence: gate high; magnitude/selection medium.

## 2026-07-24 — Motif vocabulary (RECONSTRUCTED)

The per-cell motif is not documented.  Observed vocabulary across the eight
posters: diamonds (plain / inner diamond / center dot), squares (solid /
frame / nested cascade), circles (solid / two-color split / ring / dotted),
semicircle pairs anchored to opposite edges, hourglasses (two triangles
meeting at center), bars, H-motifs with oval accents, and half-cell diagonal
triangles.  Implemented with seeded weighted selection
(`geometry._CellPainter`); whole-quadrant cells prefer large simple forms
(circle / diamond / hourglass / semis); wide strip cells prefer rectilinear
forms.  Cell backgrounds avoid repeating the previous cell's color.

| feature | hypothesized visual channel | evidence | confidence | current formula |
|---|---|---|---|---|
| danceability | motif rotation or placement regularity | labeled prominently in captions; no visible wiring | low | not mapped |
| energy | motif density / complexity | labeled prominently in captions | low | not mapped |
| valence | color weighting within palette | none visible | low | not mapped |
| liveness | local variation | none visible | low | not mapped |
| acousticness | — | not referenced by source | low | not mapped |

These remain open reconstruction targets; per-cell seeded choice currently
carries the variety they may control.

## Comparison status (2026-07-24)

`scripts/compare_reference_set.py` aggregate similarity: **0.796** over eight
references (range 0.77–0.84).  Stage A (topology: composition type, cell
count, grid placement, palette) matches for all eight.  Stage B+ is limited
by the undisclosed per-cell motif selection, which no general rule can
reproduce cell-for-cell; improvements should come from decoding more of the
Grasshopper wiring, not from per-song tuning.

## 2026-07-24 — Style-tightening pass (motif coherence)

Observation: first-pass renders matched topology but not the posters' visual
character — circles rendered as loudness/tempo-stretched ellipses, squares
and diamonds displaced, and motif sizes varied too widely.

Changes (all in geometry.py / config.py, applied to every track):
- circular forms always render round (min of the two scaled radii); the
  non-uniform loudness/tempo scale reads through rectilinear motifs only;
- displacement applies only to circle motifs (observed: displaced forms in
  the posters are circles/semicircles; squares and diamonds stay centered);
- size jitter narrowed to 0.9–1.1 (1.02–1.18 for whole quadrants) and
  speechiness radius range raised to (0.62, 1.05);
- dot elements snap to quarter-grid positions;
- cell backgrounds avoid repeating any edge-neighbor's color (spatial check,
  not just the previous cell in index order).

Metric effect is neutral (aggregate 0.796) — pixel metrics cannot reward
style coherence when per-cell motif choices differ — but visual family
resemblance is substantially closer.  Cell-for-cell identity remains
impossible without the original Grasshopper definition's per-cell selection
logic, which no published source discloses.
