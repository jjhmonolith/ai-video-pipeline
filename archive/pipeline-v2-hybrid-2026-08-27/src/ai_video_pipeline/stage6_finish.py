"""AI fast-track review, adaptive retries, and deterministic Stage 06 stitching."""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .contract import load as load_contract
from .execution_mode import FAST_TRACK_MODE, load_execution_mode
from .research import _client
from .stage6 import SCHEMA, _seed, varied_prompt


class Stage6FinishError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> dict:
    if not path.is_file():
        raise Stage6FinishError(f"required JSON is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _motion_root(attempt: Path) -> Path:
    contract = load_contract(attempt)
    return attempt / contract.stage_for("motion", "06-motion")


def _manifest(attempt: Path) -> tuple[Path, dict]:
    path = _motion_root(attempt) / "qa" / "manifest.json"
    payload = _json(path)
    if payload.get("schema_version") != SCHEMA:
        raise Stage6FinishError("unsupported Stage 06 manifest")
    mode = load_execution_mode(attempt)
    if mode.get("mode") != FAST_TRACK_MODE:
        raise Stage6FinishError("Stage 06 AI finish requires explicit fast_track mode")
    recorded = payload.get("execution_mode") or {}
    if recorded.get("mode") != FAST_TRACK_MODE or recorded.get("set_at") != mode.get("set_at"):
        raise Stage6FinishError("Stage 06 manifest is not bound to the current fast_track receipt")
    return path, payload


def _job_video(attempt: Path, job: dict) -> Path:
    files = list((job.get("generation") or {}).get("files") or [])
    candidates = [Path(value) for value in files if str(value).lower().endswith(".mp4")]
    if not candidates:
        candidates = sorted((attempt / str(job["output_dir"])).glob("*.mp4"))
    if not candidates:
        raise Stage6FinishError(f"{job.get('job_id')}: completed video is missing")
    path = candidates[-1]
    if not path.is_absolute():
        path = attempt / path
    if not path.is_file() or path.stat().st_size == 0:
        raise Stage6FinishError(f"{job.get('job_id')}: invalid video {path}")
    return path.resolve()


def _probe(path: Path) -> dict:
    raw = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout
    data = json.loads(raw)
    video = next((stream for stream in data.get("streams", []) if stream.get("codec_type") == "video"), None)
    if not video:
        raise Stage6FinishError(f"video stream is missing: {path}")
    duration = float(video.get("duration") or (data.get("format") or {}).get("duration") or 0)
    return {
        "width": int(video.get("width") or 0), "height": int(video.get("height") or 0),
        "duration": duration, "codec": video.get("codec_name"),
        "fps": video.get("avg_frame_rate"),
        "has_audio": any(s.get("codec_type") == "audio" for s in data.get("streams", [])),
    }


def _frame(path: Path, at: float) -> Image.Image:
    result = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-ss", f"{at:.3f}", "-i", str(path),
         "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"],
        check=True, capture_output=True,
    )
    return Image.open(io.BytesIO(result.stdout)).convert("RGB")


def _mean_abs(left: Image.Image, right: Image.Image) -> float:
    # Preserve the source aspect while measuring.  The Stage 06 contract may be
    # portrait, landscape, or square; forcing every frame into a portrait
    # thumbnail makes landscape motion harder to inspect and biases the metric.
    source_width, source_height = left.size
    if source_width >= source_height:
        size = (168, max(1, round(168 * source_height / source_width)))
    else:
        size = (max(1, round(168 * source_width / source_height)), 168)
    a = left.resize(size).convert("RGB")
    b = right.resize(size).convert("RGB")
    av = list(a.getdata())
    bv = list(b.getdata())
    return sum(abs(x - y) for pa, pb in zip(av, bv) for x, y in zip(pa, pb)) / (len(av) * 3 * 255)


