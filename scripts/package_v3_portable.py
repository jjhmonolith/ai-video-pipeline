#!/usr/bin/env python3
"""Build a secret-free, hash-manifested portable source bundle for pipeline v3."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import zipfile
from datetime import datetime, timezone
from pathlib import Path


BUNDLE_ROOT = "ai-video-pipeline-v3"
ROOT_FILES = (
    ".gitignore",
    "AGENTS.md",
    "PORTABLE_SETUP.md",
    "README.md",
    "pyproject.toml",
    "uv.lock",
)
SCRIPT_FILES = (
    "scripts/package_v3_portable.py",
    "scripts/render_stage6_parallel.py",
    "scripts/update_from_github.py",
    "scripts/validate_project_skills.py",
    "scripts/verify_v3_portable.py",
)
ROOT_TREES = (
    ".agents/skills",
    "contracts",
    "dashboard",
    "docs/pipeline-v3",
    "src",
)
TEST_FILES = (
    "tests/test_portable_package.py",
    "tests/test_run_layout.py",
    "tests/test_v3_dashboard.py",
    "tests/test_v3_end_to_end.py",
    "tests/test_v3_integrity.py",
    "tests/test_v3_orchestrator.py",
)
EXCLUDED_PARTS = {
    ".DS_Store",
    ".git",
    ".pytest_cache",
    ".secrets",
    ".venv",
    "__pycache__",
    "archive",
    "build",
    "dist",
    "node_modules",
    "renders",
    "runs",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
FORBIDDEN_NAMES = {".env", "credentials.json", "secrets.json", "token.json"}
SECRET_PATTERNS = (
    re.compile(rb"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}"),
    re.compile(rb"ghp_[A-Za-z0-9]{20,}"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)


class PackagingError(RuntimeError):
    pass


def _project_version(root: Path) -> str:
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise PackagingError("project version is missing from pyproject.toml")
    return match.group(1)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _allowed_file(path: Path) -> bool:
    if any(part in EXCLUDED_PARTS for part in path.parts):
        return False
    if any(part.endswith(".egg-info") for part in path.parts):
        return False
    if path.name.lower() in FORBIDDEN_NAMES or path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    return path.is_file()


def _collect(root: Path) -> list[Path]:
    files: set[Path] = set()
    for relative in ROOT_FILES + SCRIPT_FILES + TEST_FILES:
        path = root / relative
        if not path.is_file():
            raise PackagingError(f"required file is missing: {relative}")
        files.add(path)
    for relative in ROOT_TREES:
        holder = root / relative
        if not holder.is_dir():
            raise PackagingError(f"required directory is missing: {relative}")
        for path in holder.rglob("*"):
            if _allowed_file(path):
                files.add(path)
    return sorted(files, key=lambda item: item.relative_to(root).as_posix())


def _read_checked(root: Path, path: Path) -> tuple[str, bytes]:
    if path.is_symlink():
        raise PackagingError(f"symlinks are not portable: {path.relative_to(root)}")
    relative = path.relative_to(root).as_posix()
    data = path.read_bytes()
    for pattern in SECRET_PATTERNS:
        if pattern.search(data):
            raise PackagingError(f"possible secret found in included file: {relative}")
    return relative, data


def _zip_info(name: str, executable: bool = False) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(2026, 8, 27, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    mode = 0o755 if executable else 0o644
    info.external_attr = (stat.S_IFREG | mode) << 16
    return info


def build(root: Path, output_dir: Path) -> Path:
    root = root.resolve()
    output_dir = output_dir.resolve()
    version = _project_version(root)
    files = _collect(root)
    records: list[dict] = []
    payloads: list[tuple[str, bytes, bool]] = []
    for path in files:
        relative, data = _read_checked(root, path)
        executable = relative.startswith("scripts/") and relative.endswith(".py")
        payloads.append((relative, data, executable))
        records.append({"path": relative, "bytes": len(data), "sha256": _sha256_bytes(data)})

    manifest = {
        "schema_version": "ai-video-pipeline-portable-manifest.v1",
        "bundle_root": BUNDLE_ROOT,
        "project_version": version,
        "pipeline_version": "3.0",
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "files": records,
        "excluded": [
            "runs and generated media",
            "archive and research material",
            "virtual environments and caches",
            "secrets, credentials, accounts, model weights, and generation servers",
        ],
    }
    manifest_data = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    checksum_lines = [f"{record['sha256']}  {record['path']}" for record in records]
    checksum_data = ("\n".join(checksum_lines) + "\n").encode("utf-8")

    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"ai-video-pipeline-v3-portable-{version}.zip"
    temporary = target.with_suffix(".zip.tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative, data, executable in payloads:
            archive.writestr(_zip_info(f"{BUNDLE_ROOT}/{relative}", executable), data)
        archive.writestr(_zip_info(f"{BUNDLE_ROOT}/PORTABLE_MANIFEST.json"), manifest_data)
        archive.writestr(_zip_info(f"{BUNDLE_ROOT}/MANIFEST.sha256"), checksum_data)
    temporary.replace(target)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Package AI Video Pipeline v3 for another computer")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    output_dir = args.output_dir or args.root / "dist"
    try:
        target = build(args.root, output_dir)
    except PackagingError as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"ok": True, "bundle": str(target), "sha256":
                      _sha256_bytes(target.read_bytes()), "bytes": target.stat().st_size},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
