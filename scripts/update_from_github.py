#!/usr/bin/env python3
"""Safely fast-forward an existing Git checkout of AI Video Pipeline v3."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FOCUSED_TESTS = (
    "tests.test_portable_package",
    "tests.test_v3_integrity",
    "tests.test_v3_orchestrator",
    "tests.test_v3_end_to_end",
)


class UpdateError(RuntimeError):
    pass


def _git(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise UpdateError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout.strip()


def _require_clean_checkout() -> tuple[str, str]:
    if shutil.which("git") is None:
        raise UpdateError("git is not installed or is not on PATH")
    if not (ROOT / ".git").exists():
        raise UpdateError(
            "this folder is not a Git checkout; download a newer release or clone the repository"
        )
    dirty = _git("status", "--porcelain", "--untracked-files=normal")
    if dirty:
        raise UpdateError(
            "tracked or untracked source changes are present; commit, stash, or move them before updating"
        )
    branch = _git("branch", "--show-current")
    if not branch:
        raise UpdateError("detached HEAD is not updateable; switch to a branch first")
    upstream = _git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    return branch, upstream


def _verify() -> None:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = str(ROOT / "src")
    command = [sys.executable, "-m", "unittest", *FOCUSED_TESTS, "-v"]
    result = subprocess.run(command, cwd=ROOT, env=environment, check=False)
    if result.returncode:
        raise UpdateError("the update completed, but focused v3 verification failed")


def _sync() -> None:
    uv = shutil.which("uv")
    if uv is None:
        raise UpdateError("--sync was requested, but uv is not installed")
    result = subprocess.run([uv, "sync", "--frozen"], cwd=ROOT, check=False)
    if result.returncode:
        raise UpdateError("the source updated, but dependency synchronization failed")


def update(*, check_only: bool, sync: bool, verify: bool) -> int:
    branch, upstream = _require_clean_checkout()
    old_commit = _git("rev-parse", "HEAD")
    _git("fetch", "--prune", "origin")
    counts = _git("rev-list", "--left-right", "--count", f"HEAD...{upstream}").split()
    if len(counts) != 2:
        raise UpdateError("could not determine local and remote revision counts")
    ahead, behind = (int(value) for value in counts)
    print(f"branch={branch} upstream={upstream} ahead={ahead} behind={behind}")
    if ahead:
        raise UpdateError(
            "the local branch contains commits not present upstream; review and push or rebase them manually"
        )
    if not behind:
        print(f"already up to date at {old_commit[:12]}")
        return 0
    if check_only:
        print(f"update available: {behind} commit(s)")
        return 0
    _git("merge", "--ff-only", upstream)
    new_commit = _git("rev-parse", "HEAD")
    print(f"updated {old_commit[:12]} -> {new_commit[:12]}")
    if sync:
        _sync()
    if verify:
        _verify()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Safely update a clean AI Video Pipeline Git checkout"
    )
    parser.add_argument("--check", action="store_true", help="fetch and report without updating")
    parser.add_argument("--sync", action="store_true", help="run uv sync --frozen after updating")
    parser.add_argument(
        "--no-verify", action="store_true", help="skip focused v3 tests after updating"
    )
    args = parser.parse_args()
    try:
        return update(check_only=args.check, sync=args.sync, verify=not args.no_verify)
    except UpdateError as error:
        print(f"update blocked: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
