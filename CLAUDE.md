# CLAUDE.md

Guidance for Claude Code (and other agents) working in this repository.

## What this is

`geomusic` is a Python CLI that reimplements Samantha Shanne & Sarah Hammond's
**(Geo) Musical Configurations** (SIGGRAPH Posters 2026): it turns a Spotify
track's metadata + audio features into a planar geometric poster, rendered as
SVG with a PNG preview. Given a track URL/URI/id it fetches and caches the raw
API responses, derives render parameters, builds a scene, and writes output.

Package lives in `src/geomusic/`; the console entry point is
`geomusic = geomusic.cli:main`.

## Commands

```bash
uv sync                                   # install deps (incl. dev group)
uv run geomusic <track-url-uri-or-id>     # render a poster
uv run geomusic <id> --offline            # render from cached JSON only
uv run pytest                             # test suite (live Spotify tests deselected by default)
uv run pytest -m spotify_live             # opt-in live API tests (needs credentials)
uv run ruff check .                       # lint
uv run mypy src                           # type check
```

Output goes to `output/<track-id>/`: `track.json`, `parameters.json`,
`composition.svg`, `composition.png`, plus `comparison.*` when `--reference`
is passed. Key CLI flags: `--format svg|png|both`, `--size WxH`, `--offline`,
`--refresh`, `--dump-data`, `--debug-overlay`, `--reference`, `--config`,
`--seed`, `--verbose`.

## Architecture (data flow)

`inputs` (parse track id) → `spotify` (fetch metadata + features) with
`reccobeats` fallback → `cache` (canonical raw JSON on disk) → `models`
(pydantic `TrackData`) → `normalize.derive` (raw features → `RenderParams`) →
`subdivision` (QuadSub grid) + `geometry.build_scene` (cells, motifs,
displacement) → `render_svg` / `render_png` → `compare` (visual regression vs
reference posters).

Module sizes are small (each ~50–170 lines; `geometry.py` is the largest at
~365). Read the module docstring first — they explain the reconstruction
reasoning and cite the reference evidence.

## Conventions that matter

- **All tuneable constants live in `src/geomusic/config.py`.** Do not scatter
  magic numbers into other modules. Constants are tagged `CALIBRATED` (measured
  from reference images) or `PROVISIONAL` (a deterministic guess where the
  source is silent). Preserve those tags when editing.
- **Determinism is a hard requirement.** Undisclosed choices (motif variety,
  per-cell color, which cells displace) are seeded from
  `SHA-256(track_id + renderer_version + cell_index)` via
  `normalize.cell_seed`. Same input must always produce the same output — this
  is what the visual-regression tests rely on. Never introduce unseeded
  randomness or wall-clock/`os`-dependent behavior into rendering.
- **Published vs reconstructed mappings.** The mapping rules in the README's
  table are from the paper and applied literally. Everything else is
  provisional and documented in `reconstruction_notes.md` — update that file
  when you change reconstructed behavior. Bump `CONFIG_VERSION`
  (`config.py`) / `RENDERER_VERSION` (`__init__.py`) when a change alters
  rendered output.
- Type hints throughout; mypy is expected to stay green. Ruff line length 100.

## Audio features API note

Spotify's `/v1/audio-features` is deprecated for apps created after Nov 2024,
so `reccobeats.py` provides a same-schema fallback keyed by track id. Rendering
works fully offline from cached JSON (`--offline`, `tests/fixtures/spotify/`),
which is the reliable path when credentials or the live API are unavailable.

## Credentials

Read only from the environment / a local `.env` (gitignored):
`SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`. Never commit real credentials;
`.env.example` documents the shape.

## Third-party assets — do not redistribute blindly

`references/source/` holds Samantha Shanne's original artwork and
`GeoMusical Configurations.pdf` is the SIGGRAPH paper. These are research
inputs, not our work. See `references/README.md`: before publishing this repo,
confirm copyright/permission terms — a public version may ship only the
downloader, manifests, and hashes rather than the images themselves.