def _candidate_metrics(attempt: Path, job: dict) -> tuple[dict, list[Image.Image]]:
    video = _job_video(attempt, job)
    probe = _probe(video)
    if probe["duration"] <= 0:
        raise Stage6FinishError(f"{job['job_id']}: zero duration")
    positions = [probe["duration"] * fraction for fraction in (0.02, 0.18, 0.34, 0.50, 0.66, 0.82)]
    frames = [_frame(video, min(at, max(0.0, probe["duration"] - 0.04))) for at in positions]
    plate = Image.open(attempt / str(job["first_plate"]["path"])).convert("RGB")
    temporal = [_mean_abs(frames[index], frames[index + 1]) for index in range(len(frames) - 1)]
    expected = float(job.get("seconds") or 0)
    metrics = {
        "candidate_id": job["candidate_id"], "job_id": job["job_id"],
        "video": str(video.relative_to(attempt)), "sha256": _sha(video),
        "probe": probe, "first_plate_mae": round(_mean_abs(plate, frames[0]), 5),
        "mean_temporal_change": round(sum(temporal) / max(1, len(temporal)), 5),
        "mechanical_pass": (
            probe["width"] == int(job["width"]) and probe["height"] == int(job["height"])
            and probe["duration"] >= expected * 0.90
        ),
        "variation_strategy": job.get("variation_strategy", "base_execution"),
    }
    return metrics, frames


def _contact_sheet(rows: list[tuple[dict, list[Image.Image]]], target: Path) -> Path:
    if not rows or not rows[0][1]:
        raise Stage6FinishError("cannot build an empty contact sheet")
    source_width, source_height = rows[0][1][0].size
    thumb = ((196, max(1, round(196 * source_height / source_width)))
             if source_width >= source_height
             else (max(1, round(196 * source_width / source_height)), 196))
    label_width = 150
    row_height = thumb[1] + 24
    canvas = Image.new("RGB", (label_width + thumb[0] * 6, 40 + row_height * len(rows)), "#10151b")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    draw.text((10, 10), "Candidate rows; time runs left to right", fill="white", font=font)
    for index, (metrics, frames) in enumerate(rows):
        y = 40 + index * row_height
        draw.text((10, y + 8), metrics["candidate_id"], fill="#7bdff2", font=font)
        draw.text((10, y + 28), str(metrics["variation_strategy"]), fill="#d8dee9", font=font)
        draw.text((10, y + 48), f"plate mae {metrics['first_plate_mae']}", fill="#d8dee9", font=font)
        for frame_index, frame in enumerate(frames):
            image = frame.copy()
            image.thumbnail(thumb, Image.Resampling.LANCZOS)
            x = label_width + frame_index * thumb[0]
            canvas.paste(image, (x + (thumb[0] - image.width) // 2, y))
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(target)
    return target


def _data_url(path: Path, max_side: int = 1800) -> str:
    image = Image.open(path).convert("RGB")
    image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=88)
    return "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode("ascii")


def _parse_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.S)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def _ai_review(prompt: str, plate: Path, sheet: Path, valid_ids: set[str]) -> tuple[dict, list[dict]]:
    model = os.environ.get("AI_VIDEO_REVIEW_MODEL", "gpt-5.4")
    failures: list[dict] = []
    for attempt_number in range(1, 11):
        try:
            response = _client().responses.create(
                model=model,
                reasoning={"effort": "medium"},
                input=[{"role": "user", "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_text", "text": "Approved first plate:"},
                    {"type": "input_image", "image_url": _data_url(plate)},
                    {"type": "input_text", "text": "Candidate time-strip comparison:"},
                    {"type": "input_image", "image_url": _data_url(sheet)},
                ]}],
            )
            review = _parse_json(response.output_text)
            selected = str(review.get("selected_candidate") or "")
            if selected not in valid_ids or review.get("decision") not in {"pass", "retry"}:
                raise ValueError("review JSON has an invalid decision or candidate id")
            review["model"] = model
            review["reviewed_at"] = _now()
            review["provider_attempt"] = attempt_number
            return review, failures
        except Exception as error:  # provider and schema failures share the ten-attempt budget
            failures.append({"attempt": attempt_number, "error_type": type(error).__name__,
                             "error": str(error)[:500], "at": _now()})
            if attempt_number < 10:
                time.sleep(min(20, attempt_number * 2))
    raise Stage6FinishError(json.dumps({"ai_review_failures": failures}, ensure_ascii=False))


