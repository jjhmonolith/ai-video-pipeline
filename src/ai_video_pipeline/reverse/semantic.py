"""Hermes-native semantic analysis adapter for reverse-engineered clips.

The deterministic pipeline prepares evidence and prompts. This adapter asks the
configured Hermes auxiliary video model to author observations and generation
instructions, preserving every raw response for audit.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


_WORKER = r'''
import asyncio, json, sys
from pathlib import Path
payload = json.loads(sys.stdin.read())
root = payload.get("hermes_root")
if root:
    sys.path.insert(0, root)
from tools.vision_tools import video_analyze_tool, vision_analyze_tool
model = payload.get("model")
if not model:
    try:
        from hermes_cli.config import cfg_get, load_config
        cfg = load_config()
        if payload.get("modality") == "video":
            model = cfg_get(cfg, "auxiliary", "video", "model") or cfg_get(cfg, "auxiliary", "vision", "model")
        else:
            model = cfg_get(cfg, "auxiliary", "vision", "model")
    except Exception:
        model = None
if payload.get("modality") == "video":
    result = asyncio.run(video_analyze_tool(payload["media"], payload["prompt"], model))
else:
    result = asyncio.run(vision_analyze_tool(payload["media"], payload["prompt"], model))
print(result)
'''


def discover_hermes_runtime() -> tuple[Path, Path]:
    executable = shutil.which("hermes")
    if not executable:
        raise RuntimeError("Hermes executable not found; pass --hermes-python")
    executable_path = Path(executable).resolve()
    candidates = [executable_path.parent / "python"]
    if "bin" in executable_path.parts:
        candidates.append(executable_path.parent.parent / "bin" / "python")
    for python in candidates:
        if python.is_file():
            root = python.parent.parent.parent
            if (root / "tools" / "vision_tools.py").is_file():
                return python, root
    # The launcher may be a shell script rather than a Python entry point.
    text = Path(executable).read_text(encoding="utf-8", errors="ignore")
    for token in text.replace('"', " ").split():
        candidate = Path(os.path.expanduser(token))
        if candidate.name.startswith("python") and candidate.is_file():
            root = candidate.parent.parent.parent
            if (root / "tools" / "vision_tools.py").is_file():
                return candidate, root
    raise RuntimeError("Could not discover Hermes Python/runtime root; pass --hermes-python and --hermes-root")


def _extract_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    try:
        value = json.loads(stripped)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        value = json.loads(stripped[start:end + 1])
        if isinstance(value, dict):
            return value
    raise ValueError("Model response did not contain a JSON object")


def _call(
    python: Path,
    hermes_root: Path,
    media: Path,
    prompt: str,
    model: str | None,
    timeout: int,
    modality: str,
) -> tuple[dict[str, Any], str]:
    payload = {
        "hermes_root": str(hermes_root),
        "media": str(media),
        "prompt": prompt,
        "model": model,
        "modality": modality,
    }
    process = subprocess.run(
        [str(python), "-c", _WORKER],
        input=json.dumps(payload),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        cwd=str(hermes_root),
    )
    if process.returncode != 0:
        raise RuntimeError(f"Hermes video worker failed: {process.stderr[-4000:]}")
    wrapper = json.loads(process.stdout)
    if not wrapper.get("success"):
        raise RuntimeError(wrapper.get("analysis") or wrapper.get("error") or "video analysis failed")
    raw = wrapper.get("analysis", "")
    return _extract_object(raw), raw


def _lacks_visual_evidence(value: dict[str, Any], raw: str) -> bool:
    text = (raw + " " + json.dumps(value, ensure_ascii=False)).lower()
    markers = (
        "no video", "no viewable", "not available to inspect", "not accessible",
        "cannot be verified", "could not be analyzed", "no audiovisual",
        "no image", "no frames", "no media was available", "imagery is not accessible",
    )
    return any(marker in text for marker in markers)


def _analyze_request(
    python: Path,
    hermes_root: Path,
    run_dir: Path,
    request: dict[str, Any],
    model: str | None,
    timeout: int,
    mode: str,
) -> tuple[dict[str, Any], str, str]:
    if mode not in {"auto", "video", "frames"}:
        raise ValueError("mode must be auto, video, or frames")
    if mode in {"auto", "video"}:
        video_value = request.get("video_path") or request.get("clip_path")
        video_path = Path(video_value) if request.get("video_path") else run_dir / str(video_value)
        result, raw = _call(python, hermes_root, video_path, request["prompt"], model, timeout, "video")
        if mode == "video" or not _lacks_visual_evidence(result, raw):
            return result, raw, "video"
    fallback = request.get("fallback_image_path")
    if not fallback:
        raise RuntimeError("Video model exposed no visual evidence and no contact-sheet fallback exists")
    frame_prompt = (
        request["prompt"]
        + "\nThe attached contact sheet is ordered left-to-right, top-to-bottom and each tile has a timestamp. "
        + "Treat it as sampled evidence: describe visible state changes between tiles, but do not claim continuous motion, audio, or unseen events."
    )
    result, raw = _call(python, hermes_root, run_dir / fallback, frame_prompt, model, timeout, "image")
    result["evidence_mode"] = "sampled_contact_sheet"
    return result, raw, "frames"


def run_hermes_semantics(
    run_dir: Path,
    *,
    hermes_python: Path | None = None,
    hermes_root: Path | None = None,
    model: str | None = None,
    timeout: int = 300,
    skip_global: bool = False,
    max_shots: int | None = None,
    mode: str = "auto",
) -> dict[str, Any]:
    run_dir = run_dir.expanduser().resolve()
    requests = json.loads((run_dir / "semantic-request.json").read_text(encoding="utf-8"))
    if hermes_python is None or hermes_root is None:
        discovered_python, discovered_root = discover_hermes_runtime()
        hermes_python = hermes_python or discovered_python
        hermes_root = hermes_root or discovered_root
    # Keep the venv launcher path intact. Resolving its Python symlink bypasses
    # pyvenv.cfg and drops Hermes dependencies such as httpx.
    hermes_python = hermes_python.expanduser().absolute()
    hermes_root = hermes_root.expanduser().resolve()
    raw_dir = run_dir / "semantic-raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    failures: list[dict[str, str]] = []
    global_result: dict[str, Any] = {}
    if not skip_global:
        try:
            global_request = requests["global"]
            global_result, raw, evidence_mode = _analyze_request(
                hermes_python, hermes_root, run_dir, global_request, model, timeout, mode,
            )
            global_result["evidence_mode"] = evidence_mode
            (raw_dir / "global.txt").write_text(raw, encoding="utf-8")
        except Exception as exc:
            failures.append({"scope": "global", "error": str(exc)})

    shot_results: list[dict[str, Any]] = []
    shot_requests = requests.get("shots", [])
    if max_shots is not None:
        shot_requests = shot_requests[:max_shots]
    for request in shot_requests:
        shot_id = request["shot_id"]
        try:
            result, raw, evidence_mode = _analyze_request(
                hermes_python, hermes_root, run_dir, request, model, timeout, mode,
            )
            result["shot_id"] = shot_id
            result["evidence_mode"] = evidence_mode
            shot_results.append(result)
            (raw_dir / f"{shot_id}.txt").write_text(raw, encoding="utf-8")
        except Exception as exc:
            failures.append({"scope": shot_id, "error": str(exc)})

    semantic = {
        "schema_version": "1.0",
        "provider": "hermes-video-analyze",
        "model_override": model,
        "requested_mode": mode,
        "global": global_result,
        "shots": shot_results,
        "failures": failures,
    }
    (run_dir / "semantic.json").write_text(json.dumps(semantic, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "ok": not failures,
        "global_completed": bool(global_result) if not skip_global else None,
        "shots_completed": len(shot_results),
        "shots_requested": len(shot_requests),
        "failures": failures,
        "semantic_path": str(run_dir / "semantic.json"),
    }
