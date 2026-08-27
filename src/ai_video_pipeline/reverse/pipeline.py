"""Deterministic media extraction and rendering for video reverse engineering.

Creative interpretation is supplied separately as semantic.json. This module owns
only source measurements, shot candidates, extracted evidence, schema-shaped
requests, rendering, and validation.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import subprocess
from dataclasses import dataclass, asdict
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class ShotMeasurement:
    shot_id: str
    index: int
    start_sec: float
    end_sec: float
    duration_sec: float
    midpoint_sec: float
    clip_path: str
    start_frame_path: str
    middle_frame_path: str
    end_frame_path: str
    contact_sheet_path: str
    sample_frame_paths: list[str]


def _run(command: list[str], *, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Required executable not found: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()[-4000:]
        raise RuntimeError(f"Command failed ({command[0]}): {detail}") from exc


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _fraction(value: str | None) -> float | None:
    if not value or value == "0/0":
        return None
    try:
        return round(float(Fraction(value)), 6)
    except (ValueError, ZeroDivisionError):
        return None


def probe_video(video: Path) -> dict[str, Any]:
    result = _run([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration,size,format_name:stream=index,codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate,sample_rate,channels",
        "-of", "json", str(video),
    ])
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
    audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    duration = round(float(data["format"]["duration"]), 6)
    return {
        "duration_sec": duration,
        "size_bytes": int(data["format"].get("size", video.stat().st_size)),
        "format_name": data["format"].get("format_name"),
        "video": {
            "codec": video_stream.get("codec_name"),
            "width": video_stream.get("width"),
            "height": video_stream.get("height"),
            "fps": _fraction(video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate")),
        },
        "audio": None if audio_stream is None else {
            "codec": audio_stream.get("codec_name"),
            "sample_rate": int(audio_stream["sample_rate"]) if audio_stream.get("sample_rate") else None,
            "channels": audio_stream.get("channels"),
        },
    }


def parse_scene_timestamps(stderr: str) -> list[float]:
    values = [float(match) for match in re.findall(r"pts_time:([0-9]+(?:\.[0-9]+)?)", stderr)]
    return sorted(set(round(value, 6) for value in values))


def detect_shot_boundaries(video: Path, duration: float, threshold: float, min_shot: float) -> list[float]:
    if not 0.0 < threshold < 1.0:
        raise ValueError("threshold must be between 0 and 1")
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-i", str(video),
            "-vf", f"select='gt(scene,{threshold})',showinfo",
            "-an", "-f", "null", "-",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=600,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Shot detection failed: {result.stderr[-4000:]}")
    candidates = [0.0, *parse_scene_timestamps(result.stderr), round(duration, 6)]
    merged = [candidates[0]]
    for value in candidates[1:-1]:
        if value - merged[-1] >= min_shot and duration - value >= min_shot:
            merged.append(value)
    merged.append(round(duration, 6))
    return merged


def _extract_frame(video: Path, time_sec: float, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    safe_time = max(0.0, time_sec)
    _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{safe_time:.6f}", "-i", str(video),
        "-frames:v", "1", "-q:v", "2", str(destination),
    ])


def _make_contact_sheet(items: list[tuple[Path, str]], destination: Path, columns: int = 3) -> None:
    from PIL import Image, ImageDraw

    if not items:
        raise ValueError("contact sheet requires at least one image")
    opened = [Image.open(path).convert("RGB") for path, _ in items]
    thumb_width = 360
    prepared = []
    for image in opened:
        height = max(1, round(image.height * thumb_width / image.width))
        prepared.append(image.resize((thumb_width, height)))
    cell_height = max(image.height for image in prepared) + 28
    rows = (len(prepared) + columns - 1) // columns
    sheet = Image.new("RGB", (thumb_width * columns, cell_height * rows), "#111111")
    draw = ImageDraw.Draw(sheet)
    for index, (image, (_, label)) in enumerate(zip(prepared, items)):
        x = (index % columns) * thumb_width
        y = (index // columns) * cell_height
        sheet.paste(image, (x, y))
        draw.rectangle((x, y + image.height, x + thumb_width, y + cell_height), fill="#111111")
        draw.text((x + 8, y + image.height + 7), label, fill="white")
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination, quality=90)
    for image in opened:
        image.close()


def _extract_clip(video: Path, start: float, duration: float, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{start:.6f}", "-i", str(video), "-t", f"{duration:.6f}",
        "-map", "0:v:0", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-movflags", "+faststart", str(destination),
    ])


def _shot_prompt(shot: ShotMeasurement) -> str:
    return f"""Analyze only shot {shot.shot_id} ({shot.start_sec:.3f}s–{shot.end_sec:.3f}s). Return one JSON object and no markdown.
