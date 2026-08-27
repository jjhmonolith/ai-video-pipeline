"""Production stage 05: approved interaction manuals and first-frame plates.

The image model is deliberately outside this module.  ``prepare`` writes an
immutable Codex work order.  For plates, every reference passes one global AI
preflight barrier before an interactive ImageGen surface may render a start
image.  The surface renders one attempt, compares it with those references,
and retries only after failure, for at most ten varied attempts. ``finalize``
validates the selected pixels and both review logs. Finalization never approves
a plate. In normal mode a human completes the generated review packet; in an
explicitly selected fast-track attempt the AI completes it. ``apply-review``
promotes only a mode-bound, explicitly approved plate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from .contract import Contract, ContractError, load as load_contract
from .lifecycle import read_direction_impact, read_premise_state
from .generation_harness import (
    HARNESS_SCHEMA,
    MAX_GENERATION_ATTEMPTS,
    VARIATION_STRATEGIES,
    harness_contract,
    retry_prompt as adaptive_retry_prompt,
    variation_strategy,
)
from .execution_mode import (
    FAST_TRACK_MODE,
    ExecutionModeError,
    load_execution_mode,
)
from .sheets import (
    PIXEL_TOLERANCE_MAX_PIXELS,
    PIXEL_TOLERANCE_RATIO,
    materialize_with_pixel_tolerance,
    pixel_tolerance,
    source_within_pixel_tolerance,
)


STAGE_ROLE = "plate"
STAGE_FALLBACK = "05-plate"
CODEX_SURFACES = {"desktop", "cli", "ide", "cloud", "unknown"}
UNIVERSAL_RENDER_CONTRACT_VERSION = "stage5-universal-render.v2"
PLATE_AI_REVIEW_SCHEMA = "stage5-plate-ai-retry-review.v1"
PLATE_AI_ATTEMPT_REVIEW_SCHEMA = "stage5-plate-ai-attempt-review.v1"
PLATE_REFERENCE_REVIEW_SCHEMA = "stage5-plate-reference-preflight.v1"
PLATE_MAX_ATTEMPTS = MAX_GENERATION_ATTEMPTS
PLATE_REFERENCE_CRITERIA = (
    "the reference image is readable and matches its declared subject and role",
    "identity, topology, proportions, materials and part count are internally coherent",
    "the interaction target and mechanically relevant geometry are visible when required",
    "no unrelated subject, contradictory design state or obvious generation defect compromises conditioning",
)
PLATE_REFERENCE_COMPARISON_CRITERIA = (
    "the start image matches every approved reference in identity, topology, proportions, materials and part count",
    "the start image contains no subject, design-state or interaction-geometry contradiction relative to the approved references",
)
UNIVERSAL_RENDER_RULES = (
    "Obey gravity, support and balance. Nothing floats; every standing person, vehicle, object "
    "and loose part has a physically credible support or suspension relation.",
    "Preserve rigid-body geometry, topology, scale and part count. Do not fuse, duplicate, detach, "
    "stretch or spontaneously redesign subjects between views or panels.",
    "Contacts, joints, hands, tools, seats, restraints, tyres and ground interfaces must be "
    "anatomically and mechanically plausible, with no penetration or impossible clearance.",
    "When acceleration, braking, turning, impact or another force is depicted, every affected body "
    "and secondary element must respond to the same force vector. Show coherent displacement through "
    "the torso, shoulders, head, facial soft tissue, hair, clothing, restraints and supports; an "
    "expressive face on an otherwise static body is not sufficient.",
    "Honor every upstream lighting contract. Use one coherent set of light sources per declared "
    "scene; do not flip the key side, add a contradictory light, or detach cast and contact shadows.",
    "Shadow direction, softness, occlusion, reflections, highlights and material response must agree "
    "with the same light sources, world geometry and camera viewpoint.",
    "Perspective, scale, depth, occlusion and reflections must be mutually consistent. Mirrors and "
    "glazing may reflect only subjects and lights that can physically occupy the scene.",
    "Treat each frame or panel as one coherent instant. No double exposure, temporal morph, repeated "
    "limbs, repeated wheels, ghost subjects or multiple action phases inside one image.",
    "Shot-specific upstream identity, action, geometry, camera, lighting and shadow constraints refine "
    "this universal contract and are authoritative when they are more specific.",
)


class Stage5Error(RuntimeError):
    """Stage 05 cannot safely continue."""


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _short_sha(path: Path) -> str:
    return _sha(path)[:16]


def _text_sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _json(path: Path, label: str) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise Stage5Error(f"{label}가 없다: {path}") from error
    except json.JSONDecodeError as error:
        raise Stage5Error(f"{label} JSON 오류: {path}: {error}") from error
    if not isinstance(payload, dict):
        raise Stage5Error(f"{label}는 JSON object여야 한다: {path}")
    return payload


def _stage_name(contract: Contract) -> str:
    return contract.stage_for(STAGE_ROLE, STAGE_FALLBACK)


def _stage_dir(attempt: Path, contract: Contract) -> Path:
    return attempt / _stage_name(contract)


def _design_path(attempt: Path, contract: Contract) -> Path:
    return (attempt / contract.stage_for("shot_design", "04-shot-design") /
            "output" / "shot-cards.json")


def _load_design(attempt: Path, contract: Contract) -> tuple[dict, Path]:
    path = _design_path(attempt, contract)
    design = _json(path, "04-shot-design shot cards")
    recorded = (design.get("contract") or {}).get("sha256")
    if recorded != contract.digest:
        raise Stage5Error(
            f"shot cards 작성 뒤 계약이 바뀌었다 design={recorded} current={contract.digest}. "
            "04-shot-design을 다시 컴파일한다")
    if design.get("schema_version") not in {"shot-design.v1", "shot-design.v2"}:
        raise Stage5Error(f"지원하지 않는 shot design {design.get('schema_version')!r}")
    return design, path


def _problem(code: str, message: str, *, shot_id: str | None = None,
             manual_id: str | None = None, scope: str = "global") -> dict:
    return {"code": code, "message": message, "scope": scope,
            "shot_id": shot_id, "manual_id": manual_id}


def _current_sheet_state(attempt: Path, contract: Contract) -> dict:
    path = (attempt / contract.stage_for("sheet", "02-sheet") /
            "qa" / "semantic-review.json")
    if not path.exists():
        return {"path": str(path), "reference_ready": False, "status": "missing"}
    payload = _json(path, "02-sheet semantic review")
    return {"path": str(path), "reference_ready": bool(payload.get("reference_ready")),
            "status": payload.get("status"), "payload": payload}


def _manuals(design: dict) -> list[tuple[str, dict]]:
    found: dict[str, tuple[str, dict]] = {}
    for shot in design.get("shots") or []:
        shot_id = str(shot.get("shot_id", ""))
        plan = shot.get("supplemental_reference_plan") or {}
        for manual in plan.get("manuals") or []:
            manual_id = str(manual.get("manual_id", ""))
            if manual_id:
                found.setdefault(manual_id, (shot_id, manual))
    return list(found.values())


def _review_path(stage: Path, asset_type: str, asset_id: str) -> Path:
    return stage / "qa" / "reviews" / f"{asset_type}-{asset_id}.json"


def _approved_manual(stage: Path, manual_id: str) -> tuple[bool, str | None]:
    output = stage / "output" / "manuals" / f"{manual_id}.png"
    review_path = _review_path(stage, "manual", manual_id)
    if not output.is_file() or not review_path.is_file():
        return False, "approved output 또는 review가 없다"
    review = _json(review_path, f"manual review {manual_id}")
    if review.get("decision") != "approved" or not str(review.get("reviewer") or "").strip():
        return False, "AI preflight 승인 기록이 없다"
    if review.get("approved_output_sha256") != _sha(output):
        return False, "승인 뒤 manual output이 바뀌었다"
    return True, None


def audit_inputs(attempt: Path) -> dict:
    """Audit production readiness without changing the attempt."""
    attempt = attempt.resolve()
    contract = load_contract(attempt)
    execution_mode = load_execution_mode(attempt)
    design, design_path = _load_design(attempt, contract)
    stage = _stage_dir(attempt, contract)
    blockers: list[dict] = []
    warnings: list[dict] = []

    premise = read_premise_state(attempt, contract)
    if not premise.get("form_ok"):
        blockers.append(_problem(
            "premise-form-invalid",
            "01-premise 형식·근거 검사가 완료되지 않았다"))
    elif not premise.get("human_approved"):
        warnings.append(_problem(
            "premise-human-approval-not-recorded",
            "01-premise 사람 승인은 기록되지 않았지만 04→05 자동 전환을 차단하지 않는다",
            scope="nonblocking_approval"))
    impact = read_direction_impact(attempt, contract)
    if not impact.get("downstream_allowed", True):
        blockers.append(_problem(
            "direction-revalidation-required",
            f"direction 변경 영향 재검토가 {impact.get('unresolved_count', 0)}건 남아 있다"))
    sheet_state = _current_sheet_state(attempt, contract)
    if not sheet_state.get("reference_ready"):
        blockers.append(_problem(
            "stage02-semantic-approval-required",
            "02-sheet semantic review가 reference_ready=true가 아니다"))

    semantic_path = (attempt / contract.stage_for("shot_design", "04-shot-design") /
                     "qa" / "semantic-check.json")
    if not semantic_path.exists():
        blockers.append(_problem("stage04-check-missing", "04-shot-design semantic check가 없다"))
    else:
        semantic = _json(semantic_path, "04-shot-design semantic check")
        if not semantic.get("form_ok"):
            blockers.append(_problem("stage04-form-invalid", "04-shot-design 형식 검사가 실패했다"))
        for warning in semantic.get("warnings") or []:
            code = warning.get("code")
            if code in {"manual-atomic-segmentation-required", "sublocation-unresolved"}:
                blockers.append(_problem(
                    code, str(warning.get("message", code)),
                    shot_id=warning.get("shot_id"), scope="shot"))

    inventory = (design.get("reference_status") or {}).get("canonical_boards") or {}
    states = design.get("states") or {}
    shots = design.get("shots") or []
    for shot in shots:
        shot_id = str(shot.get("shot_id", ""))
        pair = shot.get("state_pair") or {}
        state_id = pair.get("start_state_id")
        state = states.get(state_id) or {}
        if not str(state.get("prompt") or "").strip():
            blockers.append(_problem(
                "plate-prompt-missing", f"{state_id} 시작판 프롬프트가 없다",
                shot_id=shot_id, scope="shot"))
        required = ((shot.get("reference_requirements") or {})
                    .get("canonical_stage02_sheet_subject_ids") or [])
        for subject_id in required:
            record = inventory.get(subject_id) or {}
            raw_path = record.get("path")
            path = Path(str(raw_path)) if raw_path else None
            if path and not path.is_absolute():
                path = attempt / path
            if not path or not path.is_file():
                blockers.append(_problem(
                    "stage02-sheet-missing", f"{subject_id} canonical sheet가 없다",
                    shot_id=shot_id, scope="shot"))
            elif record.get("sha256") and record.get("sha256") != _short_sha(path):
                blockers.append(_problem(
                    "stage02-sheet-drift", f"{subject_id} canonical sheet hash가 4단계 이후 바뀌었다",
                    shot_id=shot_id, scope="shot"))
        direction = (shot.get("motion_control") or {}).get("screen_direction_contract") or {}
        if direction.get("required") and direction.get("generation_blocked_until_resolved"):
            warnings.append(_problem(
                "screen-direction-after-selection-required",
                "시작판 선택 뒤 start/end 좌표와 depth intent 승인이 필요하다",
                shot_id=shot_id, scope="post_selection"))

    for shot_id, manual in _manuals(design):
        manual_id = str(manual.get("manual_id"))
        if manual.get("unresolved_contract_fields"):
            blockers.append(_problem(
                "interaction-manual-spec-unresolved",
                f"설명서 계약 필드가 미해결이다: {manual.get('unresolved_contract_fields')}",
                shot_id=shot_id, manual_id=manual_id, scope="manual"))
        if not str(manual.get("image_generation_prompt") or "").strip():
            blockers.append(_problem(
                "interaction-manual-prompt-blocked",
                "정식 image_generation_prompt가 없다. BLOCKED DRAFT는 production에 사용할 수 없다",
                shot_id=shot_id, manual_id=manual_id, scope="manual"))
        approved, reason = _approved_manual(stage, manual_id)
        if not approved:
            warnings.append(_problem(
                "interaction-manual-approval-pending", reason or "사람 승인 대기",
                shot_id=shot_id, manual_id=manual_id, scope="manual_approval"))

    deduped = []
    seen = set()
    for item in blockers:
        key = (item["code"], item.get("shot_id"), item.get("manual_id"))
        if key not in seen:
            deduped.append(item)
            seen.add(key)
    blocker_scopes = {item["scope"] for item in deduped}
    manual_prompt_ready = not any(scope in {"global", "manual"} for scope in blocker_scopes)
    return {
        "schema_version": "stage5-input-audit.v1",
        "checked_at": _now(),
        "attempt": str(attempt),
        "contract": contract.receipt_block(_stage_name(contract)),
        "source": str(design_path.relative_to(attempt)),
        "source_sha256": _short_sha(design_path),
        "counts": {"shots": len(shots), "start_plate_prompts": sum(
            bool(str((states.get((shot.get("state_pair") or {}).get("start_state_id")) or {})
                     .get("prompt") or "").strip()) for shot in shots),
            "required_manuals": len(_manuals(design)),
            "ready_manual_prompts": sum(
                bool(str(manual.get("image_generation_prompt") or "").strip()) and
                not manual.get("unresolved_contract_fields")
                for _, manual in _manuals(design)),
        },
        "premise_state": premise,
        "direction_impact": {"downstream_allowed": impact.get("downstream_allowed", True),
                             "unresolved_count": impact.get("unresolved_count", 0)},
        "sheet_state": {k: v for k, v in sheet_state.items() if k != "payload"},
        "blockers": deduped,
        "execution_mode": execution_mode,
        "warnings": warnings,
        "manual_generation_ready": manual_prompt_ready and not deduped,
        "plate_generation_ready": not deduped and not any(
            item["code"] == "interaction-manual-approval-pending" for item in warnings),
    }


def _render_instruction(plan: Any, quality: str) -> str:
    width, height = plan.target
    orientation = "landscape" if width > height else "portrait" if height > width else "square"
    return (
        "OUTPUT REQUIREMENTS — BINDING\n"
        f"Generate one native {width}x{height}-pixel {orientation} PNG at {quality.upper()} quality. "
        "Render at that native resolution; do not return a smaller preview and do not upscale a "
        "lower-resolution image. Preserve every declared identity, geometry and state constraint."
    )


def _universal_render_instruction() -> str:
    return (
        f"UNIVERSAL PHYSICAL, LIGHTING AND OPTICAL CONTRACT — BINDING "
        f"({UNIVERSAL_RENDER_CONTRACT_VERSION})\n- "
        + "\n- ".join(UNIVERSAL_RENDER_RULES)
    )


def _job_prompt(prompt: str, plan: Any, quality: str) -> tuple[str, str]:
    instruction = _render_instruction(plan, quality)
    universal = _universal_render_instruction()
    return f"{prompt.rstrip()}\n\n{universal}\n\n{instruction}", instruction


def _retry_prompt(base_prompt: str, attempt: int, correction: str,
                  failed_criteria: list[str] | None = None,
                  prior_attempt_sha256: str | None = None) -> str:
    """Keep the structured base prompt and vary the criterion-scoped repair."""
    return adaptive_retry_prompt(
        base_prompt, attempt, correction,
        failed_criteria=failed_criteria or (),
        prior_attempt_sha256=prior_attempt_sha256,
    )


def _start_state_overrides(stage: Path) -> tuple[dict[str, dict], dict | None]:
    """Load an optional, reviewable stage-05 positive-state prompt overlay.

    Stage 04 remains the source of shot intent.  This overlay exists for cases
    where a negative instruction such as "the action has not begun" is too
    ambiguous for an image model and production needs an explicit frozen pose
    and location without rewriting upstream receipts.
    """
    path = stage / "prompts" / "start-state-overrides.json"
    if not path.exists():
        return {}, None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Stage5Error(f"start-state override를 읽을 수 없다: {path}: {exc}") from exc
    if payload.get("schema_version") != "stage5-start-state-overrides.v1":
        raise Stage5Error("start-state override schema_version이 올바르지 않다")
    shots = payload.get("shots")
    if not isinstance(shots, dict):
        raise Stage5Error("start-state override의 shots는 객체여야 한다")
    for shot_id, item in shots.items():
        if not isinstance(item, dict) or not str(item.get("positive_state", "")).strip():
            raise Stage5Error(f"{shot_id} start-state override에 positive_state가 없다")
    receipt = {
        "path": str(path.relative_to(stage.parent)),
        "sha256": _sha(path),
        "reason": str(payload.get("reason", "")),
    }
    return shots, receipt


def _apply_start_state_override(prompt: str, item: dict | None) -> str:
    if not item:
        return prompt
    positive = str(item["positive_state"]).strip()
    forbidden = str(item.get("forbidden_state", "")).strip()
    lines = [
        prompt.rstrip(),
        "",
        "START-PLATE POSITIVE STATE OVERRIDE — BINDING",
        f"Depict exactly this frozen pre-action moment: {positive}",
        "The subject is completely still. The first requested action has not begun.",
    ]
    if forbidden:
        lines.append(f"Reject any image showing: {forbidden}")
    lines.append(
        "Treat action verbs elsewhere in the prompt only as future motion context; do not depict "
        "that motion, its midpoint, or its destination in this start plate."
    )
    return "\n".join(lines)


def _reference(attempt: Path, subject_id: str, path: Path,
               role: str, order: int) -> dict:
    attempt = attempt.resolve()
    path = path.resolve()
    return {"order": order, "subject_id": subject_id, "role": role,
            "path": str(path.relative_to(attempt)), "sha256": _sha(path)}


def _filter_blockers(audit: dict, shot_ids: set[str] | None, phase: str) -> list[dict]:
    result = []
    for item in audit.get("blockers") or []:
        if shot_ids and item.get("shot_id") and item["shot_id"] not in shot_ids:
            continue
        result.append(item)
    if phase == "plates":
        for item in audit.get("warnings") or []:
            if item.get("code") != "interaction-manual-approval-pending":
                continue
            if shot_ids and item.get("shot_id") not in shot_ids:
                continue
            result.append(item)
    return result


def prepare_codex_jobs(attempt: Path, phase: str,
                       only: list[str] | None = None, force: bool = False) -> dict:
    """Prepare 5A references first, then 5B plates after their approval.

    ``manuals`` remains a compatibility alias for older automation.  The 5A
    phase now includes both interaction manuals and Stage-03 reference debt.
    """
    if phase == "references":
        phase = "manuals"
    if phase not in {"manuals", "plates"}:
        raise Stage5Error("phase는 references(legacy manuals) 또는 plates여야 한다")
    attempt = attempt.resolve()
    contract = load_contract(attempt)
    execution_mode = load_execution_mode(attempt)
    fast_track = execution_mode.get("mode") == FAST_TRACK_MODE
    design, design_path = _load_design(attempt, contract)
    stage = _stage_dir(attempt, contract)
    selected = set(only or []) or None
    audit = audit_inputs(attempt)
    blockers = _filter_blockers(audit, selected, phase)
    if blockers:
        lines = [f"{item['code']}: {item['message']}" for item in blockers]
        raise Stage5Error(f"{phase} production 준비 차단:\n- " + "\n- ".join(lines))

    created = datetime.now(timezone.utc).astimezone()
    universal_render_contract = {
        "version": UNIVERSAL_RENDER_CONTRACT_VERSION,
        "sha256": _text_sha(_universal_render_instruction()),
    }
    manifest_id = f"{created.strftime('%Y%m%dT%H%M%S%f%z')}-{contract.digest[:8]}-{phase}"
    manifest_dir = stage / "qa" / "codex" / "manifests"
    raw_dir = stage / "qa" / "codex" / "candidates" / manifest_id
    prompt_dir = stage / "prompts" / "production" / phase
    jobs: list[dict] = []
    skipped: list[dict] = []
    start_overrides, start_override_receipt = _start_state_overrides(stage)

    if phase == "manuals":
        plan = contract.image_plan("sheet")
        quality = contract.image_quality("sheet")
        inventory = (design.get("reference_status") or {}).get("canonical_boards") or {}
        for shot_id, manual in _manuals(design):
            manual_id = str(manual["manual_id"])
            if selected and shot_id not in selected and manual_id not in selected:
                continue
            approved, _ = _approved_manual(stage, manual_id)
            if approved and not force:
                skipped.append({"asset_id": manual_id, "reason": "approved-output-exists"})
                continue
            refs = []
            for order, subject_id in enumerate(
                    manual.get("required_stage02_sheet_subject_ids") or [], 1):
                path = Path(str((inventory.get(subject_id) or {}).get("path", "")))
                if not path.is_absolute():
                    path = attempt / path
                refs.append(_reference(attempt, subject_id, path,
                                       "canonical_stage02_reference_board", order))
            prompt = str(manual["image_generation_prompt"])
            imagegen_prompt, instruction = _job_prompt(prompt, plan, quality)
            prompt_pack = {
                "schema_version": "stage5-production-prompt.v1", "asset_type": "manual",
                "asset_id": manual_id, "shot_id": shot_id,
                "source_shot_design": str(design_path.relative_to(attempt)),
                "source_shot_design_sha256": _short_sha(design_path),
                "prompt": prompt, "prompt_sha256": _text_sha(prompt),
                "imagegen_prompt": imagegen_prompt,
                "imagegen_prompt_sha256": _text_sha(imagegen_prompt),
                "universal_render_contract": universal_render_contract,
                "reference_images": refs, "manual_contract": manual,
            }
            prompt_dir.mkdir(parents=True, exist_ok=True)
            prompt_path = prompt_dir / f"{manual_id}.json"
            prompt_path.write_text(json.dumps(prompt_pack, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
            jobs.append({
                "job_id": manual_id, "asset_type": "manual", "asset_id": manual_id,
                "shot_id": shot_id, "status": "awaiting-imagegen",
                "prompt_path": str(prompt_path.relative_to(attempt)),
                "prompt_sha256": _text_sha(prompt), "imagegen_prompt": imagegen_prompt,
                "imagegen_prompt_sha256": _text_sha(imagegen_prompt),
                "universal_render_contract": universal_render_contract,
                "render_instruction": instruction, "reference_images": refs,
                "candidate_path": str((raw_dir / f"{manual_id}.png").relative_to(attempt)),
                "retry_harness": {
                    **harness_contract(
                        "stage05_interaction_manual",
                        _text_sha(imagegen_prompt),
                        list((manual.get("approval") or {}).get("criteria", [])),
                        exhaustion_policy="return_attempt_10_for_manual_review",
                        execution_mode=execution_mode["mode"],
                    ),
                    "attempt_path_pattern": str(
                        (raw_dir / manual_id / "attempts" / "A{attempt:02d}.png")
                        .relative_to(attempt)),
                    "review_log_path": str(
                        (raw_dir / manual_id / "ai-retry-review.json")
                        .relative_to(attempt)),
                },
                "requested": list(plan.target), "quality": quality, "overwrite": force,
            })
    else:
        plan = contract.image_plan("plate")
        quality = contract.image_quality("plate")
        states = design.get("states") or {}
        inventory = (design.get("reference_status") or {}).get("canonical_boards") or {}
        for shot in design.get("shots") or []:
            shot_id = str(shot.get("shot_id", ""))
            if selected and shot_id not in selected:
                continue
            output = stage / "output" / "plates" / f"{shot_id}.png"
            if output.exists() and not force:
                skipped.append({"asset_id": shot_id, "reason": "approved-output-exists"})
                continue
            state_id = (shot.get("state_pair") or {}).get("start_state_id")
            state = states[state_id]
            refs = []
            subjects = ((shot.get("reference_requirements") or {})
                        .get("canonical_stage02_sheet_subject_ids") or [])
            for order, subject_id in enumerate(subjects, 1):
                path = Path(str((inventory.get(subject_id) or {}).get("path", "")))
                if not path.is_absolute():
                    path = attempt / path
                refs.append(_reference(attempt, subject_id, path,
                                       "canonical_stage02_reference_board", order))
            manuals = (shot.get("supplemental_reference_plan") or {}).get("manuals") or []
            for manual in manuals:
                manual_id = str(manual["manual_id"])
                path = stage / "output" / "manuals" / f"{manual_id}.png"
                refs.append(_reference(attempt, manual_id, path,
                                       "approved_clean_interaction_manual", len(refs) + 1))
            upstream_prompt = str(state["prompt"])
            override = start_overrides.get(shot_id)
            prompt = _apply_start_state_override(upstream_prompt, override)
            imagegen_prompt, instruction = _job_prompt(prompt, plan, quality)
            prompt_pack = {
                "schema_version": "stage5-production-prompt.v1", "asset_type": "plate",
                "asset_id": shot_id, "shot_id": shot_id, "state_id": state_id,
                "source_shot_design": str(design_path.relative_to(attempt)),
                "source_shot_design_sha256": _short_sha(design_path),
                "upstream_prompt_sha256": _text_sha(upstream_prompt),
                "start_state_override": override,
                "start_state_override_receipt": start_override_receipt if override else None,
                "prompt": prompt, "prompt_sha256": _text_sha(prompt),
                "imagegen_prompt": imagegen_prompt,
                "imagegen_prompt_sha256": _text_sha(imagegen_prompt),
                "universal_render_contract": universal_render_contract,
                "reference_images": refs, "plate_acceptance": shot.get("plate_acceptance"),
            }
            prompt_dir.mkdir(parents=True, exist_ok=True)
            prompt_path = prompt_dir / f"{shot_id}.json"
            prompt_path.write_text(json.dumps(prompt_pack, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
            review_log = raw_dir / shot_id / "ai-retry-review.json"
            jobs.append({
                "job_id": f"{shot_id}-SEQUENTIAL", "asset_type": "plate",
                "asset_id": shot_id, "shot_id": shot_id, "state_id": state_id,
                "candidate_id": "AI-SELECTED", "status": "awaiting-imagegen",
                "prompt_path": str(prompt_path.relative_to(attempt)),
                "prompt_sha256": _text_sha(prompt), "imagegen_prompt": imagegen_prompt,
                "imagegen_prompt_sha256": _text_sha(imagegen_prompt),
                "universal_render_contract": universal_render_contract,
                "render_instruction": instruction, "reference_images": refs,
                "candidate_path": str((raw_dir / shot_id / "selected.png")
                                      .relative_to(attempt)),
                "retry_harness": {
                    "schema_version": PLATE_AI_REVIEW_SCHEMA,
                    "shared_harness_schema": HARNESS_SCHEMA,
                    "shared_contract": harness_contract(
                        "stage05_start_plate",
                        _text_sha(imagegen_prompt),
                        [
                            *list((shot.get("plate_acceptance") or {}).get("start", [])),
                            *PLATE_REFERENCE_COMPARISON_CRITERIA,
                        ],
                        exhaustion_policy=(
                            "return_attempt_10_with_accepted_defects"
                            if fast_track else "return_attempt_10_for_human_review"
                        ),
                        execution_mode=execution_mode["mode"],
                    ),
                    "strategy": "sequential_ai_review",
                    "initial_generation_count": 1,
                    "max_attempts": PLATE_MAX_ATTEMPTS,
                    "stop_on_pass": True,
                    "attempt_path_pattern": str(
                        (raw_dir / shot_id / "attempts" / "A{attempt:02d}.png")
                        .relative_to(attempt)),
                    "ai_review_log_path": str(review_log.relative_to(attempt)),
                    "retry_prompt_policy": (
                        "keep imagegen_prompt byte-for-byte as the prefix and append only the "
                        "failed-criterion correction using the declared RETRY CORRECTION template"
                    ),
                    "vary_every_retry": True,
                    "variation_strategies": list(VARIATION_STRATEGIES),
                    "exhaustion_policy": (
                        "use_attempt_10_with_accepted_defects"
                        if fast_track else "use_attempt_10_for_human_review"
                    ),
                    "acceptance_criteria": [
                        *list((shot.get("plate_acceptance") or {}).get("start", [])),
                        *PLATE_REFERENCE_COMPARISON_CRITERIA,
                    ],
                },
                "requested": list(plan.target), "quality": quality, "overwrite": force,
            })

    instructions = [
        "reference_images를 order 순서대로 모두 첨부하고 각 role을 그대로 유지한다",
        "반환 원본 PNG를 candidate_path에 저장한다",
        (
            "finalize 뒤 AI fast-track review packet을 판정·적용하고 즉시 다음 단계로 진행한다"
            if fast_track else
            "finalize는 픽셀과 기록을 검증할 뿐 사람 승인을 대신하지 않는다"
        ),
    ]
    if phase == "plates":
        unique_references: list[dict] = []
        reference_index: dict[tuple[str, str, str, str], dict] = {}
        for job in jobs:
            for reference in job.get("reference_images") or []:
                key = (
                    str(reference.get("subject_id") or ""),
                    str(reference.get("role") or ""),
                    str(reference.get("path") or ""),
                    str(reference.get("sha256") or ""),
                )
                existing = reference_index.get(key)
                if existing:
                    existing["used_by_jobs"].append(job["job_id"])
                    continue
                item = {
                    "reference_id": f"R{len(unique_references) + 1:03d}",
                    "subject_id": key[0],
                    "role": key[1],
                    "path": key[2],
                    "sha256": key[3],
                    "used_by_jobs": [job["job_id"]],
                }
                reference_index[key] = item
                unique_references.append(item)
        reference_preflight = {
            "schema_version": PLATE_REFERENCE_REVIEW_SCHEMA,
            "strategy": "global_reference_barrier",
            "must_complete_before_start_image": True,
            "criteria": list(PLATE_REFERENCE_CRITERIA),
            "references": unique_references,
            "ai_review_log_path": str(
                (raw_dir / "reference-preflight.json").relative_to(attempt)),
        }
        instructions = [
            "어떤 시작 이미지도 만들기 전에 reference_preflight.references 전체를 먼저 시각 검수한다",
            "모든 레퍼런스가 pass인 reference preflight를 기록한 뒤에만 시작 이미지 생성 wave를 시작한다",
            "각 shot은 imagegen_prompt로 한 장만 먼저 생성한다",
            "생성 직후 승인된 레퍼런스를 다시 함께 보며 retry_harness.acceptance_criteria를 "
            "AI가 시각 검수하고 근거를 기록한다",
            "통과하면 즉시 중단한다. 실패하면 구조화된 원본 prompt 전체를 유지한 채 "
            "실패 기준 보정만 덧붙여 다음 한 장을 생성한다",
            "총 시도는 10회다. 매 재시도는 실패 기준을 유지하면서 서로 다른 변주 전략을 쓴다",
            "10회 연속 실패하면 10회차를 selected.png로 사용한다",
            "모든 시도와 판정을 ai_review_log_path에 기록하고 선택 시도를 selected.png로 복사한다",
            *instructions,
        ]
    else:
        reference_preflight = None
        instructions.insert(0, "각 job의 imagegen_prompt를 바꾸지 않고 한 번씩 imagegen에 전달한다")

    manifest = {
        "schema_version": "codex-stage5-jobs.v1", "manifest_id": manifest_id,
        "status": "prepared", "created_at": created.isoformat(timespec="seconds"),
        "attempt": str(attempt), "stage": _stage_name(contract), "phase": phase,
        "contract": contract.receipt_block(_stage_name(contract)),
        "source_shot_design": str(design_path.relative_to(attempt)),
        "source_shot_design_sha256": _short_sha(design_path),
        "start_state_override_receipt": start_override_receipt,
        "universal_render_contract": universal_render_contract,
        "execution_mode": execution_mode,
        "reference_preflight": reference_preflight,
        "generator": {"mode": "codex", "invocation": "interactive-imagegen-skill",
                      "model": "gpt-image-2", "usage_accounting": "codex-general-usage",
                      "api_key_required": False},
        "jobs": jobs, "skipped": skipped,
        "instructions": instructions,
    }
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / f"{manifest_id}.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"manifest": str(manifest_path), "phase": phase, "jobs": len(jobs),
            "skipped": skipped, "api_called": False}


def _validate_manifest(attempt: Path, contract: Contract, manifest_path: Path) -> dict:
    manifest = _json(manifest_path, "stage5 Codex manifest")
    if manifest.get("schema_version") != "codex-stage5-jobs.v1":
        raise Stage5Error(f"지원하지 않는 manifest {manifest.get('schema_version')!r}")
    if manifest.get("status") != "prepared":
        raise Stage5Error(f"manifest 상태가 prepared가 아니다: {manifest.get('status')!r}")
    if Path(str(manifest.get("attempt", ""))).resolve() != attempt.resolve():
        raise Stage5Error("manifest가 다른 attempt를 가리킨다")
    if (manifest.get("contract") or {}).get("sha256") != contract.digest:
        raise Stage5Error("manifest 작성 뒤 계약이 바뀌었다")
    design_path = _design_path(attempt, contract)
    if manifest.get("source_shot_design_sha256") != _short_sha(design_path):
        raise Stage5Error("manifest 작성 뒤 shot cards가 바뀌었다")
    current_mode = load_execution_mode(attempt)
    recorded_mode = manifest.get("execution_mode") or {}
    if (recorded_mode.get("schema_version") != current_mode.get("schema_version") or
            recorded_mode.get("mode") != current_mode.get("mode") or
            recorded_mode.get("set_at") != current_mode.get("set_at")):
        raise Stage5Error("manifest 작성 뒤 execution mode가 바뀌었다. 새 manifest를 준비한다")
    if not manifest.get("jobs"):
        raise Stage5Error("manifest에 생성할 job이 없다")
    return manifest


def _reference_preflight_path(attempt: Path, manifest: dict) -> Path:
    preflight = manifest.get("reference_preflight") or {}
    if (preflight.get("schema_version") != PLATE_REFERENCE_REVIEW_SCHEMA or
            preflight.get("strategy") != "global_reference_barrier" or
            preflight.get("must_complete_before_start_image") is not True):
        raise Stage5Error("plate manifest의 전역 reference preflight 계약이 없거나 다르다")
    path = (attempt / str(preflight.get("ai_review_log_path") or "")).resolve()
    try:
        path.relative_to(attempt)
    except ValueError as error:
        raise Stage5Error("reference preflight log가 attempt 밖을 가리킨다") from error
    return path


def _validate_reference_payload(attempt: Path, manifest: dict, payload: dict,
                                *, require_pass: bool) -> dict:
    preflight = manifest.get("reference_preflight") or {}
    if (payload.get("schema_version") != PLATE_REFERENCE_REVIEW_SCHEMA or
            payload.get("manifest_id") != manifest.get("manifest_id")):
        raise Stage5Error("reference preflight의 schema 또는 manifest 결속 정보가 다르다")
    expected = list(preflight.get("references") or [])
    actual = payload.get("references") or []
    if len(actual) != len(expected):
        raise Stage5Error("reference preflight가 manifest의 모든 레퍼런스를 검수하지 않았다")
    criteria_expected = list(preflight.get("criteria") or [])
    binding_keys = ("reference_id", "subject_id", "role", "path", "sha256", "used_by_jobs")
    item_decisions = []
    for index, (record, source) in enumerate(zip(actual, expected), 1):
        if any(record.get(key) != source.get(key) for key in binding_keys):
            raise Stage5Error(f"reference preflight R{index:03d}의 순서·경로·hash 결속이 다르다")
        path = (attempt / str(source.get("path") or "")).resolve()
        try:
            path.relative_to(attempt)
        except ValueError as error:
            raise Stage5Error(f"{source.get('reference_id')}: reference가 attempt 밖을 가리킨다") from error
        if not path.is_file() or source.get("sha256") != _sha(path):
            raise Stage5Error(f"{source.get('reference_id')}: reference가 없거나 검수 전후 바뀌었다")
        criteria = record.get("criteria") or []
        if [item.get("criterion") for item in criteria] != criteria_expected:
            raise Stage5Error(f"{source.get('reference_id')}: reference 검수 기준이 계약과 다르다")
        statuses = [item.get("status") for item in criteria]
        if any(status not in {"pass", "fail"} for status in statuses):
            raise Stage5Error(f"{source.get('reference_id')}: 기준 상태는 pass/fail이어야 한다")
        if any(not (item.get("evidence") or []) for item in criteria):
            raise Stage5Error(f"{source.get('reference_id')}: 각 reference 기준에는 시각 근거가 필요하다")
        decision = record.get("decision")
        if decision not in {"pass", "fail"}:
            raise Stage5Error(f"{source.get('reference_id')}: 판정은 pass/fail이어야 한다")
        if (decision == "pass") != bool(statuses and all(status == "pass" for status in statuses)):
            raise Stage5Error(f"{source.get('reference_id')}: 종합 판정과 기준별 판정이 모순된다")
        item_decisions.append(decision)
    decision = payload.get("decision")
    all_passed = all(item == "pass" for item in item_decisions)
    if decision not in {"pass", "fail"} or (decision == "pass") != all_passed:
        raise Stage5Error("reference preflight 종합 판정이 개별 판정과 모순된다")
    if not str(payload.get("reviewer") or "").strip() or not str(payload.get("reviewed_at") or "").strip():
        raise Stage5Error("reference preflight reviewer 또는 reviewed_at이 비어 있다")
    if require_pass and decision != "pass":
        raise Stage5Error("모든 reference preflight가 통과하기 전에는 시작 이미지를 처리할 수 없다")
    return {
        "schema_version": PLATE_REFERENCE_REVIEW_SCHEMA,
        "strategy": "global_reference_barrier",
        "decision": decision,
        "reference_count": len(actual),
        "reviewer": payload.get("reviewer"),
        "reviewed_at": payload.get("reviewed_at"),
    }


def _validate_reference_preflight(attempt: Path, manifest: dict) -> dict:
    path = _reference_preflight_path(attempt, manifest)
    payload = _json(path, "plate reference preflight")
    summary = _validate_reference_payload(attempt, manifest, payload, require_pass=True)
    return {**summary, "review_log": str(path.relative_to(attempt)),
            "review_log_sha256": _sha(path)}


def record_ai_reference_review(attempt: Path, manifest_path: Path, review_path: Path) -> dict:
    """Record the global reference review barrier before any start image exists."""
    attempt = attempt.resolve()
    contract = load_contract(attempt)
    manifest = _validate_manifest(attempt, contract, manifest_path)
    if manifest.get("phase") != "plates":
        raise Stage5Error("reference preflight는 plate manifest에만 적용한다")
    for job in manifest.get("jobs") or []:
        harness = job.get("retry_harness") or {}
        selected = (attempt / str(job.get("candidate_path") or "")).resolve()
        retry_log = (attempt / str(harness.get("ai_review_log_path") or "")).resolve()
        generated = any(
            (attempt / str(harness.get("attempt_path_pattern") or "")
             .format(attempt=number)).resolve().exists()
            for number in range(1, PLATE_MAX_ATTEMPTS + 1)
        )
        if generated or selected.exists() or retry_log.exists():
            raise Stage5Error(
                "reference preflight는 모든 시작 이미지 생성보다 먼저 기록해야 한다: "
                f"{job.get('job_id')}")
    review = _json(review_path, "AI reference preflight review")
    summary = _validate_reference_payload(attempt, manifest, review, require_pass=False)
    log_path = _reference_preflight_path(attempt, manifest)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
    if summary["decision"] != "pass":
        return {**summary, "status": "reference_repair_required",
                "ai_review_log": str(log_path)}
    return {**summary, "status": "reference_preflight_passed",
            "ai_review_log": str(log_path), "ai_review_log_sha256": _sha(log_path)}


def record_ai_plate_review(attempt: Path, manifest_path: Path, review_path: Path) -> dict:
    """Record one AI preflight verdict and return either the retry or selection work order."""
    attempt = attempt.resolve()
    contract = load_contract(attempt)
    manifest = _validate_manifest(attempt, contract, manifest_path)
    if manifest.get("phase") != "plates":
        raise Stage5Error("AI 순차 검수는 plate manifest에만 적용한다")
    reference_preflight = _validate_reference_preflight(attempt, manifest)
    review = _json(review_path, "AI plate attempt review")
    if review.get("schema_version") != PLATE_AI_ATTEMPT_REVIEW_SCHEMA:
        raise Stage5Error(f"지원하지 않는 AI attempt review {review.get('schema_version')!r}")
    job_id = str(review.get("job_id") or "")
    job = next((item for item in manifest.get("jobs") or []
                if item.get("job_id") == job_id), None)
    if not job or job.get("asset_type") != "plate":
        raise Stage5Error(f"manifest에 plate job이 없다: {job_id}")
    harness = job.get("retry_harness") or {}
    if (harness.get("schema_version") != PLATE_AI_REVIEW_SCHEMA or
            int(harness.get("max_attempts", 0)) != PLATE_MAX_ATTEMPTS):
        raise Stage5Error(f"{job_id}: AI retry harness가 없거나 버전이 다르다")

    log_path = (attempt / str(harness.get("ai_review_log_path", ""))).resolve()
    try:
        log_path.relative_to(attempt)
    except ValueError as error:
        raise Stage5Error(f"{job_id}: AI review log가 attempt 밖을 가리킨다") from error
    if log_path.exists():
        log = _json(log_path, f"AI retry review {job_id}")
    else:
        log = {
            "schema_version": PLATE_AI_REVIEW_SCHEMA,
            "job_id": job_id,
            "asset_id": job.get("asset_id"),
            "max_attempts": PLATE_MAX_ATTEMPTS,
            "base_imagegen_prompt_sha256": job.get("imagegen_prompt_sha256"),
            "reference_preflight_sha256": reference_preflight["review_log_sha256"],
            "attempts": [],
            "selected_attempt": None,
            "selection_reason": None,
            "selected_candidate_path": None,
            "selected_candidate_sha256": None,
        }
    if log.get("reference_preflight_sha256") != reference_preflight["review_log_sha256"]:
        raise Stage5Error(f"{job_id}: 시작 이미지 검수가 승인된 reference preflight와 결속되지 않았다")
    attempts = log.get("attempts") or []
    if log.get("selected_attempt") is not None or len(attempts) >= PLATE_MAX_ATTEMPTS:
        raise Stage5Error(f"{job_id}: AI retry harness는 이미 종료됐다")
    number = len(attempts) + 1
    expected_criteria = list(harness.get("acceptance_criteria") or [])
    criteria = review.get("criteria") or []
    if [item.get("criterion") for item in criteria] != expected_criteria:
        raise Stage5Error(f"{job_id}: AI 판정 기준이 shot card와 다르다")
    statuses = [item.get("status") for item in criteria]
    if any(status not in {"pass", "fail"} for status in statuses):
        raise Stage5Error(f"{job_id}: AI 기준 상태는 pass/fail이어야 한다")
    decision = review.get("decision")
    if (decision == "pass") != bool(statuses and all(status == "pass" for status in statuses)):
        raise Stage5Error(f"{job_id}: AI 종합 판정과 기준별 판정이 모순된다")
    if decision not in {"pass", "fail"}:
        raise Stage5Error(f"{job_id}: AI 판정은 pass/fail이어야 한다")
    reviewer = str(review.get("reviewer") or "").strip()
    reviewed_at = str(review.get("reviewed_at") or "").strip()
    feedback = str(review.get("feedback") or "").strip()
    if not reviewer or not reviewed_at:
        raise Stage5Error(f"{job_id}: AI reviewer 또는 reviewed_at이 비어 있다")
    if decision == "fail" and number < PLATE_MAX_ATTEMPTS and not feedback:
        raise Stage5Error(f"{job_id}: 실패 판정에는 다음 생성용 feedback이 필요하다")

    candidate_rel = str(harness.get("attempt_path_pattern", "")).format(attempt=number)
    candidate = (attempt / candidate_rel).resolve()
    try:
        candidate.relative_to(attempt)
    except ValueError as error:
        raise Stage5Error(f"{job_id}: AI 시도 이미지가 attempt 밖을 가리킨다") from error
    if not candidate.is_file() or candidate.stat().st_size == 0:
        raise Stage5Error(f"{job_id}: 검수할 AI 시도 이미지가 없다: {candidate}")
    correction = "" if number == 1 else str(attempts[-1].get("feedback") or "").strip()
    previous_failed = ([] if number == 1 else
                       list(attempts[-1].get("failed_criteria") or []))
    previous_sha = None if number == 1 else attempts[-1].get("candidate_sha256")
    effective_prompt = _retry_prompt(
        str(job["imagegen_prompt"]), number, correction,
        previous_failed, previous_sha)
    failed_criteria = [item.get("criterion") for item in criteria
                       if item.get("status") == "fail"]
    attempts.append({
        "attempt": number,
        "variation_strategy": variation_strategy(number),
        "candidate_path": candidate_rel,
        "candidate_sha256": _sha(candidate),
        "decision": decision,
        "criteria": criteria,
        "feedback": feedback,
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
        "retry_correction": correction,
        "failed_criteria": failed_criteria,
        "effective_prompt_sha256": _text_sha(effective_prompt),
    })
    log["attempts"] = attempts

    selected = decision == "pass" or number == PLATE_MAX_ATTEMPTS
    if selected:
        selected_path = (attempt / str(job.get("candidate_path", ""))).resolve()
        try:
            selected_path.relative_to(attempt)
        except ValueError as error:
            raise Stage5Error(f"{job_id}: selected image가 attempt 밖을 가리킨다") from error
        selected_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(candidate, selected_path)
        log["selected_attempt"] = number
        log["selection_reason"] = ("ai_pass" if decision == "pass"
                                   else "max_attempts_exhausted")
        log["selected_candidate_path"] = job.get("candidate_path")
        log["selected_candidate_sha256"] = _sha(selected_path)

    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    if selected:
        fast_track = ((manifest.get("execution_mode") or {}).get("mode") == FAST_TRACK_MODE)
        return {
            "status": ("selected_for_ai_fast_track_review" if fast_track
                       else "selected_for_human_review"),
            "job_id": job_id,
            "selected_attempt": number,
            "selection_reason": log["selection_reason"],
            "candidate_path": str((attempt / str(job["candidate_path"])).resolve()),
            "ai_review_log": str(log_path),
        }
    next_number = number + 1
    next_correction = feedback
    return {
        "status": "retry_required",
        "job_id": job_id,
        "next_attempt": next_number,
        "candidate_path": str((attempt / str(harness["attempt_path_pattern"])
                               .format(attempt=next_number)).resolve()),
        "imagegen_prompt": _retry_prompt(str(job["imagegen_prompt"]),
                                          next_number, next_correction,
                                          failed_criteria, _sha(candidate)),
        "variation_strategy": variation_strategy(next_number),
        "reference_images": job.get("reference_images") or [],
        "ai_review_log": str(log_path),
    }


def _annotate_manual(clean: Path, target: Path, manual: dict) -> None:
    with Image.open(clean) as source:
        image = source.convert("RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    width, height = image.size
    panels = manual.get("panels") or []
    cols, rows = 2, 3
    for index, panel in enumerate(panels[:6]):
        col, row = index % cols, index // cols
        left, top = round(col * width / cols), round(row * height / rows)
        right, bottom = round((col + 1) * width / cols) - 1, round((row + 1) * height / rows) - 1
        draw.rectangle((left, top, right, bottom), outline=(255, 80, 40, 220), width=max(1, width // 500))
        label = f"{panel.get('panel_id')} {panel.get('role')} / {panel.get('state')}"
        box_height = max(14, height // 45)
        draw.rectangle((left, top, right, min(bottom, top + box_height)), fill=(0, 0, 0, 170))
        draw.text((left + 3, top + 2), label, fill=(255, 255, 255, 255))
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target)


def _validate_ai_retry_log(attempt_root: Path, job: dict, selected: Path,
                           reference_preflight: dict) -> dict:
    harness = job.get("retry_harness") or {}
    if (harness.get("schema_version") != PLATE_AI_REVIEW_SCHEMA or
            harness.get("strategy") != "sequential_ai_review" or
            int(harness.get("initial_generation_count", 0)) != 1 or
            int(harness.get("max_attempts", 0)) != PLATE_MAX_ATTEMPTS or
            harness.get("stop_on_pass") is not True or
            harness.get("vary_every_retry") is not True or
            harness.get("variation_strategies") != list(VARIATION_STRATEGIES) or
            harness.get("exhaustion_policy") not in {
                "use_attempt_10_for_human_review",
                "use_attempt_10_with_accepted_defects",
            }):
        raise Stage5Error(f"{job.get('job_id')}: AI 순차 재생성 하네스 계약이 다르다")

    log_path = (attempt_root / str(harness.get("ai_review_log_path", ""))).resolve()
    try:
        log_path.relative_to(attempt_root)
    except ValueError as error:
        raise Stage5Error(f"{job.get('job_id')}: AI review log가 attempt 밖을 가리킨다") from error
    log = _json(log_path, f"AI retry review {job.get('job_id')}")
    if (log.get("schema_version") != PLATE_AI_REVIEW_SCHEMA or
            log.get("job_id") != job.get("job_id") or
            log.get("asset_id") != job.get("asset_id") or
            int(log.get("max_attempts", 0)) != PLATE_MAX_ATTEMPTS or
            log.get("base_imagegen_prompt_sha256") != job.get("imagegen_prompt_sha256") or
            log.get("reference_preflight_sha256") !=
            reference_preflight.get("review_log_sha256")):
        raise Stage5Error(f"{job.get('job_id')}: AI review log 결속 정보가 다르다")

    attempts = log.get("attempts") or []
    if not 1 <= len(attempts) <= PLATE_MAX_ATTEMPTS:
        raise Stage5Error(
            f"{job.get('job_id')}: AI 시도 수는 1~{PLATE_MAX_ATTEMPTS}이어야 한다")
    expected_criteria = list(harness.get("acceptance_criteria") or [])
    previous_feedback = ""
    for index, record in enumerate(attempts, 1):
        if record.get("attempt") != index:
            raise Stage5Error(f"{job.get('job_id')}: AI 시도 번호는 1부터 연속이어야 한다")
        if record.get("variation_strategy") != variation_strategy(index):
            raise Stage5Error(f"{job.get('job_id')}: 재시도 변주 전략 기록이 계약과 다르다")
        decision = record.get("decision")
        if decision not in {"pass", "fail"}:
            raise Stage5Error(f"{job.get('job_id')}: AI 판정은 pass/fail이어야 한다")
        criteria = record.get("criteria") or []
        if [item.get("criterion") for item in criteria] != expected_criteria:
            raise Stage5Error(f"{job.get('job_id')}: AI 판정 기준이 shot card와 다르다")
        statuses = [item.get("status") for item in criteria]
        if any(status not in {"pass", "fail"} for status in statuses):
            raise Stage5Error(f"{job.get('job_id')}: AI 기준 상태는 pass/fail이어야 한다")
        if (decision == "pass") != bool(statuses and all(status == "pass" for status in statuses)):
            raise Stage5Error(f"{job.get('job_id')}: AI 종합 판정과 기준별 판정이 모순된다")
        if not str(record.get("reviewer") or "").strip() or not str(record.get("reviewed_at") or "").strip():
            raise Stage5Error(f"{job.get('job_id')}: AI reviewer 또는 reviewed_at이 비어 있다")
        correction = str(record.get("retry_correction") or "")
        if index == 1 and correction:
            raise Stage5Error(f"{job.get('job_id')}: 첫 시도에는 retry correction이 없어야 한다")
        if index > 1 and correction != previous_feedback:
            raise Stage5Error(f"{job.get('job_id')}: 재시도는 직전 AI feedback만 보정문으로 써야 한다")
        prior_record = attempts[index - 2] if index > 1 else {}
        effective = _retry_prompt(
            str(job["imagegen_prompt"]), index, correction,
            list(prior_record.get("failed_criteria") or []),
            prior_record.get("candidate_sha256"))
        if record.get("effective_prompt_sha256") != _text_sha(effective):
            raise Stage5Error(f"{job.get('job_id')}: 재시도 prompt가 구조화된 원본에서 이탈했다")
        expected_path = str(harness.get("attempt_path_pattern", "")).format(attempt=index)
        if record.get("candidate_path") != expected_path:
            raise Stage5Error(f"{job.get('job_id')}: AI 시도 이미지 경로가 계약과 다르다")
        candidate = (attempt_root / expected_path).resolve()
        try:
            candidate.relative_to(attempt_root)
        except ValueError as error:
            raise Stage5Error(f"{job.get('job_id')}: AI 시도 이미지가 attempt 밖을 가리킨다") from error
        if not candidate.is_file() or record.get("candidate_sha256") != _sha(candidate):
            raise Stage5Error(f"{job.get('job_id')}: AI 시도 이미지가 없거나 검수 뒤 바뀌었다")
        if index < len(attempts) and decision != "fail":
            raise Stage5Error(f"{job.get('job_id')}: AI 통과 뒤 추가 이미지를 생성할 수 없다")
        previous_feedback = str(record.get("feedback") or "").strip()
        if decision == "fail" and index < PLATE_MAX_ATTEMPTS and not previous_feedback:
            raise Stage5Error(f"{job.get('job_id')}: 실패한 AI 검수에는 재생성 feedback이 필요하다")

    last = attempts[-1]
    if len(attempts) < PLATE_MAX_ATTEMPTS and last.get("decision") != "pass":
        raise Stage5Error(
            f"{job.get('job_id')}: AI 실패 뒤 최대 {PLATE_MAX_ATTEMPTS}회 전에 중단할 수 없다")
    reason = "ai_pass" if last.get("decision") == "pass" else "max_attempts_exhausted"
    if (log.get("selected_attempt") != len(attempts) or
            log.get("selection_reason") != reason or
            log.get("selected_candidate_path") != job.get("candidate_path") or
            log.get("selected_candidate_sha256") != _sha(selected) or
            _sha(selected) != last.get("candidate_sha256")):
        raise Stage5Error(f"{job.get('job_id')}: AI 선택 결과가 마지막 유효 시도와 다르다")
    return {
        "strategy": "sequential_ai_review",
        "attempt_count": len(attempts),
        "max_attempts": PLATE_MAX_ATTEMPTS,
        "selected_attempt": len(attempts),
        "selection_reason": reason,
        "all_attempts_failed": reason == "max_attempts_exhausted",
        "review_log": str(log_path.relative_to(attempt_root)),
        "review_log_sha256": _sha(log_path),
        "reference_preflight": reference_preflight,
        "attempts": attempts,
    }


def finalize_codex_jobs(attempt: Path, manifest_path: Path,
                        surface: str = "unknown") -> dict:
    """Validate generated images and create pending human-review packets."""
    if surface not in CODEX_SURFACES:
        raise Stage5Error(f"Codex surface는 {sorted(CODEX_SURFACES)} 중 하나여야 한다")
    attempt = attempt.resolve()
    contract = load_contract(attempt)
    design, _ = _load_design(attempt, contract)
    manifest = _validate_manifest(attempt, contract, manifest_path)
    phase = str(manifest.get("phase"))
    fast_track = ((manifest.get("execution_mode") or {}).get("mode") == FAST_TRACK_MODE)
    reference_preflight = (_validate_reference_preflight(attempt, manifest)
                           if phase == "plates" else None)
    plan = contract.image_plan("sheet" if phase == "manuals" else "plate")
    quality = contract.image_quality("sheet" if phase == "manuals" else "plate")
    universal_render_contract = {
        "version": UNIVERSAL_RENDER_CONTRACT_VERSION,
        "sha256": _text_sha(_universal_render_instruction()),
    }
    root = attempt.resolve()
    problems = []
    prepared = []
    for job in manifest["jobs"]:
        prompt_path = (attempt / str(job.get("prompt_path", ""))).resolve()
        candidate = (attempt / str(job.get("candidate_path", ""))).resolve()
        try:
            prompt_path.relative_to(root)
            candidate.relative_to(root)
        except ValueError:
            problems.append(f"{job.get('job_id')}: attempt 밖 경로")
            continue
        pack = _json(prompt_path, f"prompt pack {job.get('job_id')}")
        prompt = str(pack.get("prompt") or "")
        imagegen_prompt, instruction = _job_prompt(prompt, plan, quality)
        if (job.get("prompt_sha256") != _text_sha(prompt) or
                job.get("imagegen_prompt") != imagegen_prompt or
                job.get("imagegen_prompt_sha256") != _text_sha(imagegen_prompt) or
                job.get("universal_render_contract") != universal_render_contract or
                pack.get("universal_render_contract") != universal_render_contract or
                manifest.get("universal_render_contract") != universal_render_contract or
                job.get("render_instruction") != instruction or
                job.get("requested") != list(plan.target) or job.get("quality") != quality):
            problems.append(f"{job.get('job_id')}: prompt/크기/품질 계약이 바뀌었다")
            continue
        for ref in job.get("reference_images") or []:
            path = (attempt / str(ref.get("path", ""))).resolve()
            if not path.is_file() or ref.get("sha256") != _sha(path):
                problems.append(f"{job.get('job_id')}: reference가 없거나 바뀌었다 {ref.get('path')}")
        if not candidate.is_file() or candidate.stat().st_size == 0:
            problems.append(f"{job.get('job_id')}: candidate가 없다 {candidate}")
            continue
        try:
            with Image.open(candidate) as image:
                source_size = list(image.size)
                image.verify()
        except Exception as error:  # noqa: BLE001
            problems.append(f"{job.get('job_id')}: candidate 이미지 오류 {error}")
            continue
        if not source_within_pixel_tolerance(tuple(source_size), tuple(plan.target)):
            allowed = pixel_tolerance(tuple(plan.target))
            problems.append(
                f"{job.get('job_id')}: 원본이 계약 허용오차를 넘는다 "
                f"source={source_size} requested={list(plan.target)} "
                f"allowed_deficit={list(allowed)}")
            continue
        ai_retry = (_validate_ai_retry_log(root, job, candidate, reference_preflight)
                    if phase == "plates" else None)
        prepared.append((job, pack, candidate, source_size, ai_retry))
    if problems:
        raise Stage5Error("Codex finalize 중단:\n- " + "\n- ".join(problems))

    stage = _stage_dir(attempt, contract)
    manifest_id = str(manifest["manifest_id"])
    rendered = []
    grouped: dict[str, list[dict]] = {}
    for job, pack, candidate, source_size, ai_retry in prepared:
        if phase == "manuals":
            target = stage / "qa" / "manual-candidates" / manifest_id / f"{job['asset_id']}.png"
        else:
            target = (stage / "qa" / "plate-candidates" / manifest_id /
                      job["shot_id"] / f"{job['candidate_id']}.png")
        with Image.open(candidate) as source:
            image, actual_fit = materialize_with_pixel_tolerance(
                source.convert("RGB"), tuple(plan.target))
            target.parent.mkdir(parents=True, exist_ok=True)
            image.save(target)
        record = {"job_id": job["job_id"], "asset_id": job["asset_id"],
                  "candidate_id": job.get("candidate_id"),
                  "path": str(target.relative_to(attempt)), "sha256": _sha(target),
                  "source_path": str(candidate.relative_to(attempt)),
                  "source_sha256": _sha(candidate), "source_dimensions": source_size,
                  "delivered": list(plan.target), "fit": actual_fit,
                  "pixel_tolerance": {
                      "max_ratio": PIXEL_TOLERANCE_RATIO,
                      "max_pixels_per_axis": PIXEL_TOLERANCE_MAX_PIXELS,
                      "allowed_deficit": list(pixel_tolerance(tuple(plan.target))),
                  },
                  "prompt_sha256": job["prompt_sha256"],
                  "imagegen_prompt_sha256": job["imagegen_prompt_sha256"],
                  "ai_retry_harness": ai_retry}
        rendered.append(record)
        grouped.setdefault(str(job["asset_id"]), []).append(record)

    review_paths = []
    review_assets = []
    for asset_id, records in grouped.items():
        if phase == "manuals":
            _, manual = next(item for item in _manuals(design) if item[1]["manual_id"] == asset_id)
            clean = attempt / records[0]["path"]
            annotated = clean.with_name(f"{asset_id}-annotated.png")
            _annotate_manual(clean, annotated, manual)
            review = {
                "schema_version": "stage5-manual-review.v1", "asset_type": "manual",
                "asset_id": asset_id, "manifest_id": manifest_id,
                "clean_board": records[0],
                "annotated_qa_board": {"path": str(annotated.relative_to(attempt)),
                                       "sha256": _sha(annotated)},
                "criteria": [{"criterion": text, "status": "pending", "evidence": []}
                             for text in (manual.get("approval") or {}).get("criteria", [])],
                "decision": "pending", "reviewer": None, "reviewed_at": None,
                "review_mode": "ai_preflight",
                "human_approval_required": False,
                "auto_approve_allowed": True,
            }
            path = _review_path(stage, "manual", asset_id)
            bound_asset = {
                "asset_type": "manual", "asset_id": asset_id,
                "clean_board": records[0],
                "annotated_qa_board": review["annotated_qa_board"],
            }
        else:
            shot = next(item for item in design["shots"] if item["shot_id"] == asset_id)
            acceptance = shot.get("plate_acceptance") or {}
            direction = (shot.get("motion_control") or {}).get("screen_direction_contract") or {}
            review = {
                "schema_version": "stage5-plate-review.v1", "asset_type": "plate",
                "asset_id": asset_id, "manifest_id": manifest_id, "candidates": records,
                "ai_retry_harness": records[0].get("ai_retry_harness"),
                "criteria": [{"criterion": text, "status": "pending", "evidence": []}
                             for text in acceptance.get("start", [])],
                "selected_candidate": "AI-SELECTED", "decision": "pending", "reviewer": None,
                "reviewed_at": None,
                "review_mode": "ai_fast_track" if fast_track else "human",
                "human_approval_required": not fast_track,
                "auto_approve_allowed": fast_track,
                "accepted_defects": [],
                "screen_direction_required": bool(direction.get("required")),
                "screen_direction": {
                    "start_center_normalized": None, "end_center_normalized": None,
                    "screen_direction_vector": None, "depth_intent": None,
                    "allowed_depth_intents": direction.get("allowed_depth_intents", []),
                } if direction.get("required") else None,
            }
            path = _review_path(stage, "plate", asset_id)
            bound_asset = {"asset_type": "plate", "asset_id": asset_id,
                           "candidates": records}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
        review_paths.append(str(path))
        review_assets.append({**bound_asset, "review_path": str(path.relative_to(attempt))})

    manifest["status"] = "finalized_pending_review"
    manifest["finalized_at"] = _now()
    manifest["surface"] = surface
    manifest["rendered"] = rendered
    manifest["review_packets"] = [str(Path(path).relative_to(attempt)) for path in review_paths]
    manifest["review_assets"] = review_assets
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    note = (
        "AI가 manual review packet을 판정·적용하면 plate 준비가 자동으로 이어진다"
        if phase == "manuals" else
        ("fast_track AI가 plate review packet을 판정·적용하고 다음 단계로 이어간다"
         if fast_track else
         "사람이 plate review packet을 판정하기 전에는 output으로 승격되지 않는다")
    )
    return {"phase": phase, "finalized": len(rendered), "review_packets": review_paths,
            "approved": 0, "note": note}


def _criteria_pass(review: dict) -> bool:
    criteria = review.get("criteria") or []
    return bool(criteria) and all(item.get("status") == "pass" for item in criteria)


def _criteria_accepted(review: dict, fast_track: bool) -> bool:
    criteria = review.get("criteria") or []
    if not criteria:
        return False
    allowed = {"pass", "accepted_defect"} if fast_track else {"pass"}
    if any(item.get("status") not in allowed for item in criteria):
        return False
    accepted = [item for item in criteria if item.get("status") == "accepted_defect"]
    if not accepted:
        return True
    retry = review.get("ai_retry_harness") or {}
    if (not fast_track or retry.get("selection_reason") != "max_attempts_exhausted" or
            int(retry.get("selected_attempt") or 0) != PLATE_MAX_ATTEMPTS or
            any(not item.get("evidence") for item in accepted)):
        return False
    declared = {str(item) for item in review.get("accepted_defects") or []}
    actual = {str(item.get("criterion")) for item in accepted}
    return declared == actual


def _archive_existing(stage: Path, output: Path, asset_id: str) -> None:
    if not output.exists():
        return
    stamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
    target = stage / "rejected" / "superseded" / stamp / asset_id / output.name
    target.parent.mkdir(parents=True, exist_ok=True)
    output.replace(target)


def _merge_receipt(stage: Path, contract: Contract, kind: str, record: dict) -> Path:
    path = stage / "receipt.json"
    if path.exists():
        receipt = _json(path, "stage5 receipt")
    else:
        receipt = {"schema_version": "stage5-receipt.v1",
                   "receipt_id": f"{contract.data['contract_id']}-PLATES",
                   "contract": contract.receipt_block(_stage_name(contract)),
                   "manuals": [], "plates": []}
    if (receipt.get("contract") or {}).get("sha256") != contract.digest:
        raise Stage5Error("기존 stage5 receipt의 계약 digest가 현재 계약과 다르다")
    key = "manuals" if kind == "manual" else "plates"
    id_key = "manual_id" if kind == "manual" else "shot_id"
    merged = {item[id_key]: item for item in receipt.get(key) or []}
    merged[record[id_key]] = record
    receipt[key] = list(merged.values())
    receipt["updated_at"] = _now()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _valid_point(value: Any) -> bool:
    return (isinstance(value, list) and len(value) == 2 and
            all(isinstance(item, (int, float)) and 0 <= item <= 1 for item in value))


def _motion_prompt_with_resolved_direction(prompt: str, direction: dict | None,
                                           review_mode: str = "human") -> str:
    """Compile a mode-approved screen annotation into the H3 prompt.

    Stage 04 deliberately leaves translating shots blocked until the mode-bound
    reviewer annotates the selected plate. Once that review is approved, the Stage 05
    handoff must not keep the old ``unresolved / do not generate`` sentence.
    """
    if not direction:
        return prompt
    approval_label = "AI-fast-track-approved" if review_mode == "ai_fast_track" else "human-approved"
    clause = (
        f"SCREEN DIRECTION — {approval_label} start center "
        f"{json.dumps(direction['start_center_normalized'])}; end center "
        f"{json.dumps(direction['end_center_normalized'])}; screen vector "
        f"{json.dumps(direction['screen_direction_vector'])}; depth intent "
        f"{direction['depth_intent']}. Keep the subject on this approved screen-space track."
    )
    unresolved = (
        "SCREEN DIRECTION — unresolved. Do not generate H3 until normalized start/end centers, "
        "direction vector and depth intent are approved."
    )
    if unresolved in prompt:
        return prompt.replace(unresolved, clause)
    return f"{prompt.rstrip()}\n{clause}"


def _write_h3_handoff(attempt: Path, contract: Contract, design: dict) -> Path:
    stage = _stage_dir(attempt, contract)
    rows = []
    complete = True
    inventory = (design.get("reference_status") or {}).get("canonical_boards") or {}
    for shot in design.get("shots") or []:
        shot_id = shot["shot_id"]
        plate = stage / "output" / "plates" / f"{shot_id}.png"
        review_path = _review_path(stage, "plate", shot_id)
        if not plate.is_file() or not review_path.is_file():
            complete = False
            continue
        review = _json(review_path, f"plate review {shot_id}")
        if review.get("decision") != "approved" or review.get("approved_output_sha256") != _sha(plate):
            complete = False
            continue
        refs = []
        for subject_id in ((shot.get("reference_requirements") or {})
                           .get("canonical_stage02_sheet_subject_ids") or []):
            path = Path(str((inventory.get(subject_id) or {}).get("path", "")))
            if not path.is_absolute():
                path = attempt / path
            path = path.resolve()
            refs.append({"subject_id": subject_id, "path": str(path.relative_to(attempt)),
                         "sha256": _sha(path)})
        manuals = []
        for manual in (shot.get("supplemental_reference_plan") or {}).get("manuals") or []:
            path = stage / "output" / "manuals" / f"{manual['manual_id']}.png"
            manuals.append({"manual_id": manual["manual_id"],
                            "path": str(path.relative_to(attempt)), "sha256": _sha(path)})
        screen_direction = review.get("screen_direction")
        rows.append({"shot_id": shot_id, "anchor_policy": "first_only",
                     "first_plate": {"path": str(plate.relative_to(attempt)), "sha256": _sha(plate)},
                     "last_plate": None, "canonical_stage02_sheets": refs,
                     "approved_interaction_manuals": manuals,
                     "screen_direction": screen_direction,
                     "motion_prompt": _motion_prompt_with_resolved_direction(
                         str(shot.get("motion_prompt") or ""), screen_direction,
                         str(review.get("review_mode") or "human"))})
    payload = {"schema_version": "stage5-h3-handoff.v1", "created_at": _now(),
               "contract": contract.receipt_block(_stage_name(contract)),
               "status": "ready" if complete and len(rows) == len(design.get("shots") or []) else "incomplete",
               "ready": complete and len(rows) == len(design.get("shots") or []),
               "expected_shots": len(design.get("shots") or []), "approved_shots": len(rows),
               "shots": rows}
    target = stage / "output" / "h3-conditioning.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def apply_review(attempt: Path, review_path: Path) -> dict:
    """Promote one asset after the mode-authorized reviewer completes its packet."""
    attempt = attempt.resolve()
    contract = load_contract(attempt)
    design, _ = _load_design(attempt, contract)
    stage = _stage_dir(attempt, contract)
    review = _json(review_path, "stage5 review")
    kind = str(review.get("asset_type"))
    asset_id = str(review.get("asset_id"))
    expected_review_path = _review_path(stage, kind, asset_id).resolve()
    if review_path.resolve() != expected_review_path:
        raise Stage5Error(f"review는 stage5가 만든 고정 경로에 있어야 한다: {expected_review_path}")
    manifest_id = str(review.get("manifest_id") or "")
    manifest_path = stage / "qa" / "codex" / "manifests" / f"{manifest_id}.json"
    manifest = _json(manifest_path, "review source manifest")
    current_mode = load_execution_mode(attempt)
    recorded_mode = manifest.get("execution_mode") or {}
    fast_track = current_mode.get("mode") == FAST_TRACK_MODE
    if (manifest.get("schema_version") != "codex-stage5-jobs.v1" or
            manifest.get("status") not in {
                "finalized_pending_review", "finalized_pending_human_review"} or
            (manifest.get("contract") or {}).get("sha256") != contract.digest or
            manifest.get("source_shot_design_sha256") != _short_sha(_design_path(attempt, contract)) or
            recorded_mode.get("mode") != current_mode.get("mode") or
            recorded_mode.get("set_at") != current_mode.get("set_at")):
        raise Stage5Error("review source manifest가 현재 계약·shot cards와 결속되지 않는다")
    bound = next((item for item in manifest.get("review_assets") or []
                  if item.get("asset_type") == kind and item.get("asset_id") == asset_id), None)
    if not bound or bound.get("review_path") != str(expected_review_path.relative_to(attempt)):
        raise Stage5Error("review asset이 finalize manifest에 결속되어 있지 않다")
    if review.get("decision") not in {"approved", "rejected"}:
        raise Stage5Error("review decision은 approved 또는 rejected여야 한다")
    if not str(review.get("reviewer") or "").strip():
        raise Stage5Error("reviewer가 비어 있다")
    if not str(review.get("reviewed_at") or "").strip():
        raise Stage5Error("reviewed_at이 비어 있다")
    if review.get("decision") == "approved" and not _criteria_accepted(review, fast_track):
        raise Stage5Error(
            "승인하려면 모든 criteria가 pass여야 하며 fast_track만 근거 있는 accepted_defect를 허용한다")
    if kind == "manual":
        if (review.get("review_mode") != "ai_preflight" or
                review.get("human_approval_required") is not False or
                review.get("auto_approve_allowed") is not True):
            raise Stage5Error("manual review는 AI preflight 자동 승인 계약과 다르다")
    elif fast_track:
        if (review.get("review_mode") != "ai_fast_track" or
                review.get("human_approval_required") is not False or
                review.get("auto_approve_allowed") is not True or
                not str(review.get("reviewer") or "").startswith("codex-ai-fast-track")):
            raise Stage5Error("fast_track plate는 AI 자율 승인 영수증과 다르다")
    elif (review.get("review_mode") != "human" or
          review.get("human_approval_required") is not True or
          review.get("auto_approve_allowed") is not False):
        raise Stage5Error("normal mode plate는 사람 승인 계약이어야 한다")

    if kind == "manual" and review.get("schema_version") == "stage5-manual-review.v1":
        manual = next((item for _, item in _manuals(design)
                       if item.get("manual_id") == asset_id), None)
        if not manual:
            raise Stage5Error(f"shot cards에 manual이 없다: {asset_id}")
        expected_criteria = list((manual.get("approval") or {}).get("criteria", []))
        if [item.get("criterion") for item in review.get("criteria") or []] != expected_criteria:
            raise Stage5Error("manual review criteria가 shot cards와 다르다")
        if (review.get("clean_board") != bound.get("clean_board") or
                review.get("annotated_qa_board") != bound.get("annotated_qa_board")):
            raise Stage5Error("manual review asset 경로 또는 hash가 finalize 뒤 바뀌었다")
        source_record = review.get("clean_board") or {}
        source = attempt / str(source_record.get("path", ""))
        annotated_record = review.get("annotated_qa_board") or {}
        annotated = attempt / str(annotated_record.get("path", ""))
        if (not source.is_file() or source_record.get("sha256") != _sha(source) or
                not annotated.is_file() or annotated_record.get("sha256") != _sha(annotated)):
            raise Stage5Error("review 작성 뒤 manual clean/annotated asset이 바뀌었다")
        output = stage / "output" / "manuals" / f"{asset_id}.png"
        if review["decision"] == "approved":
            _archive_existing(stage, output, asset_id)
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, output)
            review["approved_output"] = str(output.relative_to(attempt))
            review["approved_output_sha256"] = _sha(output)
            record = {"manual_id": asset_id, "status": "approved",
                      "output": review["approved_output"], "sha256": _sha(output),
                      "annotated_qa_board": annotated_record,
                      "review_mode": review.get("review_mode"),
                      "reviewer": review["reviewer"], "reviewed_at": review["reviewed_at"],
                      "manifest_id": review.get("manifest_id")}
            receipt = _merge_receipt(stage, contract, kind, record)
        else:
            receipt = stage / "receipt.json"
    elif kind == "plate" and review.get("schema_version") == "stage5-plate-review.v1":
        shot = next((item for item in design.get("shots") or []
                     if item.get("shot_id") == asset_id), None)
        if not shot:
            raise Stage5Error(f"shot cards에 shot이 없다: {asset_id}")
        expected_criteria = list((shot.get("plate_acceptance") or {}).get("start", []))
        if [item.get("criterion") for item in review.get("criteria") or []] != expected_criteria:
            raise Stage5Error("plate review criteria가 shot cards와 다르다")
        if review.get("candidates") != bound.get("candidates"):
            raise Stage5Error("plate candidate 경로 또는 hash가 finalize 뒤 바뀌었다")
        selected = str(review.get("selected_candidate") or "")
        options = {str(item.get("candidate_id")): item for item in review.get("candidates") or []}
        if (len(options) != 1 or selected != "AI-SELECTED" or
                review.get("ai_retry_harness") !=
                (options.get(selected) or {}).get("ai_retry_harness")):
            raise Stage5Error("plate는 AI 순차 검수 하네스가 고른 단일 후보에 결속되어야 한다")
        if review["decision"] == "approved" and selected not in options:
            raise Stage5Error("selected_candidate가 candidates 안에 없다")
        source_direction = ((shot.get("motion_control") or {})
                            .get("screen_direction_contract") or {})
        direction_required = bool(source_direction.get("required"))
        if review.get("screen_direction_required") is not direction_required:
            raise Stage5Error("screen_direction_required가 shot cards와 다르다")
        if review["decision"] == "approved" and direction_required:
            direction = review.get("screen_direction") or {}
            if direction.get("allowed_depth_intents") != source_direction.get("allowed_depth_intents", []):
                raise Stage5Error("allowed_depth_intents가 shot cards와 다르다")
            if (not _valid_point(direction.get("start_center_normalized")) or
                    not _valid_point(direction.get("end_center_normalized")) or
                    not isinstance(direction.get("screen_direction_vector"), list) or
                    len(direction["screen_direction_vector"]) != 2 or
                    direction.get("depth_intent") not in direction.get("allowed_depth_intents", [])):
                raise Stage5Error("필수 screen_direction 좌표·벡터·depth_intent가 유효하지 않다")
        for item in options.values():
            path = attempt / str(item.get("path", ""))
            if not path.is_file() or item.get("sha256") != _sha(path):
                raise Stage5Error(f"plate candidate가 없거나 바뀌었다: {item.get('path')}")
        output = stage / "output" / "plates" / f"{asset_id}.png"
        if review["decision"] == "approved":
            source = attempt / options[selected]["path"]
            _archive_existing(stage, output, asset_id)
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, output)
            review["approved_output"] = str(output.relative_to(attempt))
            review["approved_output_sha256"] = _sha(output)
            record = {"shot_id": asset_id, "status": "approved", "selected_candidate": selected,
                      "output": review["approved_output"], "sha256": _sha(output),
                      "prompt_sha256": options[selected]["prompt_sha256"],
                      "imagegen_prompt_sha256": options[selected]["imagegen_prompt_sha256"],
                      "screen_direction": review.get("screen_direction"),
                      "review_mode": review.get("review_mode"),
                      "accepted_defects": review.get("accepted_defects") or [],
                      "reviewer": review["reviewer"], "reviewed_at": review["reviewed_at"],
                      "manifest_id": review.get("manifest_id")}
            receipt = _merge_receipt(stage, contract, kind, record)
        else:
            receipt = stage / "receipt.json"
    else:
        raise Stage5Error("지원하지 않는 stage5 review schema/asset_type")

    review_path.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
    handoff = _write_h3_handoff(attempt, contract, design)
    return {"asset_type": kind, "asset_id": asset_id, "decision": review["decision"],
            "receipt": str(receipt) if receipt.exists() else None, "h3_handoff": str(handoff)}


def main() -> int:
    parser = argparse.ArgumentParser(description="05-plate production preparation and mode-bound promotion")
    parser.add_argument("attempt", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--audit", action="store_true")
    mode.add_argument("--prepare", choices=["references", "manuals", "plates"])
    mode.add_argument("--record-reference-review", type=Path, metavar="MANIFEST")
    mode.add_argument("--record-ai-review", type=Path, metavar="MANIFEST")
    mode.add_argument("--finalize-manifest", type=Path)
    mode.add_argument("--apply-review", type=Path)
    parser.add_argument("--review-file", type=Path,
                        help="reference 또는 start-image AI review JSON")
    parser.add_argument("--only", nargs="*", help="shot id 또는 manual id")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--codex-surface", choices=sorted(CODEX_SURFACES), default="unknown")
    args = parser.parse_args()
    try:
        if args.audit:
            result = audit_inputs(args.attempt)
        elif args.prepare:
            result = prepare_codex_jobs(args.attempt, args.prepare, args.only, args.force)
        elif args.record_reference_review:
            if not args.review_file:
                raise Stage5Error("--record-reference-review에는 --review-file이 필요하다")
            result = record_ai_reference_review(
                args.attempt, args.record_reference_review, args.review_file)
        elif args.record_ai_review:
            if not args.review_file:
                raise Stage5Error("--record-ai-review에는 --review-file이 필요하다")
            result = record_ai_plate_review(
                args.attempt, args.record_ai_review, args.review_file)
        elif args.finalize_manifest:
            result = finalize_codex_jobs(args.attempt, args.finalize_manifest, args.codex_surface)
        else:
            result = apply_review(args.attempt, args.apply_review)
    except (Stage5Error, ContractError, ExecutionModeError) as error:
        print(json.dumps({"ok": False, "problem": str(error)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
