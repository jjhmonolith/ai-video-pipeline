"""Serve blind H3 review pages and persist browser responses into the project."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .h3_followup_experiment import EXPERIMENT_ID


TOPICS = {"luxury-penthouse-tour", "sky-village-plumber"}


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _response_path(project_root: Path, page_id: str) -> Path:
    if page_id not in TOPICS:
        raise ValueError("unknown review page")
    return (project_root / "runs" / page_id / "attempts" / "v1-pilot" / "06-motion" /
            "qa" / "experiments" / EXPERIMENT_ID / "comparison" /
            "human-review-response.json")


def serve(project_root: Path, host: str, port: int) -> None:
    project_root = project_root.resolve()

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(project_root), **kwargs)

        def do_POST(self) -> None:  # noqa: N802 - stdlib hook
            if self.path != "/api/save-review":
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 2_000_000:
                    raise ValueError("invalid response size")
                data = json.loads(self.rfile.read(length).decode("utf-8"))
                if data.get("schema_version") != "h3-followup-human-response.v1":
                    raise ValueError("invalid schema")
                target = _response_path(project_root, str(data.get("page_id")))
                data["saved_at"] = _now()
                target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                payload = json.dumps({"ok": True, "saved_at": data["saved_at"]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except Exception as error:  # noqa: BLE001 - return a readable browser error
                self.send_error(400, str(error))

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"review server http://{host}:{port}", flush=True)
    server.serve_forever()


def main() -> int:
    parser = argparse.ArgumentParser(description="serve H3 blind review and save form JSON")
    parser.add_argument("project_root", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    serve(args.project_root, args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