Use observed evidence only; use null or [] when uncertain. This output will drive an AI video generator.
Required keys: shot_id, observation, narrative_function, setting, time_of_day, subjects, visible_person_count,
actions, performance, framing, camera_angle, lens_intent, composition, camera_movement, lighting, color_palette,
transition_in, transition_out, on_screen_text, dialogue_or_voiceover, ambience, music, sound_events,
continuity_entry, continuity_exit, must_show, must_not_show, generation_prompt, negative_prompt, confidence,
evidence_timestamps. Keep shot_id exactly \"{shot.shot_id}\"."""


def _global_prompt(duration: float, shot_count: int) -> str:
    return f"""Analyze this complete {duration:.3f}-second video as a screenplay and edit blueprint. Return one JSON object and no markdown.
Use observed evidence only; do not invent motivation or dialogue. Required keys: title_guess, logline, viewer_promise,
tone, visual_grammar, narrative_structure, scene_groups, recurring_subjects, locations, global_continuity,
audio_strategy, generation_constraints. There are {shot_count} mechanically detected shot candidates; scene_groups must
reference only S001..S{shot_count:03d} and group shots semantically rather than treating every cut as a new scene."""


def analyze_video(video: Path, out_dir: Path, *, threshold: float = 0.3, min_shot: float = 0.25) -> dict[str, Any]:
    video = video.expanduser().resolve()
    out_dir = out_dir.expanduser().resolve()
    if not video.is_file():
        raise FileNotFoundError(video)
    out_dir.mkdir(parents=True, exist_ok=True)
    probe = probe_video(video)
    boundaries = detect_shot_boundaries(video, probe["duration_sec"], threshold, min_shot)
    shots: list[ShotMeasurement] = []
    for index, (start, end) in enumerate(zip(boundaries, boundaries[1:]), start=1):
        shot_id = f"S{index:03d}"
        duration = round(end - start, 6)
        midpoint = round(start + duration / 2, 6)
        shot_dir = out_dir / "shots" / shot_id
        clip = shot_dir / "clip.mp4"
        start_frame = shot_dir / "start.jpg"
        middle_frame = shot_dir / "middle.jpg"
        end_frame = shot_dir / "end.jpg"
        _extract_clip(video, start, duration, clip)
        frame_epsilon = min(0.05, max(duration / 20, 0.001))
        _extract_frame(video, start + frame_epsilon, start_frame)
        _extract_frame(video, midpoint, middle_frame)
        _extract_frame(video, max(start, end - frame_epsilon), end_frame)
        sample_paths: list[Path] = []
        sample_items: list[tuple[Path, str]] = []
        for sample_index, fraction in enumerate((0.02, 0.20, 0.40, 0.60, 0.80, 0.98), start=1):
            timestamp = min(end - frame_epsilon, max(start + frame_epsilon, start + duration * fraction))
            sample_path = shot_dir / "samples" / f"frame-{sample_index:02d}.jpg"
            _extract_frame(video, timestamp, sample_path)
            sample_paths.append(sample_path)
            sample_items.append((sample_path, f"{shot_id}  t={timestamp:.3f}s"))
        contact_sheet = shot_dir / "contact-sheet.jpg"
        _make_contact_sheet(sample_items, contact_sheet, columns=3)
        shots.append(ShotMeasurement(
            shot_id=shot_id,
            index=index,
            start_sec=start,
            end_sec=end,
            duration_sec=duration,
            midpoint_sec=midpoint,
            clip_path=str(clip.relative_to(out_dir)),
            start_frame_path=str(start_frame.relative_to(out_dir)),
            middle_frame_path=str(middle_frame.relative_to(out_dir)),
            end_frame_path=str(end_frame.relative_to(out_dir)),
            contact_sheet_path=str(contact_sheet.relative_to(out_dir)),
            sample_frame_paths=[str(path.relative_to(out_dir)) for path in sample_paths],
        ))

    global_items = [
        (out_dir / shot.middle_frame_path, f"{shot.shot_id}  t={shot.midpoint_sec:.3f}s")
        for shot in shots
    ]
    global_contact_sheet = out_dir / "global-contact-sheet.jpg"
    _make_contact_sheet(global_items, global_contact_sheet, columns=min(4, max(1, len(global_items))))

    source = {
        "source_path": str(video),
        "source_sha256": _sha256(video),
        "probe": probe,
        "detection": {"method": "ffmpeg-scene-score", "threshold": threshold, "min_shot_sec": min_shot},
    }
    measurements = {
        "schema_version": "1.0",
        "source": source,
        "shot_count": len(shots),
        "boundaries_sec": boundaries,
        "shots": [asdict(shot) for shot in shots],
        "duration_sum_sec": round(sum(shot.duration_sec for shot in shots), 6),
    }
    requests = {
        "schema_version": "1.0",
        "global": {
            "video_path": str(video),
            "fallback_image_path": str(global_contact_sheet.relative_to(out_dir)),
            "prompt": _global_prompt(probe["duration_sec"], len(shots)),
        },
        "shots": [
            {
                "shot_id": shot.shot_id,
                "clip_path": shot.clip_path,
                "fallback_image_path": shot.contact_sheet_path,
                "prompt": _shot_prompt(shot),
            }
            for shot in shots
        ],
        "expected_semantic_path": "semantic.json",
    }
    _write_json(out_dir / "source.json", source)
    _write_json(out_dir / "measurements.json", measurements)
    _write_json(out_dir / "semantic-request.json", requests)
    _write_json(out_dir / "semantic.template.json", {
        "schema_version": "1.0",
        "global": {},
        "shots": [{"shot_id": shot.shot_id} for shot in shots],
    })
    return measurements


