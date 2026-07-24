#!/usr/bin/env python3
"""Generate a 1080x1920 Instagram-story poster for a rendered geomusic track.

This is a *presentation* layer on top of the geomusic render pipeline. For a
given track it:

  1. Re-renders the composition (caption-free) via the normal pipeline.
  2. Crops to the palette-background field and floats it, full-bleed, on a
     story canvas painted the same palette background -- so the artwork's own
     margin blends seamlessly and the motif reads as the focal point.
  3. Sets the composer and performer as large text in two palette-derived hues,
     plus a shortened work / movement line, on a contrasting palette panel.

Composer vs. performer follows Spotify's classical convention: the first
credited artist is the composer, the remaining artist(s) are the performer(s).

The constants below are *story presentation* choices and are deliberately kept
separate from the render-determinism config in ``src/geomusic/config.py`` --
nothing here feeds back into the visual-regression pipeline.

A track is given as an output dir, a playlist index, or a Spotify URL / URI /
id; an unprocessed track is resolved via the geomusic cache or a live fetch
(disable with --offline).

Usage:
    uv run python scripts/instagram_story.py <dir | index | URL | URI | id>
    uv run python scripts/instagram_story.py --all            # whole playlist
    uv run python scripts/instagram_story.py 181 --out foo.png
    uv run python scripts/instagram_story.py https://open.spotify.com/track/...
"""

from __future__ import annotations

import argparse
import colorsys
import json
import re
from pathlib import Path
from xml.sax.saxutils import escape

from dotenv import load_dotenv
from PIL import ImageFont

from geomusic import cache
from geomusic.config import load_config
from geomusic.geometry import build_scene
from geomusic.inputs import InputError, parse_track_input
from geomusic.models import TrackData
from geomusic.normalize import derive
from geomusic.palettes import Palette, get_palette
from geomusic.reccobeats import ReccoBeatsError, complete_features, fetch_audio_features
from geomusic.render_png import svg_to_png
from geomusic.render_svg import render_svg
from geomusic.spotify import ForbiddenError, SpotifyClient, SpotifyError

# --- story canvas -----------------------------------------------------------
STORY_W = 1080
STORY_H = 1920

# Art placement (all in story px). The square palette-background field is fit to
# the height of the art zone and centered; it bleeds slightly off the sides
# (canvas-colored, so invisibly). Fitting the whole field -- rather than zooming
# the motif -- keeps tall "rect" motifs (which nearly fill the field) uncropped.
ART_TOP = 64
ART_BOTTOM = 1200
SQUARE_MOTIF_BOOST = 1.32  # enlarge square motifs (margins clip harmlessly)

PANEL_TOP = 1250          # where the text panel begins
PAD = 96                  # left/right text inset

# Typography (macOS system fonts; cairosvg resolves them via fontconfig).
# Roman = Didot (a striking high-contrast display serif); italic = Palatino.
# Didot's *italic* kerns badly in cairosvg (loose gaps after capitals), whereas
# Palatino's italic is clean -- and a classic, apt match for classical music.
# The paths/indices are used only for PIL width measurement.
FONT_FAMILY = "Didot"
FONT_ITALIC_FAMILY = "Palatino"
_FONT_FILES = {
    False: ("/System/Library/Fonts/Supplemental/Didot.ttc", 0),  # Didot Regular
    True: ("/System/Library/Fonts/Palatino.ttc", 1),             # Palatino Italic
}

COMPOSER_MAX = 92
PERFORMER_MAX = 74
META_SIZE = 40
LINE_SPACING = 1.28

# --- color utilities --------------------------------------------------------


