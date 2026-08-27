"""Attempt-scoped execution mode with an explicit fast-track opt-in."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


MODE_SCHEMA = "execution-mode.v1"
NORMAL_MODE = "normal"
FAST_TRACK_MODE = "fast_track"
EXECUTION_MODES = {NORMAL_MODE, FAST_TRACK_MODE}


class ExecutionModeError(ValueError):
    """An execution mode record is invalid or was not explicitly authorized."""


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def mode_path(attempt: Path) -> Path:
    return attempt.resolve() / "qa" / "execution-mode.json"


def normal_mode_record(attempt: Path) -> dict:
    return {
        "schema_version": MODE_SCHEMA,
        "mode": NORMAL_MODE,
        "attempt": str(attempt.resolve()),
        "source": "default",
        "explicit_opt_in_required_for_fast_track": True,
        "intermediate_human_approval_required": True,
        "ai_may_apply_internal_review_packets": False,
        "continue_through_accepted_quality_defects": False,
        "external_side_effects_authorized": False,
    }


def load_execution_mode(attempt: Path) -> dict:
    attempt = attempt.resolve()
    path = mode_path(attempt)
    if not path.exists():
        return normal_mode_record(attempt)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ExecutionModeError(f"execution mode를 읽을 수 없다: {path}: {error}") from error
    if (payload.get("schema_version") != MODE_SCHEMA or
            payload.get("mode") not in EXECUTION_MODES or
            Path(str(payload.get("attempt") or "")).resolve() != attempt):
        raise ExecutionModeError("execution mode의 schema·mode·attempt 결속이 다르다")
    if payload["mode"] == FAST_TRACK_MODE:
        if (payload.get("source") != "explicit_user_instruction" or
                not str(payload.get("set_by") or "").strip() or
                not str(payload.get("reason") or "").strip()):
            raise ExecutionModeError("fast_track에는 명시적 사용자 지시 영수증이 필요하다")
    return payload


def set_execution_mode(attempt: Path, mode: str, *, by: str, reason: str) -> dict:
    attempt = attempt.resolve()
    if mode not in EXECUTION_MODES:
        raise ExecutionModeError(f"mode는 {sorted(EXECUTION_MODES)} 중 하나여야 한다")
    if not str(by).strip() or not str(reason).strip():
        raise ExecutionModeError("mode 변경에는 by와 reason이 필요하다")
    payload = {
        "schema_version": MODE_SCHEMA,
        "mode": mode,
        "attempt": str(attempt),
        "source": "explicit_user_instruction",
        "set_by": str(by).strip(),
        "reason": str(reason).strip(),
        "set_at": _now(),
        "explicit_opt_in_required_for_fast_track": True,
        "intermediate_human_approval_required": mode == NORMAL_MODE,
        "ai_may_apply_internal_review_packets": mode == FAST_TRACK_MODE,
        "continue_through_accepted_quality_defects": mode == FAST_TRACK_MODE,
        "external_side_effects_authorized": False,
        "safety_and_permission_boundaries_unchanged": True,
    }
    path = mode_path(attempt)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**payload, "path": str(path)}


def is_fast_track(attempt: Path) -> bool:
    return load_execution_mode(attempt).get("mode") == FAST_TRACK_MODE


def main() -> int:
    parser = argparse.ArgumentParser(description="attempt 실행 모드를 조회하거나 명시적으로 설정한다")
    parser.add_argument("attempt", type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("show")
    setter = sub.add_parser("set")
    setter.add_argument("mode", choices=sorted(EXECUTION_MODES))
    setter.add_argument("--by", required=True)
    setter.add_argument("--reason", required=True)
    args = parser.parse_args()
    try:
        result = (load_execution_mode(args.attempt) if args.command == "show" else
                  set_execution_mode(args.attempt, args.mode, by=args.by, reason=args.reason))
    except ExecutionModeError as error:
        print(json.dumps({"ok": False, "problem": str(error)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
