"""Apply an explicit user-directed one-take-per-shot policy to a live manifest."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .contract import load as load_contract
from .stage6 import SCHEMA, TERMINAL_JOB_STATUSES


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def apply(attempt: Path, start_shot: str) -> dict:
    attempt = attempt.resolve()
    contract = load_contract(attempt)
    stage = contract.stage_for("motion", "06-motion")
    path = attempt / stage / "qa" / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != SCHEMA:
        raise RuntimeError("unsupported Stage 06 manifest")
    skipped = []
    preserved = []
    for job in manifest.get("jobs", []):
        shot_id = str(job.get("shot_id") or "")
        number = int(job.get("candidate_number") or 0)
        if shot_id >= start_shot and number > 1 and job.get("status") != "completed":
            job["status"] = "skipped_by_user_single_take"
            job["skipped_at"] = _now()
            job["skip_reason"] = (
                f"Explicit user direction: from {start_shot}, generate one video per shot and stitch directly."
            )
            skipped.append(job["job_id"])
        elif job.get("status") == "completed":
            preserved.append(job["job_id"])
    manifest["single_take_policy"] = {
        "schema_version": "stage6-single-take-policy.v1",
        "applied_at": _now(), "set_by": "user", "start_shot": start_shot,
        "keep_candidate_number": 1,
        "direction": "Generate no candidate variants from the next scene; make one video per shot and stitch directly.",
    }
    manifest["completed_count"] = sum(j.get("status") == "completed" for j in manifest["jobs"])
    manifest["skipped_count"] = sum(j.get("status") == "skipped_by_user_single_take" for j in manifest["jobs"])
    manifest["terminal_count"] = sum(j.get("status") in TERMINAL_JOB_STATUSES for j in manifest["jobs"])
    manifest["all_completed"] = manifest["terminal_count"] == manifest["job_count"]
    manifest["updated_at"] = _now()
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "attempt": str(attempt), "start_shot": start_shot,
        "preserved_completed": len(preserved), "skipped_jobs": len(skipped),
        "remaining_renders": manifest["job_count"] - manifest["terminal_count"],
        "manifest": str(path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("attempt", type=Path)
    parser.add_argument("--start-shot", required=True)
    args = parser.parse_args()
    print(json.dumps(apply(args.attempt, args.start_shot), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
