"""Check what the model actually produced, not just what it was told to produce.

v1 passed every card-level gate and still shipped a frame with large invented
Korean lettering burned into the photograph, next to the deterministic caption
that was supposed to be the only text on screen. The card said no readable
text. The prompt said no readable text. Nobody looked at the output.

So this gate reads frames. It cannot read Korean, and it does not try: it looks
for the geometric signature of rendered lettering, which is a horizontal band
of many small high-contrast connected marks sharing a baseline. That catches
signage, wordmarks and hallucinated captions without needing OCR.

It reports suspicion, not certainty. A dashboard of switches or a grille can
trip it. The output is a ranked list to look at, and the reviewer decides.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

SAMPLES_PER_CLIP = 6
MIN_MARKS = 8           # 한 줄에 이만큼 이상의 표시가 늘어서면 글자로 의심한다
BAND_HEIGHT = 22        # 검사할 가로 띠의 높이, 축소 프레임 기준
MARK_MIN, MARK_MAX = 2, 30   # 글자 획 하나의 폭 범위


def sample_frames(clip: Path, out_dir: Path, count: int) -> list[Path]:
    duration = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(clip)], check=True, capture_output=True, text=True).stdout)
    paths = []
    for index in range(count):
        at = duration * (index + 0.5) / count
        target = out_dir / f"{clip.stem}_{index}.png"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{at:.3f}",
                        "-i", str(clip), "-vframes", "1", str(target)], check=True)
        paths.append(target)
    return paths


def text_score(image_path: Path) -> dict:
    """Highest count of small, evenly-spaced high-contrast marks on one baseline."""
    image = Image.open(image_path).convert("L")
    scale = 720 / image.width
    small = image.resize((720, int(image.height * scale)), Image.LANCZOS)
    array = np.asarray(small, dtype=np.float64)

    # Local contrast: a stroke is a step against its immediate surroundings.
    gradient = np.abs(np.diff(array, axis=1))
    threshold = max(28.0, float(np.percentile(gradient, 99.2)))
    edges = gradient > threshold

    best = {"marks": 0, "row": None}
    height = edges.shape[0]
    for top in range(0, height - BAND_HEIGHT, BAND_HEIGHT // 2):
        band = edges[top:top + BAND_HEIGHT]
        columns = np.where(band.sum(axis=0) >= 2)[0]
        if len(columns) < MIN_MARKS:
            continue
        gaps = np.diff(columns)
        runs, current = [], 1
        for gap in gaps:
            if gap <= 2:
                current += 1
            else:
                runs.append((current, gap))
                current = 1
        runs.append((current, 0))
        marks = [width for width, _ in runs if MARK_MIN <= width <= MARK_MAX]
        if len(marks) > best["marks"]:
            best = {"marks": len(marks), "row": int(top / scale)}
    return best


def check_clip(clip: Path, threshold: int) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        frames = sample_frames(clip, Path(tmp), SAMPLES_PER_CLIP)
        scores = [text_score(frame) for frame in frames]
    worst = max(scores, key=lambda s: s["marks"])
    return {
        "clip": clip.name,
        "max_marks_in_a_row": worst["marks"],
        "at_row": worst["row"],
        "suspected_text": worst["marks"] >= threshold,
        "per_sample": [s["marks"] for s in scores],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="생성 프레임의 문자 의심 검출")
    parser.add_argument("--clips", type=Path, required=True)
    parser.add_argument("--pattern", default="*.mp4")
    parser.add_argument("--threshold", type=int, default=26)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    clips = sorted(args.clips.glob(args.pattern))
    if not clips:
        raise SystemExit(f"클립 없음: {args.clips}/{args.pattern}")

    results = [check_clip(clip, args.threshold) for clip in clips]
    flagged = [r for r in results if r["suspected_text"]]
    report = {
        "threshold": args.threshold,
        "clips": len(results),
        "flagged": [r["clip"] for r in flagged],
        "note": "확정이 아니라 의심이다. 계기판이나 그릴도 걸린다. 사람이 확인한다",
        "ranked": sorted(results, key=lambda r: -r["max_marks_in_a_row"]),
        "ok": not flagged,
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
