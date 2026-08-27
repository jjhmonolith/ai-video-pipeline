"""Measure whether a recurring subject stays the same subject across cuts.

Identity drift is the failure a character sheet exists to prevent, and it is
the one thing eye judgement is worst at: two frames of a similar-looking person
in different light read as the same person until they are side by side.

This does not recognise faces. It compares colour and texture statistics of a
fixed region across the frames that are meant to hold the same subject, which
is enough to rank one version against another. It answers "did v2 hold the
subject better than v1", not "is this the same person".

Because it is relative, only compare runs of the same shot list. An absolute
score means nothing on its own.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

REGIONS = {
    # (x0, y0, x1, y1) as fractions of the frame
    "upper": (0.20, 0.10, 0.80, 0.55),
    "full": (0.0, 0.0, 1.0, 1.0),
}
BINS = 12


def frame_at(clip: Path, seconds: float, target: Path) -> Path:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{seconds}",
                    "-i", str(clip), "-vframes", "1", str(target)], check=True)
    return target


def signature(image_path: Path, region: str) -> np.ndarray:
    image = Image.open(image_path).convert("RGB")
    width, height = image.size
    x0, y0, x1, y1 = REGIONS[region]
    crop = image.crop((int(x0 * width), int(y0 * height), int(x1 * width), int(y1 * height)))
    array = np.asarray(crop, dtype=np.float64)

    parts = []
    for channel in range(3):
        histogram, _ = np.histogram(array[:, :, channel], bins=BINS, range=(0, 255))
        parts.append(histogram / max(histogram.sum(), 1))
    grey = array.mean(axis=2)
    gx = np.abs(np.diff(grey, axis=1)).mean()
    gy = np.abs(np.diff(grey, axis=0)).mean()
    parts.append(np.array([gx / 255, gy / 255]))
    return np.concatenate(parts)


def distance(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.abs(a - b).sum())


def measure(clips: dict[str, Path], region: str, at: float) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        signatures = {}
        for shot, clip in clips.items():
            frame = frame_at(clip, at, Path(tmp) / f"{shot}.png")
            signatures[shot] = signature(frame, region)

        shots = sorted(signatures)
        pairs = []
        for index, left in enumerate(shots):
            for right in shots[index + 1:]:
                pairs.append({"pair": f"{left}-{right}",
                              "distance": round(distance(signatures[left], signatures[right]), 4)})

    values = [p["distance"] for p in pairs] or [0.0]
    return {
        "region": region, "sampled_at_seconds": at, "shots": shots,
        "pair_count": len(pairs),
        "mean_distance": round(float(np.mean(values)), 4),
        "max_distance": round(float(np.max(values)), 4),
        "worst_pair": max(pairs, key=lambda p: p["distance"])["pair"] if pairs else None,
        "pairs": sorted(pairs, key=lambda p: -p["distance"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="컷 사이 피사체 일관성 측정")
    parser.add_argument("--clips", type=Path, required=True)
    parser.add_argument("--shots", nargs="+", required=True)
    parser.add_argument("--region", default="upper", choices=sorted(REGIONS))
    parser.add_argument("--at", type=float, default=1.0)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    clips = {}
    for shot in args.shots:
        matches = sorted(args.clips.glob(f"{shot}_*.mp4"))
        if not matches:
            raise SystemExit(f"{shot} 클립 없음")
        clips[shot] = matches[0]

    report = measure(clips, args.region, args.at)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
