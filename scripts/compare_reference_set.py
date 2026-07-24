"""Compare rendered reference tracks against the source posters.

Emits a ranked report (least similar first) with the metric most likely
responsible, and writes references/processed/comparison-report.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from geomusic.compare import compare_images

MANIFEST = ROOT / "references" / "reference-manifest.json"
RENDERS = ROOT / "references" / "processed" / "renders"
REPORT = ROOT / "references" / "processed" / "comparison-report.json"


def blame(m: dict) -> str:
    """Name the metric family most responsible for a low score."""
    issues = []
    if m["edge_overlap"] < 0.5:
        issues.append("geometry/motif placement")
    if m["palette_histogram_distance"] > 0.8:
        issues.append("color coverage")
    if m["pixel_mismatch"] > 0.5:
        issues.append("large-area mismatch")
    return ", ".join(issues) or "close; residual differences"


def main() -> None:
    entries = json.loads(MANIFEST.read_text())["entries"]
    results = []
    for entry in entries:
        slug = entry["slug"]
        gen = RENDERS / f"{slug}.png"
        ref = ROOT / entry["reference"]
        if not gen.exists() or not ref.exists():
            print(f"{slug:28s} SKIP (missing {'render' if not gen.exists() else 'reference'})")
            continue
        m = compare_images(gen, ref, RENDERS / f"{slug}-diff.png")
        m["slug"] = slug
        results.append(m)

    results.sort(key=lambda m: m["similarity"])
    print(f"\n{'rank':4s} {'slug':28s} {'sim':>6s} {'edges':>6s} {'palette':>8s} {'pixmis':>7s}")
    for i, m in enumerate(results, 1):
        print(
            f"{i:<4d} {m['slug']:28s} {m['similarity']:6.3f} {m['edge_overlap']:6.3f} "
            f"{m['palette_histogram_distance']:8.3f} {m['pixel_mismatch']:7.3f}  {blame(m)}"
        )
    if results:
        agg = sum(m["similarity"] for m in results) / len(results)
        print(f"\naggregate similarity: {agg:.4f}")
        REPORT.write_text(json.dumps({"aggregate": agg, "results": results}, indent=2))
        print(f"wrote {REPORT}")


if __name__ == "__main__":
    main()