def _semantic_map(semantic: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("shot_id")): item
        for item in semantic.get("shots", [])
        if isinstance(item, dict) and item.get("shot_id")
    }


def _join(value: Any) -> str:
    if value is None:
        return "미확정"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "없음"
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _shot_contract(measurement: dict[str, Any], semantic: dict[str, Any]) -> dict[str, Any]:
    return {
        "shot_id": measurement["shot_id"],
        "source_evidence": {
            "start_sec": measurement["start_sec"],
            "end_sec": measurement["end_sec"],
            "clip_path": measurement["clip_path"],
            "frames": [measurement["start_frame_path"], measurement["middle_frame_path"], measurement["end_frame_path"]],
            "contact_sheet_path": measurement.get("contact_sheet_path"),
            "sample_frame_paths": measurement.get("sample_frame_paths", []),
        },
        "purpose": semantic.get("narrative_function"),
        "duration_sec": measurement["duration_sec"],
        "story": {
            "observation": semantic.get("observation"),
            "entering_state": semantic.get("continuity_entry"),
            "action": semantic.get("actions"),
            "performance": semantic.get("performance"),
            "exiting_state": semantic.get("continuity_exit"),
        },
        "visual": {
            "setting": semantic.get("setting"),
            "time_of_day": semantic.get("time_of_day"),
            "subjects": semantic.get("subjects", []),
            "visible_person_count": semantic.get("visible_person_count"),
            "framing": semantic.get("framing"),
            "camera_angle": semantic.get("camera_angle"),
            "lens_intent": semantic.get("lens_intent"),
            "composition": semantic.get("composition"),
            "camera_movement": semantic.get("camera_movement"),
            "lighting": semantic.get("lighting"),
            "color_palette": semantic.get("color_palette"),
        },
        "edit": {
            "transition_in": semantic.get("transition_in"),
            "transition_out": semantic.get("transition_out"),
            "on_screen_text": semantic.get("on_screen_text", []),
        },
        "sound": {
            "dialogue_or_voiceover": semantic.get("dialogue_or_voiceover"),
            "ambience": semantic.get("ambience"),
            "music": semantic.get("music"),
            "events": semantic.get("sound_events", []),
        },
        "generation": {
            "prompt": semantic.get("generation_prompt"),
            "negative_prompt": semantic.get("negative_prompt"),
            "reference_first_frame": measurement["start_frame_path"],
            "reference_last_frame": measurement["end_frame_path"],
            "must_show": semantic.get("must_show", []),
            "must_not_show": semantic.get("must_not_show", []),
        },
        "confidence": semantic.get("confidence"),
        "evidence_timestamps": semantic.get("evidence_timestamps", []),
    }