def review(attempt: Path) -> dict:
    attempt = attempt.resolve()
    _, manifest = _manifest(attempt)
    if not manifest.get("all_completed"):
        raise Stage6FinishError("all prepared Stage 06 candidates must finish before AI review")
    root = _motion_root(attempt) / "qa" / "ai-fast-track"
    pack = _json(_motion_root(attempt) / "prompts" / "shot-pack.json")
    pack_by_shot = {str(item["shot"]): item for item in pack.get("shots", [])}
    jobs_by_shot: dict[str, list[dict]] = {}
    for job in manifest.get("jobs", []):
        if job.get("status") == "completed":
            jobs_by_shot.setdefault(str(job["shot_id"]), []).append(job)
    prior_path = root / "selection.json"
    prior = _json(prior_path) if prior_path.is_file() else {}
    prior_by_shot = {item["shot_id"]: item for item in prior.get("shots", [])}
    selections = []
    needs_retry = []
    for shot_id in sorted(jobs_by_shot):
        jobs = sorted(jobs_by_shot[shot_id], key=lambda item: int(item["candidate_number"]))
        rows = [_candidate_metrics(attempt, job) for job in jobs]
        sheet = _contact_sheet(rows, root / "contact-sheets" / f"{shot_id}.jpg")
        metrics = [item[0] for item in rows]
        latest_count = len(jobs)
        previous = prior_by_shot.get(shot_id)
        if previous and previous.get("decision") == "pass" and previous.get("reviewed_candidate_count") == latest_count:
            selections.append(previous)
            continue
        base_prompt = str(jobs[0].get("base_prompt") or jobs[0].get("prompt") or "")
        review_prompt = (
            "You are the semantic fast-track reviewer for a generated production shot. Compare every "
            "candidate row against the approved first plate and the motion contract below. Time runs "
            "left to right in each row. Select the best coherent candidate. Reject a candidate for "
            "identity/count drift, invented people/props/text, impossible anatomy/contact, wrong action "
            "or direction, camera/light discontinuity, disappearance, topology changes, or excessive/" 
            "insufficient motion. Ignore all generated audio. Return JSON only with keys: decision "
            "('pass' if at least one candidate is production-usable, otherwise 'retry'), "
            "selected_candidate, summary, failed_criteria (array of concise concrete strings), "
            "accepted_defects (array), and scores (object mapping every candidate id to integer 1..5). "
            f"Valid candidate ids: {', '.join(m['candidate_id'] for m in metrics)}.\n\n"
            f"Motion contract:\n{base_prompt}\n\nMechanical observations:\n"
            + json.dumps(metrics, ensure_ascii=False)
        )
        plate = attempt / str(jobs[0]["first_plate"]["path"])
        try:
            verdict, provider_failures = _ai_review(
                review_prompt, plate, sheet, {m["candidate_id"] for m in metrics})
        except Stage6FinishError as error:
            mechanically_valid = [m for m in metrics if m["mechanical_pass"]] or metrics
            picked = min(mechanically_valid, key=lambda m: (m["first_plate_mae"], -m["mean_temporal_change"]))
            verdict = {
                "decision": "retry" if latest_count < 10 else "pass",
                "selected_candidate": picked["candidate_id"],
                "summary": "AI provider review exhausted; deterministic mechanical fallback retained.",
                "failed_criteria": ["semantic AI review unavailable after ten attempts"],
                "accepted_defects": (["semantic AI review unavailable after ten attempts"]
                                     if latest_count >= 10 else []),
                "scores": {m["candidate_id"]: (3 if m["candidate_id"] == picked["candidate_id"] else 2)
                           for m in metrics},
                "model": None, "reviewed_at": _now(), "provider_attempt": 10,
            }
            provider_failures = [{"error": str(error)[:2000]}]
        selected = next(m for m in metrics if m["candidate_id"] == verdict["selected_candidate"])
        exhausted = latest_count >= 10
        if verdict["decision"] == "retry" and exhausted:
            verdict["decision"] = "pass"
            verdict.setdefault("accepted_defects", []).extend(verdict.get("failed_criteria") or ["attempts exhausted"])
            verdict["selection_reason"] = "max_attempts_exhausted_ai_fast_track"
        else:
            verdict["selection_reason"] = "ai_semantic_pass" if verdict["decision"] == "pass" else "retry_required"
        record = {
            "shot_id": shot_id, **verdict, "review_mode": "ai_fast_track",
            "reviewer": "codex-ai-fast-track-stage6", "reviewed_candidate_count": latest_count,
            "selected_video": selected["video"], "selected_video_sha256": selected["sha256"],
            "contact_sheet": str(sheet.relative_to(attempt)), "candidate_metrics": metrics,
            "provider_failures": provider_failures,
        }
        selections.append(record)
        if record["decision"] == "retry":
            needs_retry.append({"shot_id": shot_id, "feedback": "; ".join(record.get("failed_criteria") or [])})
    payload = {
        "schema_version": "stage6-ai-fast-track-selection.v1", "created_at": _now(),
        "attempt": str(attempt), "reviewer": "codex-ai-fast-track-stage6",
        "audio_excluded_from_review": True, "shots": selections,
        "needs_retry": needs_retry, "all_selected": not needs_retry,
    }
    root.mkdir(parents=True, exist_ok=True)
    prior_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def prepare_packets(attempt: Path) -> dict:
    """Build local-only temporal contact sheets without calling any external reviewer."""
    attempt = attempt.resolve()
    _, manifest = _manifest(attempt)
    if not manifest.get("all_completed"):
        raise Stage6FinishError("all prepared Stage 06 candidates must finish before packet creation")
    root = _motion_root(attempt) / "qa" / "ai-fast-track"
    jobs_by_shot: dict[str, list[dict]] = {}
    for job in manifest.get("jobs", []):
        if job.get("status") == "completed":
            jobs_by_shot.setdefault(str(job["shot_id"]), []).append(job)
    shots = []
    for shot_id in sorted(jobs_by_shot):
        jobs = sorted(jobs_by_shot[shot_id], key=lambda item: int(item["candidate_number"]))
        rows = [_candidate_metrics(attempt, job) for job in jobs]
        sheet = _contact_sheet(rows, root / "contact-sheets" / f"{shot_id}.jpg")
        shots.append({
            "shot_id": shot_id,
            "motion_contract": str(jobs[0].get("base_prompt") or jobs[0].get("prompt") or ""),
            "first_plate": jobs[0]["first_plate"],
            "contact_sheet": str(sheet.relative_to(attempt)),
            "candidate_metrics": [item[0] for item in rows],
        })
    packet = {
        "schema_version": "stage6-local-ai-review-packet.v1", "created_at": _now(),
        "attempt": str(attempt), "privacy": "local_only_no_external_api_upload",
        "audio_excluded": True, "shots": shots,
    }
    root.mkdir(parents=True, exist_ok=True)
    path = root / "local-review-packet.json"
    path.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"packet": str(path), "shot_count": len(shots),
            "contact_sheets": [item["contact_sheet"] for item in shots]}


