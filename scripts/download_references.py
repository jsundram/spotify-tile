#!/usr/bin/env python3
"""Download source images for the Geo-Musical Configurations reimplementation.

This script intentionally keeps a curated manifest of the project-page assets.
Cargo's image host may reject sandboxed or non-browser requests; run this locally.

Usage:
    uv run python scripts/download_references.py
    uv run python scripts/download_references.py --only key final
    uv run python scripts/download_references.py --force
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PAGE_URL = "https://samanthashanne.cargo.site/Geo-Musical-Configurations"


@dataclass(frozen=True)
class Asset:
    category: str
    filename: str
    url: str
    description: str


ASSETS = [
    Asset("data", "Screenshot-of-Excel.png", "https://freight.cargo.site/t/original/i/13c25f68aa2adf3063626b3cd7a9030afbb6f719292c266ba9a55d1fa1e00c06/Screenshot-of-Excel.png", "Parsed Spotify dataset"),
    Asset("mode", "1_mode.png", "https://freight.cargo.site/t/original/i/236972e74eac6b41b6d8a1d443ce73884bf6105e8c61415594fa72b1d77ec3e7/1_mode.png", "Mode mapping overview"),
    Asset("mode", "1_mode_spotify-doc.png", "https://freight.cargo.site/t/original/i/5806d994b8a049654cfbb107d121a4654ce766ae688bab95433ccaaaae551ace/1_mode_spotify-doc.png", "Spotify mode documentation screenshot"),
    Asset("mode", "1_GH-script.png", "https://freight.cargo.site/t/original/i/43561b04a2eacdeca7c7716b06f827239af15f6ebced9926a2b3225372c4cf69/1_GH-script.png", "Grasshopper mode script"),
    Asset("mode", "Holocene.jpg", "https://freight.cargo.site/t/original/i/591e23bc898c8afb1217d751b2fa16f43a79addf71904233adb46c58f58e424c/Holocene.jpg", "Holocene square-composition example"),
    Asset("mode", "Bohemian-Rhapsody.jpg", "https://freight.cargo.site/t/original/i/7c405590e6f840550850ab39be06393a3d3f0b2d678adfc5050c3ce095635812/Bohemian-Rhapsody.jpg", "Bohemian Rhapsody rectangular-composition example"),
    Asset("track-id", "2_track-id.png", "https://freight.cargo.site/t/original/i/c050efc6ac51f06185d5220fb16f4221f585a344494f7ad302e0fa5dd99a18db/2_track-id.png", "Track-ID mapping overview"),
    Asset("track-id", "2_gh-script.png", "https://freight.cargo.site/t/original/i/f28d880f8bc19e2e15f9f7934b1be0557bde5d3e7820d48fe242d3dc68cffa6e/2_gh-script.png", "Grasshopper/Python track-ID script"),
    Asset("track-id", "2_square-subdivisions.png", "https://freight.cargo.site/t/original/i/837830ec2589d1904f6db0c2bf03ed40a7a9834c19e1a4b5f2e6121c6076d02d/2_square-subdivisions.png", "Quad subdivision diagram"),
    Asset("track-id", "The-Adults-are-Talking.jpg", "https://freight.cargo.site/t/original/i/0cd680e7aa2070197d958d6728d425136b97a6ca555eb81d8dbd30be9b922706/The-Adults-are-Talking.jpg", "Seven-subdivision example"),
    Asset("track-id", "Sunset-The-xx.jpg", "https://freight.cargo.site/t/original/i/f578327380138f0245a5797511c2067bba8f1a73ffc2047c5ac949760da492bf/Sunset-The-xx.jpg", "Thirteen-subdivision example"),
    Asset("scaling", "3_loudness_spotify-doc-a.png", "https://freight.cargo.site/t/original/i/559d2cb215fe8928f81d4b78c02b2fe00bf56cfb235b5cb998dec21c07268ff2/3_loudness_spotify-doc.png", "Loudness documentation screenshot"),
    Asset("scaling", "3_loudness_spotify-doc-b.png", "https://freight.cargo.site/t/original/i/0cf4055948ff7a382f3e09a3cd4fe34ae33f33e97fa997e7cb59b3394874c28d/3_loudness_spotify-doc.png", "Tempo/documentation screenshot (source filename duplicated)"),
    Asset("scaling", "3_gh-script.png", "https://freight.cargo.site/t/original/i/8365e69ed6bd7e9de2af90e2d22aacde9a4d2ac3d67c16bbf5053c5712870a41/3_gh-script.png", "Grasshopper scaling script"),
    Asset("instrumentalness", "3_instrumentalness_spotify-doc.png", "https://freight.cargo.site/t/original/i/eff43b5450cd2948e590bb9d481834f5368af30f0a790bd667091e0715fb8677/3_instrumentalness_spotify-doc.png", "Instrumentalness documentation screenshot"),
    Asset("instrumentalness", "3_gh-script2.png", "https://freight.cargo.site/t/original/i/bde8aa24eed644a3a142774e5fae00a28e695c6b6316b20da873a72f48058066/3_gh-script2.png", "Grasshopper instrumentalness script"),
    Asset("key", "4_key.png", "https://freight.cargo.site/t/original/i/2bc9df67e6d6f6072a7c526f574f79b43d8cff847878153dbd015684dfc5750b/4_key.png", "Key mapping overview"),
    Asset("key", "pitch-class-wikipedia.png", "https://freight.cargo.site/t/original/i/e9b7f8cb4f57a5c1f9ee133227318e48685f38bfab179a99a5130bfc3a1e8d4d/pitch-class-wikipedia.png", "Pitch-class reference"),
    Asset("key", "4_key_spotify-doc.png", "https://freight.cargo.site/t/original/i/01eec51e5c198a8ca2885cc4ee3f14204a281538b28f1f2542dfb99aeb9bf3bf/4_key_spotify-doc.png", "Spotify key documentation screenshot"),
    Asset("key", "4_key_script.png", "https://freight.cargo.site/t/original/i/bdb4c4671347e91eeca6ca79ba4c4928b80a59344a4d8575a552cf53ef74c2cf/4_key_script.png", "Grasshopper palette definitions"),
    Asset("final", "Lover-You-Should-ve-Come-Over_annotated.jpg", "https://freight.cargo.site/t/original/i/b69d6036b99c9130ae5057934cfe74f406a67646d3f3b61086c761152ea39614/Lover-You-Should-ve-Come-Over_annotated.jpg", "Final reference output: Lover, You Should've Come Over"),
    Asset("final", "Real-Love-Baby_annotated.jpg", "https://freight.cargo.site/t/original/i/6bb473c362f87fee4e783857e95d5de67bb7c160e17b66322827186856ab3735/Real-Love-Baby_annoatated.jpg", "Final reference output: Real Love Baby"),
    Asset("final", "Judas_annotated.jpg", "https://freight.cargo.site/t/original/i/0a39b9a36d41c032bf1ecc2048bf6994020aaa9a53a1f94f658af690e8ebdac0/Judas_annoated.jpg", "Final reference output: Judas"),
    Asset("final", "Vienna_annotated.jpg", "https://freight.cargo.site/t/original/i/a81cddd377fc635c8f4d22245de3810456234bc9cc41a71f9dd5824dc04f69a9/Vienna_annotated.jpg", "Final reference output: Vienna"),
    Asset("final", "exhibition-board.jpg", "https://freight.cargo.site/t/original/i/92dc54fe369043045bd58d988413d96f93b51eb04c7259d6193382709afd685e/Pages-from-Boards_Exhibition_Separate-for-Drive-01.jpg", "Exhibition board with multiple outputs"),
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(asset: Asset, destination: Path, force: bool) -> dict[str, object]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not force:
        return {"status": "existing", "size": destination.stat().st_size, "sha256": sha256(destination)}

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126 Safari/537.36",
        "Referer": PAGE_URL,
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    }
    request = Request(asset.url, headers=headers)
    temporary = destination.with_suffix(destination.suffix + ".part")
    try:
        with urlopen(request, timeout=60) as response, temporary.open("wb") as output:
            content_type = response.headers.get("Content-Type", "")
            if not content_type.startswith("image/"):
                raise RuntimeError(f"unexpected content type: {content_type!r}")
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        temporary.replace(destination)
        return {"status": "downloaded", "size": destination.stat().st_size, "sha256": sha256(destination)}
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("references/source"))
    parser.add_argument("--only", nargs="*", help="Categories to download, e.g. key final track-id")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--delay", type=float, default=0.25, help="Delay between requests")
    args = parser.parse_args()

    selected = [a for a in ASSETS if not args.only or a.category in set(args.only)]
    if not selected:
        categories = sorted({a.category for a in ASSETS})
        parser.error(f"no assets matched; valid categories: {', '.join(categories)}")

    records: list[dict[str, object]] = []
    failures = 0
    for asset in selected:
        destination = args.output / asset.category / asset.filename
        print(f"{asset.category:16} {destination}")
        record = {**asdict(asset), "path": str(destination)}
        if args.dry_run:
            record["status"] = "dry-run"
        else:
            try:
                record.update(download(asset, destination, args.force))
                print(f"  -> {record['status']} ({record['size']} bytes)")
            except (HTTPError, URLError, RuntimeError, OSError) as error:
                failures += 1
                record.update(status="failed", error=str(error))
                print(f"  !! {error}", file=sys.stderr)
            time.sleep(max(args.delay, 0))
        records.append(record)

    args.output.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output / "download-manifest.json"
    manifest_path.write_text(json.dumps({"source_page": PAGE_URL, "assets": records}, indent=2) + "\n")
    print(f"Manifest: {manifest_path}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
