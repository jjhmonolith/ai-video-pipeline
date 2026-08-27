#!/usr/bin/env python3
"""Render pending Stage 06 jobs on multiple ComfyUI servers without manifest races."""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from pathlib import Path

from ai_video_pipeline.contract import load as load_contract
from ai_video_pipeline.stage6 import _render_job


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _render_with_retries(attempt: Path, job: dict, server: str, timeout: float) -> dict:
    last_error: Exception | None = None
    for runtime_attempt in range(1, 11):
        try:
            print(
                f"START {job['job_id']} server={server} runtime-attempt={runtime_attempt}",
                flush=True,
            )
            completed = _render_job(attempt, job, server, timeout)
            elapsed = (completed.get("generation") or {}).get("elapsed_seconds")
            print(f"DONE {job['job_id']} elapsed={elapsed}s", flush=True)
            return completed
        except Exception as error:  # runtime/network failures share the ten-attempt budget
            last_error = error
            print(
                f"RETRY {job['job_id']} runtime-attempt={runtime_attempt} "
                f"error={type(error).__name__}: {str(error)[:300]}",
                flush=True,
            )
            if runtime_attempt < 10:
                time.sleep(min(30, runtime_attempt * 3))
    assert last_error is not None
    raise last_error


def _refresh_progress(manifest: dict) -> None:
    manifest["job_count"] = len(manifest["jobs"])
    manifest["completed_count"] = sum(
        job.get("status") == "completed" for job in manifest["jobs"]
    )
    manifest["all_completed"] = manifest["completed_count"] == manifest["job_count"]
    manifest["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _collapse_to_one_pending_candidate_per_shot(manifest: dict) -> list[str]:
    """Keep finished work, but retain only C01 for every unfinished shot."""
    completed_shots = {
        str(job["shot_id"])
        for job in manifest["jobs"]
        if job.get("status") == "completed"
    }
    kept: list[dict] = []
    pending_kept: set[str] = set()
    removed: list[str] = []
    for job in manifest["jobs"]:
        shot_id = str(job["shot_id"])
        if job.get("status") == "completed":
            kept.append(job)
        elif shot_id not in completed_shots and shot_id not in pending_kept:
            kept.append(job)
            pending_kept.add(shot_id)
        else:
            removed.append(str(job["job_id"]))
    manifest["jobs"] = kept
    _refresh_progress(manifest)
    return removed


def render_pending(
    attempt: Path,
    servers: list[str],
    timeout: float,
    one_per_unfinished_shot: bool = False,
) -> None:
    attempt = attempt.resolve()
    contract = load_contract(attempt)
    motion_stage = contract.stage_for("motion", "06-motion")
    manifest_path = attempt / motion_stage / "qa" / "manifest.json"
    receipt_path = attempt / motion_stage / "receipt.json"

    manifest = _load(manifest_path)
    if one_per_unfinished_shot:
        removed = _collapse_to_one_pending_candidate_per_shot(manifest)
        _save(manifest_path, manifest)
        _save(receipt_path, manifest)
        print(f"COLLAPSED removed={len(removed)} job_count={manifest['job_count']}", flush=True)

    pending = [job for job in manifest["jobs"] if job.get("status") != "completed"]
    if not pending:
        print("ALL_STAGE6_JOBS_COMPLETED", flush=True)
        return

    with ThreadPoolExecutor(max_workers=min(len(servers), len(pending))) as pool:
        futures: dict[Future, str] = {}

        def submit_next(server: str) -> None:
            if pending:
                job = pending.pop(0)
                future = pool.submit(_render_with_retries, attempt, job, server, timeout)
                futures[future] = server

        for server in servers:
            submit_next(server)

        while futures:
            finished, _ = wait(set(futures), return_when=FIRST_COMPLETED)
            for future in finished:
                server = futures.pop(future)
                completed = future.result()
                for index, job in enumerate(manifest["jobs"]):
                    if str(job.get("job_id")) == str(completed["job_id"]):
                        manifest["jobs"][index] = completed
                        break
                _refresh_progress(manifest)
                _save(manifest_path, manifest)
                _save(receipt_path, manifest)
                print(
                    f"PROGRESS {manifest['completed_count']}/{manifest['job_count']}",
                    flush=True,
                )
                submit_next(server)

    print("ALL_STAGE6_JOBS_COMPLETED", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("attempt", type=Path)
    parser.add_argument("--server", action="append", required=True)
    parser.add_argument("--timeout", type=float, default=7200.0)
    parser.add_argument("--one-per-unfinished-shot", action="store_true")
    args = parser.parse_args()
    render_pending(
        args.attempt,
        args.server,
        args.timeout,
        one_per_unfinished_shot=args.one_per_unfinished_shot,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
