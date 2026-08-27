"""Local, read-only HTTP server for the v3 production dashboard."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import BinaryIO
from urllib.parse import parse_qs, quote, unquote, urlsplit
from urllib.request import urlopen

from .dashboard_model import build_snapshot


RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)$")
TEXT_PREVIEW_CAP = 2_000_000
DASHBOARD_SESSION_SCHEMA = "v3-dashboard-session.v1"
_DETACHED_PROCESSES: dict[int, subprocess.Popen] = {}
_DETACHED_PROCESS_LOCK = threading.Lock()


def _static_root() -> Path:
    return Path(str(files("ai_video_pipeline").joinpath("dashboard_static"))).resolve()


def _contained(root: Path, value: str) -> Path | None:
    candidate = (root / value.lstrip("/")).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def _session_path(attempt: Path) -> Path:
    return attempt.resolve() / ".dashboard" / "session.json"


def _write_json_atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _read_session(attempt: Path) -> dict | None:
    path = _session_path(attempt)
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or value.get("schema_version") != DASHBOARD_SESSION_SCHEMA:
        return None
    if Path(str(value.get("attempt") or "")).resolve() != attempt.resolve():
        return None
    parsed = urlsplit(str(value.get("url") or ""))
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"} or not parsed.port:
        return None
    return value


def _session_responds(session: dict) -> bool:
    try:
        with urlopen(f"{str(session['url']).rstrip('/')}/api/snapshot", timeout=1.0) as response:
            return response.status == HTTPStatus.OK
    except (OSError, ValueError, KeyError):
        return False


def _reap_detached_process(process: subprocess.Popen) -> None:
    try:
        process.wait()
    finally:
        with _DETACHED_PROCESS_LOCK:
            _DETACHED_PROCESSES.pop(process.pid, None)


def launch_dashboard(
    attempt: Path,
    *,
    open_browser: bool = True,
    wait_seconds: float = 4.0,
) -> dict:
    """Start one detached local dashboard for an attempt, or reuse the live one."""
    attempt = attempt.resolve()
    if not (attempt / "pipeline-state.json").is_file():
        raise ValueError(f"not a v3 attempt: {attempt}")

    existing = _read_session(attempt)
    if existing and _session_responds(existing):
        if open_browser:
            webbrowser.open(str(existing["url"]))
        return {"status": "already_running", "url": existing["url"], "pid": existing.get("pid")}

    runtime = attempt / ".dashboard"
    runtime.mkdir(parents=True, exist_ok=True)
    session_path = _session_path(attempt)
    log_path = runtime / "server.log"
    command = [
        sys.executable,
        "-m",
        "ai_video_pipeline.v3.dashboard_server",
        str(attempt),
        "--host",
        "127.0.0.1",
        "--port",
        "0",
        "--session-file",
        str(session_path),
    ]
    if not open_browser:
        command.append("--no-open")
    process_options: dict = {"close_fds": True}
    if os.name == "nt":
        process_options["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        )
    else:
        process_options["start_new_session"] = True
    with log_path.open("ab") as log:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                   **process_options)
    with _DETACHED_PROCESS_LOCK:
        _DETACHED_PROCESSES[process.pid] = process
    threading.Thread(target=_reap_detached_process, args=(process,), daemon=True).start()

    deadline = time.monotonic() + max(0.1, wait_seconds)
    while time.monotonic() < deadline:
        session = _read_session(attempt)
        if session and session.get("pid") == process.pid and _session_responds(session):
            return {"status": "serving", "url": session["url"], "pid": process.pid}
        if process.poll() is not None:
            break
        time.sleep(0.05)

    message = "dashboard process did not become ready"
    if process.poll() is not None:
        try:
            tail = log_path.read_text(encoding="utf-8", errors="replace")[-2000:].strip()
        except OSError:
            tail = ""
        if tail:
            message = tail
    return {"status": "failed", "pid": process.pid, "error": message, "log": str(log_path)}


class DashboardHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], attempt: Path, static_root: Path | None = None):
        self.attempt = attempt.resolve()
        self.static_root = (static_root or _static_root()).resolve()
        super().__init__(address, DashboardHandler)


class DashboardHandler(BaseHTTPRequestHandler):
    server: DashboardHTTPServer
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:
        return

    def _headers(self, status: int, content_type: str, length: int, **extra: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; "
            "font-src 'self'; object-src 'none'; frame-ancestors 'none'",
        )
        for key, value in extra.items():
            self.send_header(key.replace("_", "-"), value)
        self.end_headers()

    def _json(self, value: object, status: int = HTTPStatus.OK, *, etag: str | None = None) -> None:
        body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        extra = {"Cache_Control": "no-store"}
        if etag:
            extra["ETag"] = f'"{etag}"'
        self._headers(status, "application/json; charset=utf-8", len(body), **extra)
        if self.command != "HEAD":
            self.wfile.write(body)

    def _error(self, status: int, message: str) -> None:
        self._json({"ok": False, "error": message}, status)

    def _snapshot(self) -> None:
        try:
            snapshot = build_snapshot(self.server.attempt)
        except Exception as error:  # dashboard must report corrupt or partial state visibly
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(error))
            return
        etag = snapshot.get("etag")
        if etag and self.headers.get("If-None-Match") == f'"{etag}"':
            self.send_response(HTTPStatus.NOT_MODIFIED)
            self.send_header("ETag", f'"{etag}"')
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        self._json(snapshot, etag=str(etag) if etag else None)

    def _attempt_path(self, encoded: str) -> Path | None:
        return _contained(self.server.attempt, unquote(encoded))

    def _copy_range(self, source: BinaryIO, length: int) -> None:
        remaining = length
        while remaining:
            block = source.read(min(1024 * 256, remaining))
            if not block:
                break
            self.wfile.write(block)
            remaining -= len(block)

    def _serve_attempt_file(self, encoded: str, *, inline: bool = True) -> None:
        path = self._attempt_path(encoded)
        if path is None or not path.is_file():
            self._error(HTTPStatus.NOT_FOUND, "attempt file not found")
            return
        size = path.stat().st_size
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        start, end = 0, size - 1
        status = HTTPStatus.OK
        range_header = self.headers.get("Range")
        if range_header:
            if size == 0:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", "bytes */0")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            match = RANGE_RE.fullmatch(range_header.strip())
            if not match:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            first, last = match.groups()
            if first:
                start = int(first)
                end = int(last) if last else end
            elif last:
                suffix = min(int(last), size)
                start = size - suffix
            if start >= size or start > end:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            end = min(end, size - 1)
            status = HTTPStatus.PARTIAL_CONTENT
        length = size if status == HTTPStatus.OK else max(0, end - start + 1)
        ascii_name = re.sub(r"[^A-Za-z0-9._-]", "_", path.name) or "media"
        encoded_name = quote(path.name, safe="")
        extra = {
            "Accept_Ranges": "bytes",
            "Cache_Control": "no-store",
            "Content_Disposition": ("inline" if inline else "attachment")
            + f'; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded_name}',
        }
        if status == HTTPStatus.PARTIAL_CONTENT:
            extra["Content_Range"] = f"bytes {start}-{end}/{size}"
        self._headers(status, content_type, length, **extra)
        if self.command == "HEAD":
            return
        with path.open("rb") as source:
            source.seek(start)
            self._copy_range(source, length)

    def _file_preview(self, query: str) -> None:
        params = parse_qs(query)
        relative = (params.get("path") or [""])[0]
        path = self._attempt_path(relative)
        if path is None or not path.is_file():
            self._error(HTTPStatus.NOT_FOUND, "attempt file not found")
            return
        if path.stat().st_size > TEXT_PREVIEW_CAP:
            self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "text preview exceeds 2 MB")
            return
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            self._error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "file is not UTF-8 text")
            return
        self._json({"path": path.relative_to(self.server.attempt).as_posix(), "text": text})

    def _serve_static(self, raw_path: str) -> None:
        relative = unquote(raw_path).lstrip("/") or "index.html"
        path = _contained(self.server.static_root, relative)
        if path is None:
            self._error(HTTPStatus.NOT_FOUND, "dashboard file not found")
            return
        if not path.is_file():
            if "." not in Path(relative).name:
                path = self.server.static_root / "index.html"
            if not path.is_file():
                self._error(HTTPStatus.NOT_FOUND, "dashboard frontend has not been built")
                return
        body = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        cache = "public, max-age=31536000, immutable" if "/assets/" in raw_path else "no-cache"
        self._headers(HTTPStatus.OK, content_type, len(body), Cache_Control=cache)
        if self.command != "HEAD":
            self.wfile.write(body)

    def _route(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path == "/api/snapshot":
            self._snapshot()
        elif parsed.path == "/api/file":
            self._file_preview(parsed.query)
        elif parsed.path.startswith("/media/"):
            self._serve_attempt_file(parsed.path.removeprefix("/media/"))
        else:
            self._serve_static(parsed.path)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self._route()

    def do_HEAD(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self._route()

    def do_POST(self) -> None:  # noqa: N802 - deliberately read-only
        self._error(HTTPStatus.METHOD_NOT_ALLOWED, "dashboard is read-only")

    do_PUT = do_POST
    do_PATCH = do_POST
    do_DELETE = do_POST


def create_server(
    attempt: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    static_root: Path | None = None,
) -> DashboardHTTPServer:
    attempt = attempt.resolve()
    if not (attempt / "pipeline-state.json").is_file():
        raise ValueError(f"not a v3 attempt: {attempt}")
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("the read-only dashboard may bind only to loopback")
    root = (static_root or _static_root()).resolve()
    if not (root / "index.html").is_file():
        raise ValueError(f"dashboard frontend is missing: {root / 'index.html'}")
    return DashboardHTTPServer((host, port), attempt, root)


def serve(
    attempt: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    open_browser: bool = True,
    session_file: Path | None = None,
) -> None:
    server = create_server(attempt, host=host, port=port)
    address, bound_port = server.server_address[:2]
    display_host = "127.0.0.1" if address in {"0.0.0.0", "::"} else address
    url = f"http://{display_host}:{bound_port}/"
    session_path = (session_file or _session_path(server.attempt)).resolve()
    try:
        session_path.relative_to(server.attempt)
    except ValueError as error:
        server.server_close()
        raise ValueError("dashboard session file must stay inside the attempt") from error
    session = {
        "schema_version": DASHBOARD_SESSION_SCHEMA,
        "status": "serving",
        "url": url,
        "attempt": str(server.attempt),
        "pid": os.getpid(),
    }
    _write_json_atomic(session_path, session)
    print(json.dumps(session, ensure_ascii=False), flush=True)
    if open_browser:
        threading.Timer(0.15, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever(poll_interval=0.4)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        current = _read_session(server.attempt)
        if current and current.get("pid") == os.getpid() and session_path == _session_path(server.attempt):
            session_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the read-only v3 production dashboard")
    parser.add_argument("attempt", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--session-file", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        serve(args.attempt, host=args.host, port=args.port, open_browser=not args.no_open,
              session_file=args.session_file)
    except (ValueError, OSError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