def local_preselect(attempt: Path) -> dict:
    """Create a privacy-safe provisional cut while semantic Codex review remains local."""
    attempt = attempt.resolve()
    prepare_packets(attempt)
    root = _motion_root(attempt) / "qa" / "ai-fast-track"
    packet = _json(root / "local-review-packet.json")
    shots = []
    for item in packet["shots"]:
        metrics = list(item["candidate_metrics"])
        eligible = [metric for metric in metrics if metric["mechanical_pass"]] or metrics
        changes = sorted(float(metric["mean_temporal_change"]) for metric in eligible)
        median_change = changes[len(changes) // 2]
        selected = min(
            eligible,
            key=lambda metric: (
                abs(float(metric["mean_temporal_change"]) - median_change) * 0.35
                + float(metric["first_plate_mae"]) * 0.65,
                metric["candidate_id"],
            ),
        )
        shots.append({
            "shot_id": item["shot_id"], "decision": "provisional_local_preselection",
            "selected_candidate": selected["candidate_id"],
            "selected_video": selected["video"], "selected_video_sha256": selected["sha256"],
            "summary": "Privacy-safe mechanical preselection; local Codex semantic review packet retained.",
            "failed_criteria": [], "accepted_defects": [],
            "selection_reason": "local_temporal_and_first_plate_metrics",
            "review_mode": "local_private_preselection", "reviewer": "stage6-local-metrics",
            "reviewed_candidate_count": len(metrics), "reviewed_at": _now(),
            "contact_sheet": item["contact_sheet"], "candidate_metrics": metrics,
            "semantic_review_pending": True,
        })
    payload = {
        "schema_version": "stage6-ai-fast-track-selection.v1", "created_at": _now(),
        "attempt": str(attempt), "reviewer": "stage6-local-metrics",
        "privacy": "local_only_no_external_api_upload", "audio_excluded_from_review": True,
        "shots": shots, "needs_retry": [], "all_selected": True,
        "provisional": True, "semantic_review_pending": True,
    }
    path = root / "selection.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def apply_local_review(attempt: Path, verdicts_path: Path) -> dict:
    """Apply a human-visible, local semantic review without an external API call."""
    attempt = attempt.resolve()
    root = _motion_root(attempt) / "qa" / "ai-fast-track"
    if not (root / "local-review-packet.json").is_file():
        prepare_packets(attempt)
    packet = _json(root / "local-review-packet.json")
    verdicts = _json(verdicts_path.resolve())
    verdict_by_shot = {str(item["shot_id"]): item for item in verdicts.get("shots", [])}
    expected = {str(item["shot_id"]) for item in packet["shots"]}
    if set(verdict_by_shot) != expected:
        raise Stage6FinishError(
            f"local verdict coverage mismatch: expected={sorted(expected)} "
            f"got={sorted(verdict_by_shot)}"
        )
    reviewed_at = _now()
    selections = []
    for item in packet["shots"]:
        shot_id = str(item["shot_id"])
        verdict = verdict_by_shot[shot_id]
        metrics = list(item["candidate_metrics"])
        selected_id = str(verdict["selected_candidate"])
        selected = next(
            (metric for metric in metrics if str(metric["candidate_id"]) == selected_id),
            None,
        )
        if selected is None:
            raise Stage6FinishError(f"{shot_id}: unknown selected candidate {selected_id}")
        accepted_defects = list(verdict.get("accepted_defects") or [])
        selections.append({
            "shot_id": shot_id,
            "decision": "pass",
            "selected_candidate": selected_id,
            "selected_video": selected["video"],
            "selected_video_sha256": selected["sha256"],
            "summary": str(verdict.get("summary") or "Local semantic review completed."),
            "failed_criteria": accepted_defects,
            "accepted_defects": accepted_defects,
            "selection_reason": (
                "user_single_candidate_policy_with_accepted_defects"
                if accepted_defects else "local_semantic_pass"
            ),
            "review_mode": "ai_fast_track_local_semantic",
            "reviewer": str(verdicts.get("reviewer") or "codex-ai-fast-track-local-semantic"),
            "reviewed_candidate_count": len(metrics),
            "reviewed_at": reviewed_at,
            "contact_sheet": item["contact_sheet"],
            "candidate_metrics": metrics,
            "semantic_review_pending": False,
        })
    payload = {
        "schema_version": "stage6-ai-fast-track-selection.v1",
        "created_at": reviewed_at,
        "attempt": str(attempt),
        "reviewer": str(verdicts.get("reviewer") or "codex-ai-fast-track-local-semantic"),
        "privacy": "local_only_no_external_api_upload",
        "audio_excluded_from_review": True,
        "candidate_policy": str(verdicts.get("candidate_policy") or "local_semantic_selection"),
        "shots": selections,
        "needs_retry": [],
        "all_selected": True,
        "provisional": False,
        "semantic_review_pending": False,
    }
    path = root / "selection.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def append_retries(attempt: Path) -> dict:
    attempt = attempt.resolve()
    manifest_path, manifest = _manifest(attempt)
    selection = _json(_motion_root(attempt) / "qa" / "ai-fast-track" / "selection.json")
    appended = []
    for request in selection.get("needs_retry", []):
        shot_id = str(request["shot_id"])
        jobs = [job for job in manifest["jobs"] if job["shot_id"] == shot_id]
        next_number = max(int(job["candidate_number"]) for job in jobs) + 1
        if next_number > 10:
            continue
        template = min(jobs, key=lambda item: int(item["candidate_number"]))
        candidate_id = f"C{next_number:02d}"
        prompt, strategy = varied_prompt(str(template.get("base_prompt") or template["prompt"]),
                                         next_number, str(request.get("feedback") or ""))
        job = {key: value for key, value in template.items() if key not in {
            "generation", "output_sha256", "server", "completed_at"
        }}
        job.update({
            "job_id": f"{shot_id}-{candidate_id}", "candidate_id": candidate_id,
            "candidate_number": next_number, "status": "prepared",
            "seed": _seed(load_contract(attempt).digest, shot_id, next_number),
            "variation_strategy": strategy, "prompt": prompt,
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "output_dir": str(Path(_motion_root(attempt).name) / "output" / "candidates" / shot_id / candidate_id),
        })
        manifest["jobs"].append(job)
        appended.append(job["job_id"])
    manifest["job_count"] = len(manifest["jobs"])
    manifest["completed_count"] = sum(job.get("status") == "completed" for job in manifest["jobs"])
    manifest["all_completed"] = manifest["completed_count"] == manifest["job_count"]
    manifest["updated_at"] = _now()
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"appended": appended, "job_count": manifest["job_count"]}


