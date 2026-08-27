#!/usr/bin/env python3
"""Resume both v3 Stage 06 attempts, AI-review, retry defects, and stitch."""

from __future__ import annotations

import json
import argparse
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ATTEMPTS = [
    ROOT / "runs/sky-village-plumber/attempts/v3",
    ROOT / "runs/luxury-penthouse-tour/attempts/v3",
]
SERVER = "http://127.0.0.1:18188"


def run(*args: str) -> None:
    command = [sys.executable, *args]
    subprocess.run(command, cwd=ROOT, check=True)


def render_pending(attempt: Path) -> None:
    manifest_path = attempt / "06-motion/qa/manifest.json"
    while True:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        pending = [job for job in manifest["jobs"]
                   if job.get("status") not in {"completed", "skipped_by_user_single_take"}]
        if not pending:
            return
        for job in pending:
            last_error = None
            for runtime_attempt in range(1, 11):
                try:
                    print(f"RENDER {attempt.name} {job['job_id']} runtime-attempt={runtime_attempt}", flush=True)
                    run("-m", "ai_video_pipeline.stage6", str(attempt), "--render", "--shot", job["shot_id"],
                        "--candidate", str(job["candidate_number"]), "--server", SERVER, "--timeout", "7200")
                    last_error = None
                    break
                except subprocess.CalledProcessError as error:
                    last_error = error
                    time.sleep(min(30, runtime_attempt * 3))
            if last_error is not None:
                raise last_error


def finish(attempt: Path) -> None:
    while True:
        render_pending(attempt)
        run("-m", "ai_video_pipeline.stage6_finish", str(attempt), "--review")
        selection = json.loads((attempt / "06-motion/qa/ai-fast-track/selection.json").read_text(encoding="utf-8"))
        if selection.get("all_selected"):
            break
        run("-m", "ai_video_pipeline.stage6_finish", str(attempt), "--append-retries")
    run("-m", "ai_video_pipeline.stage6_finish", str(attempt), "--stitch")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--render-only", action="store_true",
                        help="finish the H3 queue without sending review frames to any API")
    args = parser.parse_args()
    for attempt in ATTEMPTS:
        if args.render_only:
            render_pending(attempt)
        else:
            finish(attempt)
    print("FAST_TRACK_STAGE6_RENDER_COMPLETE" if args.render_only
          else "FAST_TRACK_STAGE6_AND_STITCH_COMPLETE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
