#!/usr/bin/env python3
"""Wait for the private H3 queue, build local packets, and stitch provisional cuts."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ATTEMPTS = [
    ROOT / "runs/sky-village-plumber/attempts/v3",
    ROOT / "runs/luxury-penthouse-tour/attempts/v3",
]


def complete(attempt: Path) -> bool:
    path = attempt / "06-motion/qa/manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return bool(payload.get("all_completed"))


def run(*args: str) -> None:
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)


def main() -> int:
    while not all(complete(attempt) for attempt in ATTEMPTS):
        counts = []
        for attempt in ATTEMPTS:
            payload = json.loads((attempt / "06-motion/qa/manifest.json").read_text(encoding="utf-8"))
            counts.append(f"{attempt.parent.parent.parent.name}:{payload.get('completed_count', 0)}/{payload['job_count']}")
        print("WAIT " + " ".join(counts), flush=True)
        time.sleep(30)
    for attempt in ATTEMPTS:
        run("-m", "ai_video_pipeline.stage6_finish", str(attempt), "--local-preselect")
        run("-m", "ai_video_pipeline.stage6_finish", str(attempt), "--stitch")
    print("LOCAL_PRIVATE_PROVISIONAL_STITCH_COMPLETE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