def compile_documents(run_dir: Path, semantic_path: Path | None = None) -> dict[str, Path]:
    run_dir = run_dir.expanduser().resolve()
    measurements = json.loads((run_dir / "measurements.json").read_text(encoding="utf-8"))
    if semantic_path is None:
        semantic_path = run_dir / "semantic.json"
    semantic = json.loads(semantic_path.read_text(encoding="utf-8")) if semantic_path.is_file() else {"global": {}, "shots": []}
    by_id = _semantic_map(semantic)
    contracts = [_shot_contract(item, by_id.get(item["shot_id"], {})) for item in measurements["shots"]]
    package = {
        "schema_version": "1.0",
        "source_sha256": measurements["source"]["source_sha256"],
        "global": semantic.get("global", {}),
        "shots": contracts,
    }
    _write_json(run_dir / "shot-contracts.json", package)

    global_data = semantic.get("global", {})
    lines = [
        "# 영상 역설계 시나리오",
        "",
        f"- 원본: `{measurements['source']['source_path']}`",
        f"- 길이: {measurements['source']['probe']['duration_sec']:.3f}초",
        f"- 검출 숏: {measurements['shot_count']}개",
        f"- 로그라인: {_join(global_data.get('logline'))}",
        f"- 시청자 약속: {_join(global_data.get('viewer_promise'))}",
        f"- 톤: {_join(global_data.get('tone'))}",
        "",
        "## 전체 구성",
        "",
        _join(global_data.get("narrative_structure")),
        "",
        "## 장면 그룹",
        "",
    ]
    groups = global_data.get("scene_groups") or []
    if groups:
        for index, group in enumerate(groups, start=1):
            lines.append(f"### Scene {index}: {_join(group.get('name') if isinstance(group, dict) else None)}")
            lines.append(_join(group))
            lines.append("")
    else:
        lines.extend(["의미 분석이 아직 입력되지 않았습니다.", ""])
    lines.extend(["## 컷 설계", ""])
    for contract in contracts:
        lines.extend([
            f"### {contract['shot_id']} · {contract['duration_sec']:.3f}초",
            f"- **구간:** {contract['source_evidence']['start_sec']:.3f}–{contract['source_evidence']['end_sec']:.3f}",
            f"- **기능:** {_join(contract['purpose'])}",
            f"- **관찰:** {_join(contract['story']['observation'])}",
            f"- **행동/연기:** {_join(contract['story']['action'])} / {_join(contract['story']['performance'])}",
            f"- **화면:** {_join(contract['visual']['framing'])}, {_join(contract['visual']['camera_angle'])}, {_join(contract['visual']['composition'])}",
            f"- **카메라:** {_join(contract['visual']['camera_movement'])}; 렌즈 의도 {_join(contract['visual']['lens_intent'])}",
            f"- **조명/색:** {_join(contract['visual']['lighting'])} / {_join(contract['visual']['color_palette'])}",
            f"- **사운드:** {_join(contract['sound'])}",
            f"- **생성 프롬프트:** {_join(contract['generation']['prompt'])}",
            f"- **금지:** {_join(contract['generation']['must_not_show'])}; {_join(contract['generation']['negative_prompt'])}",
            "",
        ])
    scenario_path = run_dir / "scenario-and-cut-design.md"
    scenario_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    rows = []
    for contract in contracts:
        middle = contract["source_evidence"]["frames"][1]
        rows.append(
            "<article class='shot'>"
            f"<img src='{html.escape(middle)}' alt='{html.escape(contract['shot_id'])} representative frame'>"
            f"<div><h3>{html.escape(contract['shot_id'])} · {contract['duration_sec']:.3f}s</h3>"
            f"<p><b>기능</b> {html.escape(_join(contract['purpose']))}</p>"
            f"<p><b>관찰</b> {html.escape(_join(contract['story']['observation']))}</p>"
            f"<p><b>카메라</b> {html.escape(_join(contract['visual']['framing']))} · {html.escape(_join(contract['visual']['camera_movement']))}</p>"
            f"<p><b>생성 프롬프트</b> {html.escape(_join(contract['generation']['prompt']))}</p></div></article>"
        )
    report = f"""<!doctype html><html lang='ko'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>영상 역설계 보고서</title><style>body{{margin:0;background:#0d1117;color:#e6edf3;font-family:-apple-system,BlinkMacSystemFont,sans-serif}}main{{max-width:920px;margin:auto;padding:24px}}.meta{{color:#9da7b3}}.shot{{display:grid;grid-template-columns:240px 1fr;gap:18px;padding:16px 0;border-top:1px solid #30363d}}img{{width:100%;border-radius:10px}}p{{line-height:1.55}}@media(max-width:640px){{main{{padding:16px}}.shot{{grid-template-columns:1fr}}}}</style></head>
<body><main><h1>영상 → 시나리오 + 컷 설계</h1><p class='meta'>{measurements['shot_count']} shots · {measurements['source']['probe']['duration_sec']:.3f}s</p>
<h2>{html.escape(_join(global_data.get('logline')))}</h2>{''.join(rows)}</main></body></html>"""
    report_path = run_dir / "report.html"
    report_path.write_text(report, encoding="utf-8")
    return {"scenario": scenario_path, "contracts": run_dir / "shot-contracts.json", "report": report_path}


