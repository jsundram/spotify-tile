"""Image comparison metrics for visual regression against reference posters."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter

ANALYSIS_SIZE = 600  # comparisons run on downscaled copies for speed


def _load_pair(generated: Path, reference: Path) -> tuple[Image.Image, Image.Image]:
    gen = Image.open(generated).convert("RGB")
    ref = Image.open(reference).convert("RGB")
    if gen.size != ref.size:
        gen = gen.resize(ref.size, Image.Resampling.LANCZOS)
    scale = ANALYSIS_SIZE / max(ref.size)
    size = (round(ref.width * scale), round(ref.height * scale))
    return gen.resize(size, Image.Resampling.LANCZOS), ref.resize(size, Image.Resampling.LANCZOS)


def pixel_mismatch(gen: Image.Image, ref: Image.Image, threshold: int = 40) -> float:
    """Fraction of pixels whose max channel delta exceeds ``threshold``."""
    diff = ImageChops.difference(gen, ref).convert("L")
    hist = diff.histogram()
    total = sum(hist)
    return sum(hist[threshold:]) / total if total else 1.0


def mean_abs_error(gen: Image.Image, ref: Image.Image) -> float:
    diff = ImageChops.difference(gen, ref)
    hist = diff.histogram()
    total = gen.width * gen.height * 3
    err = 0
    for ch in range(3):
        for v, n in enumerate(hist[ch * 256 : (ch + 1) * 256]):
            err += v * n
    return err / total if total else 255.0


def palette_histogram_distance(gen: Image.Image, ref: Image.Image, bins: int = 4) -> float:
    """L1 distance between coarse 3D color histograms (0..2)."""

    def hist3d(img: Image.Image) -> list[float]:
        counts = [0] * (bins**3)
        step = 256 // bins
        raw = img.tobytes()
        for i in range(0, len(raw), 3):
            counts[
                (raw[i] // step) * bins * bins + (raw[i + 1] // step) * bins + (raw[i + 2] // step)
            ] += 1
        n = img.width * img.height
        return [c / n for c in counts]

    hg, hr = hist3d(gen), hist3d(ref)
    return sum(abs(a - b) for a, b in zip(hg, hr))


def edge_overlap(gen: Image.Image, ref: Image.Image, threshold: int = 40) -> float:
    """IoU of binarized edge maps (geometry agreement, 0..1)."""

    def edges(img: Image.Image) -> list[bool]:
        e = img.convert("L").filter(ImageFilter.FIND_EDGES)
        e = e.filter(ImageFilter.MaxFilter(3))
        return [v >= threshold for v in e.tobytes()]

    eg, er = edges(gen), edges(ref)
    inter = sum(1 for a, b in zip(eg, er) if a and b)
    union = sum(1 for a, b in zip(eg, er) if a or b)
    return inter / union if union else 1.0


def compare_images(generated: Path, reference: Path, diff_out: Path | None = None) -> dict:
    gen, ref = _load_pair(Path(generated), Path(reference))
    mismatch = pixel_mismatch(gen, ref)
    mae = mean_abs_error(gen, ref)
    hist_dist = palette_histogram_distance(gen, ref)
    edges = edge_overlap(gen, ref)
    # Composite similarity in [0, 1]: weighted blend of the four metrics.
    similarity = (
        0.35 * (1 - mismatch)
        + 0.20 * (1 - min(1.0, mae / 128))
        + 0.20 * (1 - hist_dist / 2)
        + 0.25 * edges
    )
    metrics: dict = {
        "reference": str(reference),
        "generated": str(generated),
        "pixel_mismatch": round(mismatch, 4),
        "mean_abs_rgb_error": round(mae, 2),
        "palette_histogram_distance": round(hist_dist, 4),
        "edge_overlap": round(edges, 4),
        "similarity": round(similarity, 4),
    }
    if diff_out is not None:
        diff = ImageChops.difference(gen, ref)
        diff.save(diff_out)
    return metrics


def write_comparison(generated: Path, reference: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    metrics = compare_images(generated, reference, out_dir / "comparison-diff.png")
    (out_dir / "comparison.json").write_text(json.dumps(metrics, indent=2))
    return metrics
