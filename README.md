# geomusic

A Python command-line reimplementation of Samantha Shanne's **(Geo) Musical
Configurations** — a rule-based parametric system that translates Spotify
track data into planar geometric compositions (Shanne & Hammond, SIGGRAPH
Posters 2026).

Give it a Spotify track URL, URI, or raw track id; it retrieves the track's
metadata and Audio Features, caches the raw responses, and renders a poster as
SVG plus a PNG preview.

```bash
uv sync
uv run geomusic "https://open.spotify.com/track/6Jv7kjGkhY2fT4yuBF3aTz"
```

## Credentials

Credentials are read only from the environment (a local `.env` is supported):

```dotenv
SPOTIFY_CLIENT_ID=...
SPOTIFY_CLIENT_SECRET=...
```

Spotify's `/v1/audio-features` endpoint is deprecated for apps created after
November 2024; rendering also works fully offline from cached JSON (see
`--offline` and `tests/fixtures/spotify/`).

## Usage

```bash
uv run geomusic 6Jv7kjGkhY2fT4yuBF3aTz
uv run geomusic spotify:track:4U45aEWtQhrm8A5mxPaFZ7 --debug-overlay
uv run geomusic 0Z57YWES04xGh3AImDz6Qr --offline
uv run geomusic 6Jv7kjGkhY2fT4yuBF3aTz --reference references/source/final/Lover-You-Should-ve-Come-Over_annotated.jpg
```

Options: `--output`, `--format svg|png|both`, `--size WxH`, `--refresh`,
`--offline`, `--dump-data`, `--debug-overlay`, `--reference`, `--config`,
`--seed`, `--verbose`.

Output goes to `output/<track-id>/`: `track.json`, `parameters.json`,
`composition.svg`, `composition.png`, plus `comparison.json` /
`comparison-diff.png` when `--reference` is used.

## Mapping rules (published)

| Feature | Visual channel |
|---|---|
| `mode` | 0 → rectangular strip composition, 1 → square composition |
| first 4 chars of `track_id` | `isdigit` booleans → QuadSub quadrant subdivision (BL, BR, TR, TL) |
| `loudness` | grid scale in x |
| `tempo` | grid scale in y |
| `speechiness` | motif radius |
| `instrumentalness` | > 0 → motif displacement + added circular element |
| `key` | one of 12 fixed palettes (extracted from the source Grasshopper screenshot) |

Undocumented mappings are reconstructed provisionally and recorded in
`reconstruction_notes.md`; all tuneable constants live in
`src/geomusic/config.py`.

## Reference workflow

```bash
uv run python scripts/download_references.py   # fetch source images (curated manifest)
uv run python scripts/measure_references.py    # calibrate layout constants
uv run python scripts/extract_palettes.py      # extract the 12 key palettes
uv run python scripts/render_palette_contact_sheet.py
uv run python scripts/fetch_reference_tracks.py
uv run python scripts/render_reference_set.py
uv run python scripts/compare_reference_set.py
uv run pytest
```

Reference images under `references/source/` are downloaded research inputs;
verify copyright/permission terms before redistributing them.
