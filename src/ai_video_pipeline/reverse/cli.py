"""CLI for video-to-scenario reverse engineering."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import analyze_video, compile_documents, validate_run
from .semantic import run_hermes_semantics


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-video-reverse", description="Convert video evidence into AI-ready scenario and shot contracts")
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze", help="detect shots and extract clips/frames")
    analyze.add_argument("video", type=Path)
    analyze.add_argument("--out", type=Path, required=True)
    analyze.add_argument("--threshold", type=float, default=0.3)
    analyze.add_argument("--min-shot", type=float, default=0.25)

    compile_parser = sub.add_parser("compile", help="render scenario, contracts, and HTML from measurements + semantic JSON")
    compile_parser.add_argument("run_dir", type=Path)
    compile_parser.add_argument("--semantic", type=Path)

    semantic = sub.add_parser("semantic", help="run configured Hermes video model over full video and detected shots")
    semantic.add_argument("run_dir", type=Path)
    semantic.add_argument("--hermes-python", type=Path)
    semantic.add_argument("--hermes-root", type=Path)
    semantic.add_argument("--model")
    semantic.add_argument("--timeout", type=int, default=300)
    semantic.add_argument("--skip-global", action="store_true")
    semantic.add_argument("--max-shots", type=int)
    semantic.add_argument("--mode", choices=("auto", "video", "frames"), default="auto")

    run = sub.add_parser("run", help="analyze and render a deterministic skeleton")
    run.add_argument("video", type=Path)
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--threshold", type=float, default=0.3)
    run.add_argument("--min-shot", type=float, default=0.25)

    validate = sub.add_parser("validate", help="validate evidence and duration integrity")
    validate.add_argument("run_dir", type=Path)
    validate.add_argument("--require-semantic", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "analyze":
        result = analyze_video(args.video, args.out, threshold=args.threshold, min_shot=args.min_shot)
        print(json.dumps({"ok": True, "shot_count": result["shot_count"], "out": str(args.out.resolve())}, ensure_ascii=False))
        return 0
    if args.command == "compile":
        paths = compile_documents(args.run_dir, args.semantic)
        print(json.dumps({"ok": True, "artifacts": {key: str(value) for key, value in paths.items()}}, ensure_ascii=False))
        return 0
    if args.command == "semantic":
        result = run_hermes_semantics(
            args.run_dir,
            hermes_python=args.hermes_python,
            hermes_root=args.hermes_root,
            model=args.model,
            timeout=args.timeout,
            skip_global=args.skip_global,
            max_shots=args.max_shots,
            mode=args.mode,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 1
    if args.command == "run":
        result = analyze_video(args.video, args.out, threshold=args.threshold, min_shot=args.min_shot)
        paths = compile_documents(args.out)
        print(json.dumps({"ok": True, "shot_count": result["shot_count"], "artifacts": {key: str(value) for key, value in paths.items()}}, ensure_ascii=False))
        return 0
    if args.command == "validate":
        result = validate_run(args.run_dir, require_semantic=args.require_semantic)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
