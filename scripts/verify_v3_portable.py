#!/usr/bin/env python3
"""Verify a copied v3 source bundle and its local execution prerequisites."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import shutil
import sys
from pathlib import Path


EXPECTED_STAGES = [
    "01-premise",
    "02-sheet",
    "03-scenario",
    "04-shot-design",
    "05-plate",
    "05.5-motion-prompt",
    "06-motion",
    "07-edit",
    "08-review",
]

EXPECTED_SKILLS = [
    "video-pipeline-orchestrator",
    "video-pipeline-recovery",
    "video-stage01-premise",
    "video-stage02-sheets",
    "video-stage03-scenario",
    "video-stage04-shot-design",
    "video-stage05-plates",
    "video-stage05b-motion-prompt",
    "video-stage06-motion",
    "video-stage07-edit",
    "video-stage08-review",
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_check(root: Path) -> tuple[list[dict], list[dict]]:
    problems: list[dict] = []
    checks: list[dict] = []
    path = root / "PORTABLE_MANIFEST.json"
    if not path.is_file():
        return ([{"check": "manifest", "message": "PORTABLE_MANIFEST.json is missing"}], checks)
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return ([{"check": "manifest", "message": f"manifest is unreadable: {error}"}], checks)
    records = manifest.get("files")
    if not isinstance(records, list):
        return ([{"check": "manifest", "message": "manifest files must be a list"}], checks)
    declared: set[str] = set()
    expected_checksums: list[str] = []
    matched_count = 0
    for record in records:
        if not isinstance(record, dict):
            problems.append({"check": "manifest-record", "message": "file record must be an object"})
            continue
        relative = record.get("path")
        if not isinstance(relative, str) or not relative:
            problems.append({"check": "manifest-path", "message": "file path must be a non-empty string"})
            continue
        if relative in declared:
            problems.append({"check": "manifest-path", "message": f"duplicate path: {relative}"})
            continue
        declared.add(relative)
        candidate = (root / str(relative or "")).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            problems.append({"check": "manifest-path", "message": f"path escapes bundle: {relative}"})
            continue
        if not candidate.is_file():
            problems.append({"check": "manifest-file", "message": f"missing: {relative}"})
            continue
        actual = _sha256(candidate)
        if actual != record.get("sha256"):
            problems.append({"check": "manifest-hash", "message": f"hash mismatch: {relative}"})
        else:
            matched_count += 1
        expected_checksums.append(f"{record.get('sha256')}  {relative}")

    actual_files = {
        item.relative_to(root).as_posix()
        for item in root.rglob("*")
        if item.is_file() and item.name not in {"PORTABLE_MANIFEST.json", "MANIFEST.sha256"}
    }
    for relative in sorted(actual_files - declared):
        problems.append({"check": "manifest-extra", "message": f"undeclared file: {relative}"})
    checksum_path = root / "MANIFEST.sha256"
    if not checksum_path.is_file():
        problems.append({"check": "checksums", "message": "MANIFEST.sha256 is missing"})
    else:
        actual_checksums = checksum_path.read_text(encoding="utf-8").splitlines()
        if actual_checksums != expected_checksums:
            problems.append({"check": "checksums", "message": "MANIFEST.sha256 does not match manifest"})
        else:
            checks.append({"check": "checksums", "status": "pass"})
    if matched_count:
        checks.append({"check": "manifest-files", "status": "pass", "count": matched_count})
    return problems, checks


def verify(root: Path, *, manifest_only: bool = False) -> dict:
    root = root.resolve()
    problems, checks = _manifest_check(root)
    warnings: list[dict] = []
    if manifest_only:
        return {"ok": not problems, "root": str(root), "checks": checks,
                "warnings": warnings, "problems": problems}

    if sys.version_info < (3, 9):
        problems.append({"check": "python", "message": "Python 3.9 or newer is required"})
    else:
        checks.append({"check": "python", "status": "pass", "version": sys.version.split()[0]})

    for relative in ("AGENTS.md", "pyproject.toml", "src/ai_video_pipeline/v3/specs.py"):
        if not (root / relative).is_file():
            problems.append({"check": "project-file", "message": f"missing: {relative}"})

    for skill in EXPECTED_SKILLS:
        path = root / ".agents" / "skills" / skill / "SKILL.md"
        if path.is_file():
            checks.append({"check": "skill", "status": "pass", "skill": skill})
        else:
            problems.append({"check": "skill", "message": f"missing skill: {skill}"})

    source = root / "src"
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))
    try:
        specs = importlib.import_module("ai_video_pipeline.v3.specs")
        actual_stages = [item["id"] for item in specs.STAGES]
        if actual_stages != EXPECTED_STAGES:
            problems.append({"check": "stage-order", "message":
                             f"expected {EXPECTED_STAGES}, got {actual_stages}"})
        else:
            checks.append({"check": "stage-order", "status": "pass", "stages": actual_stages})
    except Exception as error:
        problems.append({"check": "pipeline-import", "message": str(error)})

    for module in ("PIL", "openai", "keyring"):
        try:
            imported = importlib.import_module(module)
            checks.append({"check": "python-package", "status": "pass", "package": module,
                           "version": str(getattr(imported, "__version__", "installed"))})
        except Exception as error:
            problems.append({"check": "python-package", "message": f"{module}: {error}"})

    for executable in ("ffmpeg", "ffprobe"):
        resolved = shutil.which(executable)
        if resolved:
            checks.append({"check": "executable", "status": "pass",
                           "name": executable, "path": resolved})
        else:
            problems.append({"check": "executable", "message": f"{executable} is not available"})

    warnings.extend([
        {"check": "image-generation", "message":
         "Stage 02/05 image-generation access requires a target-computer capability check."},
        {"check": "video-runtime", "message":
         "Stage 06 video runtime, model, GPU/provider access, and credentials require a manual smoke test."},
    ])
    return {"ok": not problems, "root": str(root), "checks": checks,
            "warnings": warnings, "problems": problems}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify an AI Video Pipeline v3 portable bundle")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", action="store_true", help="verify copied file hashes only")
    args = parser.parse_args()
    report = verify(args.root, manifest_only=args.manifest)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
