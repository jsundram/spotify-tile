# References

Research and regression inputs for the (Geo) Musical Configurations
reimplementation.

## Sources

- Samantha Shanne and Sarah Hammond, "(Geo) Musical Configurations: A
  Parametric Framework for Translating Musical Data into Planar Geometric
  Compositions," SIGGRAPH Posters 2026 (`../GeoMusical Configurations.pdf`).
- Portfolio page: <https://samanthashanne.cargo.site/Geo-Musical-Configurations>

## Contents

- `source/` — original images downloaded from the portfolio's freight.cargo
  assets by `scripts/download_references.py`; `source/download-manifest.json`
  records URL, path, size, SHA-256, and status for each file.  **Do not edit
  or recompress these files.**
- `palette-crops.json` — panel crop rectangles and chip boxes located in
  `source/key/4_key_script.png` by `scripts/extract_palettes.py`; the palette
  constants derived from them are checked in at
  `src/geomusic/data/palettes.json` and pinned to the source image hash.
- `reference-manifest.json` — reference tracks (verified Spotify ids) paired
  with their poster images, used by `scripts/render_reference_set.py` and
  `scripts/compare_reference_set.py`.
- `processed/` — generated artifacts (measurements, renders, diffs, reports,
  palette contact sheet).  Regenerable; not source material.

## Copyright

The images under `source/` are Samantha Shanne's artwork, downloaded for
research and visual-regression use.  Before publishing or redistributing a
repository containing them, verify the applicable copyright and permission
terms; a public package may instead ship only the downloader, manifests,
hashes, and locally generated outputs.
