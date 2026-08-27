from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from .h3_runtime import (
    DEFAULT_SERVER,
    NATIVE_LANDSCAPE,
    ComfyClient,
    H3Request,
    H3Settings,
    generate,
)
from .human_gates import load_catalog, resolve_required_gates, validate_feedback_delta, validate_judgment_packet
from .execution_mode import load_execution_mode


def _add_generate_parser(sub: argparse._SubParsersAction) -> None:
    gen = sub.add_parser("generate", help="render one clip on the local MiniMax H3 runtime")
    gen.add_argument("prompt")
    gen.add_argument("--out", type=Path, default=Path("renders"))
    gen.add_argument("--server", default=DEFAULT_SERVER)
    gen.add_argument("--width", type=int, default=NATIVE_LANDSCAPE[0])
    gen.add_argument("--height", type=int, default=NATIVE_LANDSCAPE[1])
    gen.add_argument("--seconds", type=float, default=5.0)
    gen.add_argument("--seed", type=int, default=0)
    gen.add_argument("--first-frame", type=Path, help="local image anchored as the opening frame")
    gen.add_argument("--last-frame", type=Path, help="local image anchored as the closing frame")
    gen.add_argument("--steps", type=int)
    gen.add_argument("--no-turbo", action="store_true", help="drop the turbo LoRA and sample at full step count")
    gen.add_argument("--timeout", type=float, default=3600.0)


def _run_generate(args: argparse.Namespace) -> dict:
    settings = H3Settings()
    if args.no_turbo:
        settings = settings.without_turbo()
    if args.steps:
        settings = replace(settings, steps=args.steps)

    client = ComfyClient(args.server)
    request = H3Request(
        prompt=args.prompt,
        width=args.width,
        height=args.height,
        seconds=args.seconds,
        seed=args.seed,
        first_frame=client.upload_image(args.first_frame) if args.first_frame else None,
        last_frame=client.upload_image(args.last_frame) if args.last_frame else None,
    )
    return generate(request, args.out, settings, args.server, args.timeout)


def main() -> int:
    parser = argparse.ArgumentParser(prog="ai-video-gates")
    parser.add_argument("--catalog", type=Path, default=Path("contracts/human-gates.v1.json"))
    sub = parser.add_subparsers(dest="command", required=True)
    resolve = sub.add_parser("resolve")
    resolve.add_argument("event", type=Path)
    resolve.add_argument("--attempt", type=Path,
                         help="execution-mode.json을 읽어 event의 mode를 attempt에 결속")
    packet = sub.add_parser("validate-packet")
    packet.add_argument("packet", type=Path)
    feedback = sub.add_parser("validate-feedback")
    feedback.add_argument("feedback", type=Path)
    _add_generate_parser(sub)
    args = parser.parse_args()

    if args.command == "generate":
        print(json.dumps(_run_generate(args), ensure_ascii=False, indent=2))
        return 0

    catalog = load_catalog(args.catalog)
    if args.command == "resolve":
        event = json.loads(args.event.read_text(encoding="utf-8"))
        if args.attempt:
            event["execution_mode"] = load_execution_mode(args.attempt)["mode"]
        result = resolve_required_gates(catalog, event)
    elif args.command == "validate-packet":
        validate_judgment_packet(json.loads(args.packet.read_text(encoding="utf-8")), catalog)
        result = {"status": "PASS", "artifact": str(args.packet)}
    else:
        validate_feedback_delta(json.loads(args.feedback.read_text(encoding="utf-8")))
        result = {"status": "PASS", "artifact": str(args.feedback)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
