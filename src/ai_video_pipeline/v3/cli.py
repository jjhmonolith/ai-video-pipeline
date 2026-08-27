"""Command-line interface for the v3 state machine and integrity guards."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .dashboard_server import launch_dashboard, serve as serve_dashboard
from .integrity import load_json, validate_artifact
from .orchestrator import (
    OrchestratorError,
    approve,
    initialize,
    load_state,
    review,
    set_mode,
    submit,
    work_order,
)


def _print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM-authored video pipeline v3")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init")
    init.add_argument("attempt", type=Path)
    init.add_argument("--direction", required=True)
    init.add_argument("--mode", choices=("normal", "fast_track"), default="normal")
    init.add_argument("--by", default="user")
    init.add_argument("--reason", default="new production")
    init.add_argument("--no-dashboard", action="store_true",
                      help="do not open the local read-only dashboard")

    status = sub.add_parser("status")
    status.add_argument("attempt", type=Path)

    work = sub.add_parser("work")
    work.add_argument("attempt", type=Path)

    submit_parser = sub.add_parser("submit")
    submit_parser.add_argument("attempt", type=Path)

    review_parser = sub.add_parser("review")
    review_parser.add_argument("attempt", type=Path)
    review_parser.add_argument("--file", type=Path)

    approval = sub.add_parser("approve")
    approval.add_argument("attempt", type=Path)
    approval.add_argument("--stage", required=True)
    approval.add_argument("--by", required=True)
    approval.add_argument("--decision", choices=("approve", "revise", "reject"), required=True)
    approval.add_argument("--feedback", default="")

    mode = sub.add_parser("set-mode")
    mode.add_argument("attempt", type=Path)
    mode.add_argument("mode", choices=("normal", "fast_track"))
    mode.add_argument("--by", required=True)
    mode.add_argument("--reason", required=True)

    validate = sub.add_parser("validate")
    validate.add_argument("attempt", type=Path)
    validate.add_argument("--stage", required=True)
    validate.add_argument("--artifact", type=Path, required=True)

    dashboard = sub.add_parser("dashboard")
    dashboard.add_argument("attempt", type=Path)
    dashboard.add_argument("--host", default="127.0.0.1")
    dashboard.add_argument("--port", type=int, default=0)
    dashboard.add_argument("--no-open", action="store_true")
    dashboard.add_argument("--detach", action="store_true",
                           help="start or reuse a background dashboard and return")

    args = parser.parse_args()
    try:
        if args.command == "init":
            result = initialize(args.attempt, args.direction, mode=args.mode,
                                by=args.by, reason=args.reason)
            if not args.no_dashboard:
                result = dict(result)
                try:
                    result["dashboard"] = launch_dashboard(args.attempt)
                except (ValueError, OSError) as error:
                    result["dashboard"] = {"status": "failed", "error": str(error)}
        elif args.command == "status":
            result = load_state(args.attempt)
        elif args.command == "work":
            result = work_order(args.attempt)
        elif args.command == "submit":
            result = submit(args.attempt)
        elif args.command == "review":
            result = review(args.attempt, args.file)
        elif args.command == "approve":
            result = approve(args.attempt, args.stage, by=args.by,
                             decision=args.decision, feedback=args.feedback)
        elif args.command == "set-mode":
            result = set_mode(args.attempt, args.mode, by=args.by, reason=args.reason)
        elif args.command == "dashboard":
            if args.detach:
                if args.host not in {"127.0.0.1", "localhost"} or args.port != 0:
                    raise ValueError("detached dashboard chooses its own loopback port")
                result = launch_dashboard(args.attempt, open_browser=not args.no_open)
                _print(result)
                return 1 if result.get("status") == "failed" else 0
            serve_dashboard(args.attempt, host=args.host, port=args.port,
                            open_browser=not args.no_open)
            return 0
        else:
            artifact = load_json(args.artifact, "artifact")
            try:
                mode_name = load_state(args.attempt)["mode"]["name"]
            except Exception:
                mode_name = "normal"
            result = validate_artifact(args.attempt.resolve(), args.stage, artifact, mode=mode_name)
    except (OrchestratorError, ValueError, OSError) as error:
        _print({"ok": False, "error": str(error)})
        return 1
    _print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