def stitch(attempt: Path) -> dict:
    attempt = attempt.resolve()
    selection_path = _motion_root(attempt) / "qa" / "ai-fast-track" / "selection.json"
    selection = _json(selection_path)
    if not selection.get("all_selected"):
        raise Stage6FinishError("cannot stitch before every shot is selected")
    contract = load_contract(attempt)
    edit_frame = contract.frame_for_stage("07-edit") or contract.frame
    pack = _json(_motion_root(attempt) / "prompts" / "shot-pack.json")
    pack_by_shot = {str(item["shot"]): item for item in pack.get("shots", [])}
    edit_root = attempt / "07-edit"
    normalized = edit_root / "work" / "normalized"
    normalized.mkdir(parents=True, exist_ok=True)
    ordered = [item for item in sorted(selection["shots"], key=lambda item: item["shot_id"])
               if (pack_by_shot.get(item["shot_id"]) or {}).get("included_in_timeline", True)]
    segments = []
    for index, item in enumerate(ordered, start=1):
        source = attempt / str(item["selected_video"])
        card = pack_by_shot.get(item["shot_id"]) or {}
        seconds = float(card.get("edit_seconds") or _probe(source)["duration"])
        temporal = card.get("temporal_design") or {}
        head = float(temporal.get("head_handle_seconds") or 0)
        playback_rate = float((card.get("retime_plan") or {}).get("source_playback_rate") or 1)
        if playback_rate <= 0:
            playback_rate = 1.0
        source_body = seconds * playback_rate
        target = normalized / f"{index:03d}-{item['shot_id']}-{item['selected_candidate']}.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error", "-ss", f"{head:.3f}",
            "-i", str(source), "-t", f"{source_body:.3f}",
            "-an", "-vf", f"setpts=PTS/{playback_rate:.6f},"
            f"fps={edit_frame.fps},"
            f"scale={edit_frame.width}:{edit_frame.height}:force_original_aspect_ratio=decrease,"
            f"pad={edit_frame.width}:{edit_frame.height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", str(target)
        ], check=True)
        segments.append({"shot_id": item["shot_id"], "candidate_id": item["selected_candidate"],
                         "source": str(source.relative_to(attempt)), "normalized": str(target.relative_to(attempt)),
                         "seconds": seconds, "source_trim_in_seconds": head,
                         "source_playback_rate": playback_rate,
                         "temporal_mode": temporal.get("temporal_mode"),
                         "sha256": _sha(target)})
    concat_file = edit_root / "work" / "concat.txt"
    concat_file.write_text(
        "".join(f"file '{(attempt / item['normalized']).resolve()}'\n" for item in segments),
        encoding="utf-8",
    )
    output = edit_root / "output" / f"{attempt.parent.parent.name}-{attempt.name}-fast-track-rough-cut.mp4"
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", str(concat_file), "-c", "copy", str(output)], check=True)
    probe = _probe(output)
    receipt = {
        "schema_version": "stage7-fast-track-stitch-receipt.v1", "created_at": _now(),
        "attempt": str(attempt), "selection": str(selection_path.relative_to(attempt)),
        "selection_sha256": _sha(selection_path), "segments": segments,
        "audio_policy": "generated_audio_discarded; silent rough cut", "output": str(output.relative_to(attempt)),
        "output_sha256": _sha(output), "probe": probe,
    }
    (edit_root / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description="AI-review and stitch a fast-track Stage 06 attempt")
    parser.add_argument("attempt", type=Path)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--review", action="store_true")
    actions.add_argument("--prepare-packets", action="store_true")
    actions.add_argument("--local-preselect", action="store_true")
    actions.add_argument("--apply-local-review", type=Path)
    actions.add_argument("--append-retries", action="store_true")
    actions.add_argument("--stitch", action="store_true")
    args = parser.parse_args()
    result = (review(args.attempt) if args.review else
              prepare_packets(args.attempt) if args.prepare_packets else
              local_preselect(args.attempt) if args.local_preselect else
              apply_local_review(args.attempt, args.apply_local_review) if args.apply_local_review else
              append_retries(args.attempt) if args.append_retries else stitch(args.attempt))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
