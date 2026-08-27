"""Snapshot, fork and compare attempts so any version can be returned to.

An attempt is a version of the whole workflow, not just its output. Going back
to v2 means getting v2's prompts, cards and tools back, not only its mp4. So a
snapshot hashes every input that decides what gets made, and a fork copies
those inputs forward into a new attempt as its starting point.

    snapshot  현재 입력을 해시로 굳혀 VERSION.json 에 기록
    fork      기존 시도를 새 시도의 출발점으로 복사
    diff      두 시도 사이에 무엇이 달라졌는지
    restore   어떤 시도의 입력을 되살려 새 시도를 만든다

Outputs are deliberately not hashed. Regenerating from identical inputs does
not give identical frames, and pretending otherwise would make every snapshot
look dirty.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

# Inputs decide what gets made. Everything else is a result.
INPUT_GLOBS = [
    "VERSION.json",
    "ATTEMPT.md",
    "tools/*.py",
    "*/prompts/*.json",
    "*/prompts/*.md",
    "*/output/*.json",
    "*/NOTES.md",
]
SKIP_NAMES = {"VERSION.json"}


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]


def collect_inputs(attempt: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    for pattern in INPUT_GLOBS:
        for path in sorted(attempt.glob(pattern)):
            if not path.is_file() or path.name in SKIP_NAMES:
                continue
            found[str(path.relative_to(attempt))] = _hash(path)
    return found


def snapshot(attempt: Path, parent: str | None, note: str | None) -> dict:
    inputs = collect_inputs(attempt)
    existing = {}
    version_file = attempt / "VERSION.json"
    if version_file.exists():
        existing = json.loads(version_file.read_text(encoding="utf-8"))

    record = {
        "attempt": attempt.name,
        "parent": parent if parent is not None else existing.get("parent"),
        "note": note if note is not None else existing.get("note"),
        "snapshot_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "input_count": len(inputs),
        "inputs": inputs,
        "history": existing.get("history", []),
    }
    if existing.get("inputs") and existing["inputs"] != inputs:
        record["history"] = existing["history"] + [{
            "snapshot_at": existing.get("snapshot_at"),
            "input_count": existing.get("input_count"),
            "inputs": existing["inputs"],
        }]
    version_file.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def fork(source: Path, target: Path, note: str) -> dict:
    if target.exists() and any(target.iterdir()):
        raise SystemExit(f"{target.name} 이 비어 있지 않다")
    target.mkdir(parents=True, exist_ok=True)

    copied = []
    for relative in collect_inputs(source):
        src = source / relative
        dst = target / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied.append(relative)

    record = snapshot(target, parent=source.name, note=note)
    record["copied_from"] = source.name
    record["copied_files"] = copied
    (target / "VERSION.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def diff(left: Path, right: Path) -> dict:
    a, b = collect_inputs(left), collect_inputs(right)
    return {
        "left": left.name, "right": right.name,
        "only_in_left": sorted(set(a) - set(b)),
        "only_in_right": sorted(set(b) - set(a)),
        "changed": sorted(k for k in set(a) & set(b) if a[k] != b[k]),
        "identical": sorted(k for k in set(a) & set(b) if a[k] == b[k]),
    }


def verify(attempt: Path) -> dict:
    version_file = attempt / "VERSION.json"
    if not version_file.exists():
        return {"attempt": attempt.name, "ok": False, "problems": ["VERSION.json 없음"]}
    recorded = json.loads(version_file.read_text(encoding="utf-8")).get("inputs", {})
    current = collect_inputs(attempt)
    problems = []
    for key in sorted(set(recorded) - set(current)):
        problems.append(f"삭제됨: {key}")
    for key in sorted(set(current) - set(recorded)):
        problems.append(f"스냅샷 이후 추가됨: {key}")
    for key in sorted(set(recorded) & set(current)):
        if recorded[key] != current[key]:
            problems.append(f"변경됨: {key}")
    return {"attempt": attempt.name, "ok": not problems, "problems": problems}


def main() -> int:
    parser = argparse.ArgumentParser(description="시도 버전 관리")
    sub = parser.add_subparsers(dest="command", required=True)

    snap = sub.add_parser("snapshot")
    snap.add_argument("attempt", type=Path)
    snap.add_argument("--parent")
    snap.add_argument("--note")

    fk = sub.add_parser("fork", help="기존 시도를 새 시도의 출발점으로 복사")
    fk.add_argument("source", type=Path)
    fk.add_argument("target", type=Path)
    fk.add_argument("--note", required=True)

    df = sub.add_parser("diff")
    df.add_argument("left", type=Path)
    df.add_argument("right", type=Path)

    vf = sub.add_parser("verify", help="스냅샷 이후 입력이 바뀌었는지")
    vf.add_argument("attempt", type=Path)

    args = parser.parse_args()
    if args.command == "snapshot":
        result = snapshot(args.attempt, args.parent, args.note)
        result.pop("inputs", None)
        result.pop("history", None)
    elif args.command == "fork":
        result = fork(args.source, args.target, args.note)
        result.pop("inputs", None)
        result.pop("history", None)
    elif args.command == "diff":
        result = diff(args.left, args.right)
    else:
        result = verify(args.attempt)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