def _hex_to_rgb01(c: str) -> tuple[float, float, float]:
    c = c.lstrip("#")
    return tuple(int(c[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def _rel_luminance(c: str) -> float:
    def lin(u: float) -> float:
        return u / 12.92 if u <= 0.03928 else ((u + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(x) for x in _hex_to_rgb01(c))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: str, b: str) -> float:
    la, lb = _rel_luminance(a), _rel_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _hsv(c: str) -> tuple[float, float, float]:
    return colorsys.rgb_to_hsv(*_hex_to_rgb01(c))


def _hue_dist(h1: float, h2: float) -> float:
    d = abs(h1 - h2)
    return min(d, 1 - d)


def pick_colors(palette: Palette) -> dict[str, str]:
    """Derive canvas / panel / text hues from the track's key palette.

    canvas   = the palette background (matches the art field -> seamless).
    panel    = the palette color with the most contrast vs. the background,
               guaranteeing a clean seam between art and text panel.
    composer = most saturated legible hue on the panel.
    performer= a second legible hue, chosen to differ from composer.
    meta     = the most legible (highest-contrast) hue, for supporting text.
    """
    colors = list(palette.colors)
    bg = palette.background

    panel = max(colors, key=lambda c: _contrast(c, bg))

    cands = [c for c in colors if c != panel and _contrast(c, panel) >= 4.5]
    if len(cands) < 2:
        cands = sorted(
            (c for c in colors if c != panel),
            key=lambda c: _contrast(c, panel),
            reverse=True,
        )[:4]

    by_sat = sorted(cands, key=lambda c: _hsv(c)[1], reverse=True)
    composer = by_sat[0]
    ch = _hsv(composer)[0]
    performer = next(
        (c for c in by_sat[1:] if _hue_dist(_hsv(c)[0], ch) > 0.06 or _hsv(c)[1] < 0.15),
        by_sat[1] if len(by_sat) > 1 else composer,
    )
    meta = max(cands, key=lambda c: _contrast(c, panel))
    return {
        "canvas": bg,
        "panel": panel,
        "composer": composer,
        "performer": performer,
        "meta": meta,
    }


# --- title parsing ----------------------------------------------------------

_CATALOG = re.compile(
    r",\s*(?:G|K|KV|BWV|D|RV|HWV|H|Wq|Hob|L|S|TrV|WoO)\.?\s*[IVXLC\d][\w:./\-]*",
    re.IGNORECASE,
)
# Spelled out rather than ♭/♯: the elegant serifs (Didot et al.) lack the
# musical-symbol glyphs, and mixing in a fallback font mid-word looks worse.
_FLAT = re.compile(r"\b([A-G])-Flat\b")
_SHARP = re.compile(r"\b([A-G])-Sharp\b")
_MOVEMENT = re.compile(r"^(.*?):\s*([IVXLCDM]+\.\s.*)$")


def parse_title(name: str) -> tuple[str, str]:
    """Split a cumbersome classical title into (work, movement), tidied.

    'String Quartet in E-Flat Major, Op. 58, No. 6, G. 247: III. Allegro ...'
      -> ('String Quartet in E-flat major, Op. 58 No. 6', 'III. Allegro ...')
    """
    m = _MOVEMENT.match(name)
    if m:
        work, movement = m.group(1).strip(), m.group(2).strip()
    else:
        work, movement = name.strip(), ""

    work = _CATALOG.sub("", work)
    work = _FLAT.sub(r"\1-flat", work)
    work = _SHARP.sub(r"\1-sharp", work)
    work = re.sub(r"\bMajor\b", "major", work)
    work = re.sub(r"\bMinor\b", "minor", work)
    work = re.sub(r"(Op\.\s*\d+),\s*(No\.)", r"\1 \2", work)
    work = re.sub(r"\s{2,}", " ", work).strip(" ,")
    return work, movement


# Leading articles that Spotify moves to the end for sort order, e.g.
# "Folies francoises, Les" -> "Les Folies francoises".
_ARTICLES = {"Les", "Le", "La", "L'", "Los", "Las", "Il", "I", "Gli", "Lo",
             "The", "Die", "Der", "Das", "El"}
_INVERTED = re.compile(r"^(.*),\s+([A-Za-z']+)$")


def uninvert_article(name: str) -> str:
    """Restore a sort-inverted artist name to natural order."""
    m = _INVERTED.match(name)
    if m and m.group(2) in _ARTICLES:
        article, rest = m.group(2), m.group(1)
        sep = "" if article.endswith("'") else " "
        return f"{article}{sep}{rest}"
    return name


# --- text measurement / fitting --------------------------------------------

_FONTS: dict[tuple[bool, int], ImageFont.FreeTypeFont] = {}


def _font(size: int, italic: bool) -> ImageFont.FreeTypeFont:
    key = (italic, size)
    if key not in _FONTS:
        path, index = _FONT_FILES[italic]
        _FONTS[key] = ImageFont.truetype(path, size, index=index)
    return _FONTS[key]


def text_width(text: str, size: float, italic: bool = False) -> float:
    return _font(int(size), italic).getlength(text)


def fit_size(text: str, max_w: float, hi: int, lo: int = 30, italic: bool = False) -> int:
    size = hi
    while size > lo and text_width(text, size, italic) > max_w:
        size -= 2
    return size


def ellipsize(text: str, size: int, max_w: float, italic: bool = False) -> str:
    if text_width(text, size, italic) <= max_w:
        return text
    while text and text_width(text + "…", size, italic) > max_w:
        text = text[:-1].rstrip()
    return f"{text}…" if text else "…"


def wrap(text: str, size: int, max_w: float, italic: bool = False) -> list[str]:
    lines: list[str] = []
    cur = ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if not cur or text_width(trial, size, italic) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


# --- art embedding ----------------------------------------------------------

_CAPTION_RE = re.compile(r'<g id="caption">.*?</g>', re.DOTALL)
_METADATA_RE = re.compile(r"<metadata>.*?</metadata>", re.DOTALL)
_SVG_OPEN_RE = re.compile(r"^<svg[^>]*>")


def build_art(doc: dict) -> tuple[str, Palette]:
    """Render the composition caption-free and return (embeddable_svg, palette).

    The art is embedded as a transformed, explicitly-clipped ``<g>`` rather than
    a nested ``<svg>``: cairosvg mishandles nested-svg viewport clipping, which
    let the artwork's background bleed over the text panel below it. The
    transform maps the palette-background field (``bg_square``, i.e. the artwork
    minus its white border) onto the art zone, and the clip keeps it there.
    """
    config = load_config(None)
    data = TrackData.from_cache_doc(doc)
    params = derive(data, config)
    scene = build_scene(data, params, config)
    svg = render_svg(scene, data, config)

    body = _SVG_OPEN_RE.sub("", svg)
    body = body[: body.rfind("</svg>")]
    body = _METADATA_RE.sub("", body)
    body = _CAPTION_RE.sub("", body)

    bg = scene.bg_square  # crop target: palette field, no white border
    zone_h = ART_BOTTOM - ART_TOP
    zone_cy = (ART_TOP + ART_BOTTOM) / 2
    # A square motif fills only ~53% of its field, so enlarge it and let the
    # (canvas-colored, thus invisible) field margins clip. A rect motif reaches
    # the field edges, so it must be fit whole -- no boost.
    boost = SQUARE_MOTIF_BOOST if params.composition == "square" else 1.0
    field = zone_h * boost
    ax = (STORY_W - field) / 2
    ay = zone_cy - field / 2
    s = field / bg.w
    transform = (
        f"translate({ax:.3f},{ay:.3f}) scale({s:.5f}) translate({-bg.x:.3f},{-bg.y:.3f})"
    )
    embed = (
        f'<defs><clipPath id="artclip"><rect x="0" y="{ART_TOP}" '
        f'width="{STORY_W}" height="{zone_h}"/></clipPath></defs>'
        f'<g clip-path="url(#artclip)"><g transform="{transform}">{body}</g></g>'
    )
    return embed, get_palette(params.key)


# --- story composition ------------------------------------------------------


def _text(x: float, y: float, s: str, size: float, fill: str, *, italic: bool = False,
          anchor: str = "start", weight: str = "normal", tracking: float = 0) -> str:
    family = FONT_ITALIC_FAMILY if italic else FONT_FAMILY
    style = ' font-style="italic"' if italic else ""
    track = f' letter-spacing="{tracking}"' if tracking else ""
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="{family}" '
        f'font-size="{size:.0f}" font-weight="{weight}" fill="{fill}"'
        f'{style}{track} text-anchor="{anchor}">{escape(s)}</text>'
    )


def compose_story(doc: dict) -> str:
    track = doc["track"]
    artists = [uninvert_article(a["name"]) for a in track.get("artists", [])]
    composer = artists[0] if artists else ""
    work, movement = parse_title(track["name"])

    art_inner, palette = build_art(doc)
    col = pick_colors(palette)

    usable = STORY_W - 2 * PAD
    parts: list[str] = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{STORY_W}" '
            f'height="{STORY_H}" viewBox="0 0 {STORY_W} {STORY_H}">'
        ),
        f'<rect width="{STORY_W}" height="{STORY_H}" fill="{col["canvas"]}"/>',
        art_inner,
        (
            f'<rect x="0" y="{PANEL_TOP}" width="{STORY_W}" '
            f'height="{STORY_H - PANEL_TOP}" fill="{col["panel"]}"/>'
        ),
    ]

    # accent rule
    y: float = PANEL_TOP + 74
    parts.append(
        f'<rect x="{PAD}" y="{y}" width="120" height="6" fill="{col["composer"]}"/>'
    )

    # composer (kicker + name)
    y += 62
    parts.append(_text(PAD, y, "COMPOSER", 25, col["meta"], tracking=5))
    csize = fit_size(composer, usable, COMPOSER_MAX)
    y += csize + 10
    parts.append(_text(PAD, y, composer, csize, col["composer"]))

    # performer (kicker + name). Classical credits list the ensemble first, then
    # its members; show the full list only if it stays legible, else just the
    # ensemble -- a long roster of individual players would shrink to mush.
    performers = artists[1:]
    if performers:
        y += 60
        parts.append(_text(PAD, y, "PERFORMED BY", 25, col["meta"], tracking=5))
        full = ", ".join(performers)
        psize = fit_size(full, usable, PERFORMER_MAX, italic=True)
        text = full if psize >= 42 else performers[0]
        psize = fit_size(text, usable, PERFORMER_MAX, italic=True)
        text = ellipsize(text, psize, usable, italic=True)
        y += psize + 8
        parts.append(_text(PAD, y, text, psize, col["performer"], italic=True))

    # work + movement
    y += 90
    for line in wrap(work, META_SIZE, usable):
        parts.append(_text(PAD, y, line, META_SIZE, col["meta"]))
        y += META_SIZE * LINE_SPACING
    if movement:
        y += 8
        for line in wrap(movement, META_SIZE - 2, usable, italic=True):
            parts.append(_text(PAD, y, line, META_SIZE - 2, col["meta"], italic=True))
            y += (META_SIZE - 2) * LINE_SPACING

    parts.append("</svg>")
    return "\n".join(parts)