def validate_run(run_dir: Path, *, require_semantic: bool = False) -> dict[str, Any]:
    run_dir = run_dir.expanduser().resolve()
    errors: list[str] = []
    required = ["source.json", "measurements.json", "semantic-request.json"]
    if require_semantic:
        required.append("semantic.json")
    for name in required:
        if not (run_dir / name).is_file():
            errors.append(f"missing {name}")
    if errors:
        return {"ok": False, "errors": errors}
    measurements = json.loads((run_dir / "measurements.json").read_text(encoding="utf-8"))
    shots = measurements.get("shots", [])
    if len(shots) != measurements.get("shot_count"):
        errors.append("shot_count mismatch")
    duration_sum = round(sum(float(item["duration_sec"]) for item in shots), 4)
    source_duration = round(float(measurements["source"]["probe"]["duration_sec"]), 4)
    if abs(duration_sum - source_duration) > 0.05:
        errors.append(f"duration mismatch: {duration_sum} vs {source_duration}")
    previous_end = 0.0
    for item in shots:
        if abs(float(item["start_sec"]) - previous_end) > 0.01:
            errors.append(f"non-contiguous boundary at {item['shot_id']}")
        previous_end = float(item["end_sec"])
        for key in ("clip_path", "start_frame_path", "middle_frame_path", "end_frame_path", "contact_sheet_path"):
            path_value = item.get(key)
            if not path_value:
                errors.append(f"missing evidence path {item['shot_id']}:{key}")
                continue
            path = run_dir / path_value
            if not path.is_file() or path.stat().st_size == 0:
                errors.append(f"missing evidence {item['shot_id']}:{key}")
    if (run_dir / "shot-contracts.json").is_file():
        contracts = json.loads((run_dir / "shot-contracts.json").read_text(encoding="utf-8"))
        if len(contracts.get("shots", [])) != len(shots):
            errors.append("shot contract count mismatch")
    return {
        "ok": not errors,
        "errors": errors,
        "shot_count": len(shots),
        "duration_sec": source_duration,
        "duration_sum_sec": duration_sum,
    }
