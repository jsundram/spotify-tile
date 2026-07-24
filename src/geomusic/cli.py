"""geomusic command-line interface."""

from __future__ import annotations

import json
from pathlib import Path
from typing import NoReturn

import typer
from dotenv import load_dotenv
from rich.console import Console

from . import cache
from .compare import write_comparison
from .config import config_dict, load_config
from .geometry import build_scene
from .inputs import InputError, parse_track_input
from .models import TrackData
from .normalize import derive
from .reccobeats import ReccoBeatsError, complete_features, fetch_audio_features
from .render_png import svg_to_png
from .render_svg import render_svg
from .spotify import ForbiddenError, SpotifyClient, SpotifyError

app = typer.Typer(add_completion=False)
console = Console()
err_console = Console(stderr=True)


def _fail(message: str, code: int = 1) -> NoReturn:
    err_console.print(f"[red]error:[/red] {message}")
    raise typer.Exit(code)


@app.command()
def render(
    track_input: str = typer.Argument(..., metavar="INPUT",
                                      help="Spotify track URL, URI, or track id"),
    output: Path | None = typer.Option(None, "--output",
                                          help="Output directory (default output/<track-id>/)"),
    format: str = typer.Option("both", "--format", help="svg | png | both"),
    size: str | None = typer.Option(None, "--size", help="WIDTHxHEIGHT override"),
    refresh: bool = typer.Option(False, "--refresh", help="Ignore valid cache; refetch"),
    offline: bool = typer.Option(False, "--offline", help="Never call Spotify"),
    dump_data: bool = typer.Option(False, "--dump-data",
                                   help="Print normalized rendering parameters as JSON"),
    debug_overlay: bool = typer.Option(False, "--debug-overlay",
                                       help="Draw cell bounds and parameter labels"),
    reference: Path | None = typer.Option(None, "--reference",
                                             help="Compare the PNG against a reference image"),
    config_path: Path | None = typer.Option(None, "--config",
                                               help="Alternate rendering configuration (JSON)"),
    seed: str | None = typer.Option(None, "--seed",
                                       help="Override deterministic seed (diagnostics only)"),
    verbose: bool = typer.Option(False, "--verbose"),
) -> None:
    """Render a (Geo) Musical Configurations poster for a Spotify track."""
    load_dotenv()

    if format not in {"svg", "png", "both"}:
        _fail(f"--format must be svg, png, or both (got {format!r})")

    try:
        track_id = parse_track_input(track_input)
    except InputError as exc:
        _fail(str(exc))

    try:
        config = load_config(config_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _fail(f"could not load config {config_path}: {exc}")

    if size:
        try:
            w, h = (int(v) for v in size.lower().split("x"))
        except ValueError:
            _fail(f"--size must look like 2400x2400 (got {size!r})")
        from dataclasses import replace

        config = replace(config, artboard_width=w, artboard_height=h)

    # --- data acquisition ---------------------------------------------
    doc = None
    if not refresh:
        try:
            doc = cache.load(track_id, offline=offline)
        except cache.CacheMissError as exc:
            _fail(str(exc))
    if doc is None:
        if offline:
            _fail(f"no cached data for {track_id} (offline mode)")
        try:
            with SpotifyClient() as client:
                raw_track = client.get_track(track_id)
                try:
                    raw_features = client.get_audio_features(track_id)
                except ForbiddenError:
                    if verbose:
                        console.print("audio-features 403; falling back to ReccoBeats")
                    features = fetch_audio_features([track_id]).get(track_id)
                    if features is None:
                        _fail(f"track {track_id} is not in the ReccoBeats dataset "
                              "and Spotify audio-features access is gone (403)")
                    raw_features = complete_features(features, raw_track)
        except (SpotifyError, ReccoBeatsError) as exc:
            _fail(str(exc))
        doc = cache.make_doc(raw_track, raw_features)
        cache.save(track_id, doc)
        if verbose:
            console.print(f"fetched and cached {cache.cache_path(track_id)}")
    elif verbose:
        console.print(f"using cache {cache.cache_path(track_id)}")

    try:
        data = TrackData.from_cache_doc(doc)
    except (KeyError, ValueError) as exc:
        _fail(f"track data is unusable: {exc}")

    # --- derivation and rendering -------------------------------------
    params = derive(data, config)
    scene = build_scene(data, params, config, seed_override=seed)
    svg_text = render_svg(scene, data, config,
                          cache_fetched_at=doc.get("fetched_at"),
                          debug_overlay=debug_overlay)

    out_dir = output if output is not None else Path("output") / track_id
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "track.json").write_text(json.dumps(doc, indent=2))
    payload = {"parameters": params.model_dump(), "config": config_dict(config)}
    (out_dir / "parameters.json").write_text(json.dumps(payload, indent=2))

    svg_path = out_dir / "composition.svg"
    png_path = out_dir / "composition.png"
    if format in {"svg", "both"}:
        svg_path.write_text(svg_text)
        console.print(f"wrote {svg_path}")
    if format in {"png", "both"} or reference is not None:
        svg_to_png(svg_text, png_path)
        console.print(f"wrote {png_path}")

    if dump_data:
        console.print_json(json.dumps(params.model_dump()))

    if reference is not None:
        if not reference.exists():
            _fail(f"reference image not found: {reference}")
        metrics = write_comparison(png_path, reference, out_dir)
        console.print_json(json.dumps(metrics))

    if verbose:
        console.print(
            f"[green]{data.track.name}[/green] — {', '.join(data.track.artists)} | "
            f"{params.composition} | key {params.key} ({params.pitch}) | "
            f"cells {params.cell_count}"
        )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