# --- track resolution / CLI -------------------------------------------------

PLAYLIST_ROOT = Path("output/playlists")


def _dir_for_id(track_id: str) -> Path | None:
    """An existing playlist output dir (``NNN-<id>``) for this track, if any."""
    for m in sorted(PLAYLIST_ROOT.glob(f"*/*-{track_id}")):
        if (m / "track.json").exists():
            return m
    return None


def _fetch_live(track_id: str) -> dict:
    """Fetch + cache a track the same way the geomusic CLI does."""
    with SpotifyClient() as client:
        raw_track = client.get_track(track_id)
        try:
            raw_features = client.get_audio_features(track_id)
        except ForbiddenError:
            features = fetch_audio_features([track_id]).get(track_id)
            if features is None:
                raise SystemExit(
                    f"track {track_id} is not in the ReccoBeats dataset and Spotify "
                    "audio-features access is gone (403); cannot render."
                ) from None
            raw_features = complete_features(features, raw_track)
    doc = cache.make_doc(raw_track, raw_features)
    cache.save(track_id, doc)
    return doc


def resolve_doc(arg: str, *, offline: bool) -> tuple[dict, Path]:
    """Resolve a dir / NNN index / URL / URI / id to (track doc, output dir).

    Order: explicit dir → playlist index → (parse to id) existing playlist dir →
    geomusic cache from a prior run → live Spotify/ReccoBeats fetch. Only the
    last step needs network + credentials; ``offline`` disables it.
    """
    p = Path(arg)
    if (p / "track.json").exists():
        return json.loads((p / "track.json").read_text()), p

    if arg.isdigit():
        for m in sorted(PLAYLIST_ROOT.glob(f"*/{int(arg):03d}-*")):
            if (m / "track.json").exists():
                return json.loads((m / "track.json").read_text()), m
        raise SystemExit(f"no track with index {int(arg):03d} in {PLAYLIST_ROOT}")

    try:
        track_id = parse_track_input(arg)
    except InputError as exc:
        raise SystemExit(str(exc)) from None

    existing = _dir_for_id(track_id)
    if existing is not None:
        return json.loads((existing / "track.json").read_text()), existing

    out_dir = Path("output") / track_id
    try:
        doc = cache.load(track_id, offline=True)
    except cache.CacheMissError:
        doc = None
    if doc is not None:
        return doc, out_dir

    if offline:
        raise SystemExit(
            f"No local data for {track_id}. Run `uv run geomusic {track_id}` first, "
            "or drop --offline to fetch it now."
        )
    load_dotenv()
    try:
        return _fetch_live(track_id), out_dir
    except (SpotifyError, ReccoBeatsError) as exc:
        raise SystemExit(f"could not fetch {track_id}: {exc}") from None


