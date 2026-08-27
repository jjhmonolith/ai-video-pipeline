"""Production Stage 06 runner for MiniMax H3 motion candidates.

The runner consumes only the mode-approved Stage 05 handoff.  It prepares one
deterministic first take per shot.  Review may append one varied retry at a
time, up to ten total; C01..C10 are takes of the same shot, never alternate
angles or an upfront best-of-N batch.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contract import load as load_contract
from .execution_mode import FAST_TRACK_MODE, load_execution_mode
from .h3_runtime import DEFAULT_SERVER, ComfyClient, H3Request, H3Settings, generate
from .generation_harness import MAX_GENERATION_ATTEMPTS, VARIATION_STRATEGIES


SCHEMA = "stage6-motion-manifest.v1"
TERMINAL_JOB_STATUSES = {"completed", "skipped_by_user_single_take"}

class Stage6Error(RuntimeError):
    """Raised when an approved motion input is incomplete or has drifted."""


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _json(path: Path, label: str) -> dict:
    if not path.is_file():
        raise Stage6Error(f"{label}가 없다: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise Stage6Error(f"{label}를 읽을 수 없다: {path}") from error


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _resolve(attempt: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else attempt / path


def _checked_asset(attempt: Path, record: dict, label: str) -> Path:
    path = _resolve(attempt, str(record.get("path") or ""))
    if not path.is_file():
        raise Stage6Error(f"{label}가 없다: {path}")
    expected = str(record.get("sha256") or "")
    if expected and _sha_file(path) != expected:
        raise Stage6Error(f"{label} hash가 Stage 05 승인 뒤 바뀌었다: {path}")
    return path


def _reference_binding(references: list[dict]) -> str:
    lines = [
        "H3 REFERENCE BINDING — Reference images define canonical identity, wardrobe, "
        "architecture and materials only. The approved first plate defines the actual "
        "composition and opening pose. Render one continuous cinematic scene while using the "
        "boards solely as latent identity and design references."
    ]
    for index, item in enumerate(references, start=1):
        identity = item.get("subject_id") or item.get("manual_id") or f"reference-{index}"
        lines.append(f"<Picture {index}> is the approved canonical reference for {identity}.")
    return "\n".join(lines)


def _motion_control_guard(shot: dict) -> str:
    direction = shot.get("screen_direction")
    if direction:
        return (
            "TRACKING COMPOSITION GUARD — Keep the primary subject centered on the approved "
            f"screen track {direction['start_center_normalized']} to "
            f"{direction['end_center_normalized']} with depth intent "
            f"{direction['depth_intent']}. The camera follows continuously at matching speed. "
            "The approved architecture, materials, lighting and subject scale remain coherent."
        )
    return (
        "LOCKED COMPOSITION GUARD — Keep the camera physically locked for every frame and "
        "preserve the exact opening crop, viewpoint, architecture, permanent inventory and "
        "lighting. The primary subject performs only the explicit action timeline. Preserve the "
        "subject's root position, feet and torso except where that timeline specifically requires "
        "a lean, pivot, stance adjustment or other local body movement. Do not suppress, reverse "
        "or replace the requested action, and do not animate any undeclared element."
    )


def _seed(contract_digest: str, shot_id: str, candidate_number: int) -> int:
    base = int(hashlib.sha256(
        f"{contract_digest}:{shot_id}".encode("utf-8")).hexdigest()[:15], 16)
    return base + candidate_number - 1


def variation_clause(candidate_number: int, feedback: str = "") -> tuple[str, str]:
    """Return the runner-owned ordered variation for one semantic attempt."""
    if candidate_number < 1 or candidate_number > len(VARIATION_STRATEGIES):
        raise Stage6Error("Stage 06 semantic candidate number는 1..10이어야 한다")
    strategy = VARIATION_STRATEGIES[candidate_number - 1]
    clauses = {
        "base_contract_execution": "",
        "positive_requirement_restatement": (
            "VARIATION — Render the requested action successfully with stable identity, exact "
            "object count, physically plausible contact and a coherent unchanged environment."
        ),
        "constraint_priority_reordering": (
            "VARIATION PRIORITY — First preserve identity, object count and architecture; second "
            "obey the approved screen track and camera behavior; third complete only the stated action."
        ),
        "identity_and_count_lock_emphasis": (
            "VARIATION IDENTITY LOCK — Every person, character, tool, fixture and furnishing visible "
            "at frame one keeps the same identity, design, count and ownership through the last frame."
        ),
        "spatial_composition_clarification": (
            "VARIATION SPATIAL LOCK — Preserve the opening scene topology, scale relationships and "
            "screen-side assignments while the declared subject follows only its approved path."
        ),
        "physical_contact_and_topology_clarification": (
            "VARIATION CONTACT — Show anatomically plausible reach, grip, contact angle, support and "
            "release. Fixed hubs and mounted parts stay fixed; only the declared moving part moves."
        ),
        "camera_lighting_and_visibility_clarification": (
            "VARIATION VISIBILITY — Use coherent camera following only when the approved track calls "
            "for it. Keep exposure, practical lights and visible scene inventory temporally stable."
        ),
        "temporal_state_and_action_boundary_clarification": (
            "VARIATION TIMELINE — Begin exactly at the approved first plate, perform each stated beat "
            "once in order, and end immediately after the final declared state without a new action."
        ),
        "contradiction_removal_and_negative_space_simplification": (
            "VARIATION CLEAN EXECUTION — Resolve the action using the simplest reading of the timeline "
            "and do not introduce any unstated event, prop, person, state change or reaction."
        ),
        "minimal_scene_rebuild_around_failed_criteria": (
            "VARIATION MINIMAL REBUILD — Keep the first plate as the complete world and animate only "
            "the minimum subject regions strictly required to complete the declared action."
        ),
    }
    parts = [clauses[strategy]] if clauses[strategy] else []
    if feedback.strip():
        parts.append(
            "PRIOR REVIEW FINDINGS — Correct these concrete failures while preserving every other "
            f"approved property: {feedback.strip()}"
        )
    return strategy, "\n".join(parts)


def varied_prompt(base_prompt: str, candidate_number: int, feedback: str = "") -> tuple[str, str]:
    strategy, clause = variation_clause(candidate_number, feedback)
    return (f"{base_prompt.rstrip()}\n\n{clause}" if clause else base_prompt, strategy)


def prepare(attempt: Path, force: bool = False) -> dict:
    attempt = attempt.resolve()
    contract = load_contract(attempt)
    execution_mode = load_execution_mode(attempt)
    fast_track = execution_mode.get("mode") == FAST_TRACK_MODE
    plate_stage = contract.stage_for("plate", "05-plate")
    motion_stage = contract.stage_for("motion", "06-motion")
    handoff_path = attempt / plate_stage / "output" / "h3-conditioning.json"
    pack_path = attempt / motion_stage / "prompts" / "shot-pack.json"
    handoff = _json(handoff_path, "Stage 05 H3 handoff")
    pack = _json(pack_path, "Stage 06 shot pack")
    override_path = attempt / motion_stage / "prompts" / "production-overrides.json"
    overrides = _json(override_path, "Stage 06 production prompt overrides") if override_path.is_file() else {}
    if overrides and overrides.get("schema_version") != "stage6-production-overrides.v1":
        raise Stage6Error("Stage 06 production prompt override schema가 유효하지 않다")
    override_shots = overrides.get("shots") or {}
    if not handoff.get("ready") or handoff.get("status") != "ready":
        raise Stage6Error("Stage 05 H3 handoff가 ready 상태가 아니다")
    if (handoff.get("contract") or {}).get("sha256") != contract.digest:
        raise Stage6Error("Stage 05 H3 handoff 계약 digest가 현재 계약과 다르다")

    frame = handoff.get("contract", {}).get("stage_frame") or {}
    width, height = int(frame.get("width", 0)), int(frame.get("height", 0))
    if (width, height) != (contract.frame.width, contract.frame.height):
        raise Stage6Error("Stage 05 H3 handoff frame이 현재 계약과 다르다")

    pack_shots = {str(item.get("shot")): item for item in pack.get("shots") or []}
    jobs: list[dict[str, Any]] = []
    for shot in handoff.get("shots") or []:
        shot_id = str(shot.get("shot_id") or "")
        card = pack_shots.get(shot_id)
        if not shot_id or not card:
            raise Stage6Error(f"shot pack에 승인 shot이 없다: {shot_id}")
        if "temporal_capability_debt" in (card.get("generation_block_reasons") or []):
            raise Stage6Error(
                f"{shot_id} temporal capability debt가 해결되지 않아 H3 생성할 수 없다")
        override = override_shots.get(shot_id) or {}
        motion_prompt = str(override.get("prompt") or shot.get("motion_prompt") or "").strip()
        if not motion_prompt:
            raise Stage6Error(f"{shot_id} motion prompt가 비어 있다")
        if "SCREEN DIRECTION — unresolved" in motion_prompt or "Do not generate H3" in motion_prompt:
            raise Stage6Error(f"{shot_id} screen direction이 prompt에서 미해결이다")

        first_plate = _checked_asset(attempt, shot.get("first_plate") or {},
                                     f"{shot_id} first plate")
        reference_records = list(shot.get("canonical_stage02_sheets") or [])
        reference_records.extend(shot.get("approved_interaction_manuals") or [])
        if not reference_records:
            raise Stage6Error(f"{shot_id} H3 reference가 없다")
        if len(reference_records) > 9:
            raise Stage6Error(f"{shot_id} H3 reference가 9장을 초과한다")
        reference_paths = [
            _checked_asset(attempt, item, f"{shot_id} reference {index}")
            for index, item in enumerate(reference_records, start=1)
        ]
        base_prompt = "\n\n".join([
            _reference_binding(reference_records),
            motion_prompt,
            _motion_control_guard(shot),
            "OUTPUT — one continuous natural shot. The exact first-plate inventory and the single "
            "primary subject remain the complete visible scene throughout.",
        ])
        seconds = float(card.get("generation_seconds") or card.get("edit_seconds") or 0)
        policy = card.get("candidate_policy") or {}
        if seconds <= 0:
            raise Stage6Error(f"{shot_id} duration이 유효하지 않다")
        if (policy and (int(policy.get("candidate_count", 1)) != 1
                        or int(policy.get("max_attempts", MAX_GENERATION_ATTEMPTS))
                        != MAX_GENERATION_ATTEMPTS)):
            raise Stage6Error(
                f"{shot_id}는 C01 한 take 후 실패 시에만 C10까지 추가하는 정책이어야 한다")
        # Initial preparation is intentionally one take.  stage6_finish's
        # semantic review appends exactly one varied retry only after a fail.
        for number in (1,):
            candidate_id = f"C{number:02d}"
            prompt, variation_strategy = varied_prompt(base_prompt, number)
            jobs.append({
                "job_id": f"{shot_id}-{candidate_id}",
                "shot_id": shot_id,
                "candidate_id": candidate_id,
                "candidate_number": number,
                "status": "prepared",
                "seconds": seconds,
                "seed": _seed(contract.digest, shot_id, number),
                "width": width,
                "height": height,
                "first_plate": {"path": str(first_plate.relative_to(attempt)),
                                "sha256": _sha_file(first_plate)},
                "references": [
                    {**record, "path": str(path.relative_to(attempt))}
                    for record, path in zip(reference_records, reference_paths)
                ],
                "base_prompt": base_prompt,
                "variation_strategy": variation_strategy,
                "prompt": prompt,
                "prompt_sha256": _sha_text(prompt),
                "output_dir": str(Path(motion_stage) / "output" / "candidates" /
                                  shot_id / candidate_id),
            })

    motion_root = attempt / motion_stage
    target = motion_root / "qa" / "manifest.json"
    source = {
        "stage5_handoff": str(handoff_path.relative_to(attempt)),
        "stage5_handoff_sha256": _sha_file(handoff_path),
        "shot_pack": str(pack_path.relative_to(attempt)),
        "shot_pack_sha256": _sha_file(pack_path),
        "production_overrides": (str(override_path.relative_to(attempt))
                                 if override_path.is_file() else None),
        "production_overrides_sha256": (_sha_file(override_path)
                                        if override_path.is_file() else None),
        "execution_mode": execution_mode,
    }
    if target.is_file() and not force:
        existing = _json(target, "Stage 06 manifest")
        if existing.get("source") == source:
            return existing
        raise Stage6Error("Stage 06 입력이 기존 manifest 이후 바뀌었다. --force로 새 manifest를 준비하라")
    manifest = {
        "schema_version": SCHEMA,
        "created_at": _now(),
        "attempt": str(attempt),
        "contract": contract.receipt_block(motion_stage),
        "runtime": pack.get("video_engine"),
        "source": source,
        "execution_mode": execution_mode,
        "candidate_policy": (
            "one take first; append one varied retry after each AI failure; automatic continuation"
            if fast_track else
            "one take first; append one varied retry after each review failure; final human selection required"
        ),
        "selection_contract": {
            "review_mode": "ai_fast_track" if fast_track else "human",
            "human_approval_required": not fast_track,
            "auto_approve_allowed": fast_track,
            "initial_generation_count": 1,
            "append_retry_only_after_review_failure": True,
            "max_varied_attempts_per_artifact": MAX_GENERATION_ATTEMPTS,
            "attempt_10_policy": (
                "record_non_safety_accepted_defects_and_continue"
                if fast_track else "retain_for_human_review"
            ),
        },
        "job_count": len(jobs),
        "completed_count": 0,
        "jobs": jobs,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def _render_job(attempt: Path, job: dict, server: str, timeout: float) -> dict:
    client = ComfyClient(server)
    first = client.upload_image(_resolve(attempt, job["first_plate"]["path"]))
    references = tuple(client.upload_image(_resolve(attempt, item["path"]))
                       for item in job["references"])
    request = H3Request(
        prompt=job["prompt"], width=int(job["width"]), height=int(job["height"]),
        seconds=float(job["seconds"]), seed=int(job["seed"]), first_frame=first,
        references=references, reference_size="match",
        filename_prefix=f"video/ai-video-pipeline/{job['shot_id']}/{job['candidate_id']}",
    )
    destination = attempt / job["output_dir"]
    result = generate(request, destination, H3Settings(), server, timeout)
    files = [Path(path) for path in result.get("files") or []]
    if not files or any(not path.is_file() or path.stat().st_size == 0 for path in files):
        raise Stage6Error(f"{job['job_id']} H3 출력 파일이 없다")
    return {**job, "status": "completed", "server": server,
            "completed_at": _now(), "generation": result,
            "output_sha256": {str(path): _sha_file(path) for path in files}}


def render(attempt: Path, shot_id: str, candidate_number: int, server: str = DEFAULT_SERVER,
           timeout: float = 3600.0, force: bool = False) -> dict:
    attempt = attempt.resolve()
    contract = load_contract(attempt)
    motion_stage = contract.stage_for("motion", "06-motion")
    manifest_path = attempt / motion_stage / "qa" / "manifest.json"
    manifest = prepare(attempt) if not manifest_path.is_file() else _json(
        manifest_path, "Stage 06 manifest")
    candidate_id = f"C{candidate_number:02d}"
    index = next((i for i, item in enumerate(manifest.get("jobs") or [])
                  if item.get("shot_id") == shot_id and item.get("candidate_id") == candidate_id), None)
    if index is None:
        raise Stage6Error(f"Stage 06 job이 없다: {shot_id}-{candidate_id}")
    job = manifest["jobs"][index]
    if job.get("status") == "skipped_by_user_single_take":
        return job
    existing = sorted((attempt / job["output_dir"]).glob("*"))
    if existing and job.get("status") == "completed" and not force:
        return job
    print(f"START {job['job_id']} seed={job['seed']} seconds={job['seconds']}", flush=True)
    completed = _render_job(attempt, job, server, timeout)
    print(f"DONE {job['job_id']} {completed['generation']['elapsed_seconds']}s", flush=True)
    manifest["jobs"][index] = completed
    manifest["completed_count"] = sum(
        item.get("status") == "completed" for item in manifest["jobs"])
    manifest["skipped_count"] = sum(
        item.get("status") == "skipped_by_user_single_take" for item in manifest["jobs"])
    manifest["terminal_count"] = sum(
        item.get("status") in TERMINAL_JOB_STATUSES for item in manifest["jobs"])
    manifest["updated_at"] = _now()
    manifest["all_completed"] = manifest["terminal_count"] == manifest["job_count"]
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    receipt = attempt / motion_stage / "receipt.json"
    receipt.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return completed


def main() -> int:
    parser = argparse.ArgumentParser(description="approved Stage 05 plates를 H3 motion으로 생성")
    parser.add_argument("attempt", type=Path)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--shot")
    parser.add_argument("--candidate", type=int, default=1)
    parser.add_argument("--server", default=DEFAULT_SERVER)
    parser.add_argument("--timeout", type=float, default=3600.0)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.render:
        if not args.shot:
            parser.error("--render에는 --shot이 필요하다")
        result = render(args.attempt, args.shot, args.candidate, args.server,
                        args.timeout, args.force)
    else:
        result = prepare(args.attempt, args.force)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