def _all_dirs() -> list[Path]:
    return sorted(
        d for d in PLAYLIST_ROOT.glob("*/*") if (d / "track.json").exists()
    )


def render_story(doc: dict, out_dir: Path, out: Path | None) -> Path:
    svg = compose_story(doc)
    out_svg = out.with_suffix(".svg") if out else out_dir / "story.svg"
    out_png = out if out else out_dir / "story.png"
    out_png.parent.mkdir(parents=True, exist_ok=True)
    out_svg.write_text(svg)
    svg_to_png(svg, out_png, width=STORY_W)
    return out_png


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate an Instagram story for a track.")
    ap.add_argument("track", nargs="?", help="track dir, NNN index, URL, URI, or id")
    ap.add_argument("--all", action="store_true", help="render every track in the playlist")
    ap.add_argument("--out", type=Path, help="output PNG path (single track only)")
    ap.add_argument("--offline", action="store_true",
                    help="never fetch; use only local output dirs / geomusic cache")
    args = ap.parse_args()

    if args.all:
        dirs = _all_dirs()
        print(f"rendering {len(dirs)} stories...")
        for d in dirs:
            png = render_story(json.loads((d / "track.json").read_text()), d, None)
            print(f"  {png}")
        return

    if not args.track:
        ap.error("provide a track, or use --all")
    doc, out_dir = resolve_doc(args.track, offline=args.offline)
    png = render_story(doc, out_dir, args.out)
    print(f"wrote {png}")


if __name__ == "__main__":
    main()
