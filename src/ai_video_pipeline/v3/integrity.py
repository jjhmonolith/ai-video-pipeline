"""Deterministic integrity checks; no creative authorship lives here."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from PIL import Image

from .specs import (
    ARTIFACT_SCHEMA,
    CRITIC_CRITERIA,
    CRITIQUE_SCHEMA,
    MAX_ATTEMPTS,
    PIPELINE_VERSION,
    STAGE02_CANVAS_CONTRACT,
    STAGE02_INPUT_SCHEMA,
    STAGE02_INPUTS_SCHEMA,
    STAGE02_META_PROMPT_SCHEMA,
    STAGE02_REQUIRED_PANEL_IDS,
    STAGE02_SPEC_PATHS,
    STAGE02_WRITER_PROTOCOL,
    STAGE02_WRITER_RULES,
    STAGE_BY_ID,
)


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path, label: str = "JSON") -> dict:
    if not path.is_file():
        raise ValueError(f"{label} missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} unreadable: {path}: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object: {path}")
    return payload


def _problem(items: list[dict], code: str, path: str, message: str) -> None:
    items.append({"code": code, "path": path, "message": message})


def _warning(items: list[dict], code: str, path: str, message: str) -> None:
    items.append({"code": code, "path": path, "message": message})


def _required_text(data: dict, fields: Iterable[str], base: str, problems: list[dict]) -> None:
    for field in fields:
        if not str(data.get(field) or "").strip():
            _problem(problems, "required", f"{base}.{field}", "non-empty text is required")


def _safe_path(attempt: Path, value: Any, label: str, problems: list[dict], *, required: bool = True) -> Path | None:
    if not str(value or "").strip():
        if required:
            _problem(problems, "path-missing", label, "path is required")
        return None
    raw = Path(str(value))
    path = raw.resolve() if raw.is_absolute() else (attempt / raw).resolve()
    try:
        path.relative_to(attempt.resolve())
    except ValueError:
        _problem(problems, "path-escape", label, "path resolves outside the attempt")
        return None
    if required and not path.is_file():
        _problem(problems, "file-missing", label, f"file does not exist: {path}")
    return path


def _stage_artifact(attempt: Path, stage_id: str) -> dict:
    return load_json(attempt / stage_id / "output" / "stage-artifact.json", stage_id)


def _stage02_spec_file(kind: str) -> Path:
    return Path(__file__).resolve().parents[1] / "sheet_specs" / f"{kind}.md"


def stage02_authoring_inputs(attempt: Path) -> dict:
    """Bind Stage 02's non-creative source facts without writing creative prose."""
    premise = _stage_artifact(attempt.resolve(), "01-premise").get("content") or {}
    clauses = premise.get("contract_clauses") or []
    boards: list[dict] = []
    for subject in premise.get("subjects") or []:
        if not isinstance(subject, dict) or not subject.get("reference_required", True):
            continue
        subject_id = str(subject.get("subject_id") or "")
        kind = str(subject.get("kind") or "")
        definition = subject.get("definition") or {}
        spec_path = STAGE02_SPEC_PATHS.get(kind)
        spec_file = _stage02_spec_file(kind)
        specification = spec_file.read_text(encoding="utf-8") if spec_path and spec_file.is_file() else ""
        spec_sha256 = text_sha256(specification) if specification else ""
        base = {
            "schema_version": STAGE02_INPUT_SCHEMA,
            "writer_protocol": STAGE02_WRITER_PROTOCOL,
            "writer_rules": STAGE02_WRITER_RULES,
            "writer_rules_sha256": text_sha256(STAGE02_WRITER_RULES),
            "subject_id": subject_id,
            "subject_kind": kind,
            "source_definition": definition,
            "source_definition_sha256": canonical_sha256(definition),
            "contract_clauses": clauses,
            "contract_clauses_sha256": canonical_sha256(clauses),
            "canvas_contract": dict(STAGE02_CANVAS_CONTRACT),
            "spec_path": spec_path or "",
            "sheet_specification": specification,
            "spec_sha256": spec_sha256,
            "required_panel_ids": list(STAGE02_REQUIRED_PANEL_IDS.get(kind, ())),
        }
        boards.append({**base, "input_contract_sha256": canonical_sha256(base)})
    return {"schema_version": STAGE02_INPUTS_SCHEMA, "boards": boards}


def stage02_meta_prompt_sha256(meta: dict) -> str:
    """Fingerprint all source-bound and LLM-authored meta-prompt sections."""
    return canonical_sha256({
        "input_contract": meta.get("input_contract"),
        "sheet_policy": meta.get("sheet_policy"),
        "panel_plan": meta.get("panel_plan"),
    })


def _orientation(width: int, height: int) -> str:
    return "landscape" if width > height else "portrait" if height > width else "square"


def _validate_frame(frame: Any, path: str, problems: list[dict]) -> None:
    if not isinstance(frame, dict):
        _problem(problems, "frame", path, "frame must be an object")
        return
    width, height, fps = frame.get("width"), frame.get("height"), frame.get("fps")
    if not all(isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0
               for value in (width, height, fps)):
        _problem(problems, "frame", path, "positive width, height, and fps are required")
        return
    if frame.get("orientation") != _orientation(int(width), int(height)):
        _problem(problems, "orientation", f"{path}.orientation", "orientation contradicts width and height")


def _validate_runtime(runtime: Any, problems: list[dict]) -> None:
    if not isinstance(runtime, dict):
        _problem(problems, "runtime", "content.runtime_contract", "runtime contract must be an object")
        return
    mode = runtime.get("mode")
    if mode not in {"fixed", "range", "open"}:
        _problem(problems, "runtime", "content.runtime_contract.mode", "mode must be fixed, range, or open")
    if mode == "fixed":
        value = runtime.get("target_seconds")
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
            _problem(problems, "runtime", "content.runtime_contract.target_seconds", "positive target required")
    if mode == "range":
        low, high = runtime.get("min_seconds"), runtime.get("max_seconds")
        if not all(isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0
                   for value in (low, high)) or float(low) > float(high):
            _problem(problems, "runtime", "content.runtime_contract", "valid positive min/max range required")


def _pixel_tolerance(target: int) -> int:
    return max(1, min(16, round(target * 0.01)))


def _validate_image(attempt: Path, record: dict, base: str,
                    problems: list[dict], warnings: list[dict]) -> None:
    requested = record.get("requested")
    if (not isinstance(requested, list) or len(requested) != 2
            or not all(isinstance(value, int) and value > 0 for value in requested)):
        _problem(problems, "image-size", f"{base}.requested", "requested must be [width, height]")
        return
    path = _safe_path(attempt, record.get("selected_image"), f"{base}.selected_image", problems)
    if not path or not path.is_file():
        return
    try:
        with Image.open(path) as image:
            actual = image.size
    except Exception as error:
        _problem(problems, "image-read", f"{base}.selected_image", f"cannot read image: {error}")
        return
    target = tuple(requested)
    if actual != target:
        within = all(abs(got - want) <= _pixel_tolerance(want)
                     for got, want in zip(actual, target))
        if within:
            _warning(warnings, "minor-pixel-variance", base,
                     f"provider pixels {actual} accepted near target {target}")
        else:
            _problem(problems, "pixel-mismatch", base,
                     f"provider pixels {actual} exceed tolerance around {target}")


def _validate_attempt_chain(attempt: Path, record: dict, base: str,
                            problems: list[dict], mode: str) -> None:
    attempts = record.get("attempts")
    selected = record.get("selected_attempt")
    if not isinstance(attempts, list) or not attempts:
        _problem(problems, "attempts", f"{base}.attempts", "at least one attempt is required")
        return
    if len(attempts) > MAX_ATTEMPTS:
        _problem(problems, "attempt-limit", f"{base}.attempts", "more than ten attempts")
    if not all(isinstance(item, dict) for item in attempts):
        _problem(problems, "attempt-record", f"{base}.attempts", "every attempt must be an object")
        return
    numbers = [item.get("attempt") for item in attempts]
    if numbers != list(range(1, len(attempts) + 1)):
        _problem(problems, "attempt-order", f"{base}.attempts", "attempts must be contiguous from 1")
    strategies = [str(item.get("variation_strategy") or "") for item in attempts]
    if any(not value for value in strategies) or len(strategies) != len(set(strategies)):
        _problem(problems, "attempt-variation", f"{base}.attempts",
                 "every attempt needs a distinct non-empty strategy")
    for index, item in enumerate(attempts):
        item_base = f"{base}.attempts[{index}]"
        _required_text(item, ("prompt",), item_base, problems)
        _safe_path(attempt, item.get("candidate_path"), f"{item_base}.candidate_path", problems)
        decision = item.get("decision")
        allowed = {"fail", "pass"}
        if mode == "fast_track" and item.get("attempt") == MAX_ATTEMPTS:
            allowed.add("accepted_defect")
        if decision not in allowed:
            _problem(problems, "attempt-decision", f"{item_base}.decision",
                     f"decision must be one of {sorted(allowed)}")
        review = item.get("review")
        if not isinstance(review, dict) or review.get("decision") != decision:
            _problem(problems, "attempt-review", f"{item_base}.review",
                     "review object must repeat the attempt decision")
        elif not str(review.get("evidence") or "").strip():
            _problem(problems, "attempt-review", f"{item_base}.review.evidence",
                     "concrete review evidence is required")
        if index and attempts[index - 1].get("decision") != "fail":
            _problem(problems, "retry-without-failure", item_base,
                     "a new candidate may exist only after the previous candidate failed")
    if selected not in numbers:
        _problem(problems, "attempt-selection", f"{base}.selected_attempt", "selected attempt is absent")
    if selected != len(attempts):
        _problem(problems, "attempt-selection", f"{base}.selected_attempt",
                 "generation must stop at and select the final attempted candidate")
    selected_record = next((item for item in attempts if item.get("attempt") == selected), {})
    decision = selected_record.get("decision")
    if decision == "accepted_defect" and not (mode == "fast_track" and selected == MAX_ATTEMPTS):
        _problem(problems, "accepted-defect-authority", base,
                 "accepted_defect is allowed only at fast-track attempt 10")
    if decision not in {"pass", "accepted_defect"}:
        _problem(problems, "attempt-selection", base, "selected attempt must pass or be an authorized accepted defect")


def _scene_records(content: dict) -> list[dict]:
    return [scene for sequence in content.get("sequences") or [] if isinstance(sequence, dict)
            for scene in sequence.get("scenes") or [] if isinstance(scene, dict)]


def _validate_common(artifact: dict, stage_id: str, problems: list[dict]) -> dict:
    if artifact.get("schema_version") != ARTIFACT_SCHEMA:
        _problem(problems, "schema", "schema_version", f"must be {ARTIFACT_SCHEMA}")
    if artifact.get("pipeline_version") != PIPELINE_VERSION:
        _problem(problems, "pipeline-version", "pipeline_version", f"must be {PIPELINE_VERSION}")
    if artifact.get("stage_id") != stage_id:
        _problem(problems, "stage", "stage_id", f"must be {stage_id}")
    _required_text(artifact, ("attempt_id", "authored_by", "authored_at"), "artifact", problems)
    if not isinstance(artifact.get("input_receipts"), list):
        _problem(problems, "input-receipts", "input_receipts", "must be a list")
    if not isinstance(artifact.get("creative_decisions"), list):
        _problem(problems, "creative-decisions", "creative_decisions", "must be a list")
    content = artifact.get("content")
    if not isinstance(content, dict):
        _problem(problems, "content", "content", "must be an object")
        return {}
    return content


def _validate_stage01(content: dict, problems: list[dict]) -> None:
    direction = content.get("direction")
    if not isinstance(direction, dict) or not str(direction.get("verbatim") or "").strip():
        _problem(problems, "direction", "content.direction.verbatim", "verbatim user direction is required")
    _validate_runtime(content.get("runtime_contract"), problems)
    _validate_frame(content.get("frame"), "content.frame", problems)
    _validate_frame(content.get("delivery_frame"), "content.delivery_frame", problems)
    subjects = content.get("subjects")
    if not isinstance(subjects, list) or not subjects:
        _problem(problems, "subjects", "content.subjects", "at least one subject is required")
        return
    ids = []
    for index, subject in enumerate(subjects):
        base = f"content.subjects[{index}]"
        if not isinstance(subject, dict):
            _problem(problems, "subject", base, "subject must be an object")
            continue
        _required_text(subject, ("subject_id", "kind", "purpose"), base, problems)
        ids.append(subject.get("subject_id"))
        if not isinstance(subject.get("definition"), dict) or not subject.get("definition"):
            _problem(problems, "definition", f"{base}.definition", "non-empty LLM-authored definition required")
    if len(ids) != len(set(ids)):
        _problem(problems, "subject-id", "content.subjects", "subject IDs must be unique")


def _validate_stage02(attempt: Path, content: dict, problems: list[dict],
                      warnings: list[dict], mode: str) -> None:
    premise = _stage_artifact(attempt, "01-premise").get("content") or {}
    required = {str(item.get("subject_id")) for item in premise.get("subjects") or []
                if item.get("reference_required", True)}
    boards = content.get("boards")
    if not isinstance(boards, list):
        _problem(problems, "boards", "content.boards", "boards must be a list")
        return
    expected_inputs = {
        item["subject_id"]: item for item in stage02_authoring_inputs(attempt).get("boards") or []
    }
    found: list[str] = []
    for index, board in enumerate(boards):
        base = f"content.boards[{index}]"
        if not isinstance(board, dict):
            _problem(problems, "board", base, "board must be an object")
            continue
        _required_text(board, ("board_id", "subject_id"), base, problems)
        subject_id = str(board.get("subject_id") or "")
        found.append(subject_id)
        expected_input = expected_inputs.get(subject_id)
        meta = board.get("structured_meta_prompt")
        if not isinstance(meta, dict):
            _problem(problems, "meta-prompt", f"{base}.structured_meta_prompt", "structured meta-prompt required")
        else:
            if meta.get("schema_version") != STAGE02_META_PROMPT_SCHEMA:
                _problem(problems, "meta-prompt-schema", f"{base}.structured_meta_prompt.schema_version",
                         f"must be {STAGE02_META_PROMPT_SCHEMA}")
            if expected_input is None:
                _problem(problems, "meta-input", f"{base}.structured_meta_prompt.input_contract",
                         "cannot bind an unknown Stage 01 subject")
            elif meta.get("input_contract") != expected_input:
                _problem(problems, "meta-input-drift", f"{base}.structured_meta_prompt.input_contract",
                         "input contract must exactly match the Stage 02 work order")

            policy = meta.get("sheet_policy")
            if not isinstance(policy, dict):
                _problem(problems, "sheet-policy", f"{base}.structured_meta_prompt.sheet_policy",
                         "LLM-authored sheet policy is required")
            else:
                _required_text(policy, (
                    "purpose", "background", "consistency", "layout_logic",
                    "labeling_policy", "proof_goal",
                ), f"{base}.structured_meta_prompt.sheet_policy", problems)

            panel_plan = meta.get("panel_plan")
            expected_ids = list((expected_input or {}).get("required_panel_ids") or [])
            if not isinstance(panel_plan, list):
                _problem(problems, "sheet-panel-contract", f"{base}.structured_meta_prompt.panel_plan",
                         "nine-panel plan must be a list")
            else:
                panel_ids = [item.get("panel_id") if isinstance(item, dict) else None
                             for item in panel_plan]
                if panel_ids != expected_ids:
                    _problem(problems, "sheet-panel-contract", f"{base}.structured_meta_prompt.panel_plan",
                             f"must contain the canonical nine panels in order: {expected_ids}")
                for panel_index, panel in enumerate(panel_plan):
                    panel_base = f"{base}.structured_meta_prompt.panel_plan[{panel_index}]"
                    if not isinstance(panel, dict):
                        _problem(problems, "sheet-panel-contract", panel_base, "panel must be an object")
                        continue
                    _required_text(panel, ("purpose",), panel_base, problems)
                    must_show = panel.get("must_show")
                    if not isinstance(must_show, list) or not must_show or not all(
                            str(item or "").strip() for item in must_show):
                        _problem(problems, "sheet-panel-contract", f"{panel_base}.must_show",
                                 "non-empty visible requirements are required")

            image_prompt = meta.get("image_prompt")
            if not str(image_prompt or "").strip():
                _problem(problems, "meta-prompt", f"{base}.structured_meta_prompt.image_prompt",
                         "exact A01 image prompt is required")
            elif meta.get("image_prompt_sha256") != text_sha256(str(image_prompt)):
                _problem(problems, "prompt-hash", f"{base}.structured_meta_prompt.image_prompt_sha256",
                         "image prompt hash mismatch")
            if meta.get("meta_prompt_sha256") != stage02_meta_prompt_sha256(meta):
                _problem(problems, "meta-prompt-hash", f"{base}.structured_meta_prompt.meta_prompt_sha256",
                         "structured meta-prompt hash mismatch")

        if board.get("requested") != [STAGE02_CANVAS_CONTRACT["width"],
                                       STAGE02_CANVAS_CONTRACT["height"]]:
            _problem(problems, "sheet-canvas", f"{base}.requested",
                     "reference sheets must use the fixed 1672x941 landscape board, independent of video frame")
        _validate_attempt_chain(attempt, board, base, problems, mode)
        _validate_image(attempt, board, base, problems, warnings)
        attempts = board.get("attempts") or []
        if isinstance(meta, dict) and attempts and isinstance(attempts[0], dict):
            if attempts[0].get("prompt") != meta.get("image_prompt"):
                _problem(problems, "prompt-binding", f"{base}.attempts[0].prompt",
                         "A01 must use the structured meta-prompt image_prompt verbatim")
        selected = next((item for item in board.get("attempts") or []
                         if item.get("attempt") == board.get("selected_attempt")), None)
        if selected and board.get("selected_image") != selected.get("candidate_path"):
            _problem(problems, "image-selection", f"{base}.selected_image",
                     "selected image must equal the selected attempt candidate")
    found_set = set(found)
    if len(found) != len(found_set):
        _problem(problems, "board-subject", "content.boards", "each subject may have only one board")
    if required - found_set:
        _problem(problems, "board-coverage", "content.boards", f"missing subjects: {sorted(required - found_set)}")
    if found_set - {str(item.get("subject_id")) for item in premise.get("subjects") or []}:
        _problem(problems, "board-subject", "content.boards", "board references unknown Stage 01 subject")
    cross_review = content.get("cross_board_review")
    if not isinstance(cross_review, dict) or cross_review.get("decision") not in {"pass", "accepted_defect"}:
        _problem(problems, "cross-board-review", "content.cross_board_review",
                 "passing cross-board review is required")
    elif not str(cross_review.get("evidence") or "").strip():
        _problem(problems, "cross-board-review", "content.cross_board_review.evidence",
                 "concrete cross-board evidence is required")


def _validate_stage03(content: dict, problems: list[dict]) -> None:
    sequences = content.get("sequences")
    if not isinstance(sequences, list) or not sequences:
        _problem(problems, "sequences", "content.sequences", "at least one sequence is required")
        return
    scenes = _scene_records(content)
    scene_ids, event_ids, requirement_ids = [], [], []
    for s_index, scene in enumerate(scenes):
        base = f"content.scenes[{s_index}]"
        _required_text(scene, ("scene_id", "intent", "role", "pov_owner", "dramatic_question",
                               "entry_state", "exit_state"), base, problems)
        scene_ids.append(scene.get("scene_id"))
        forbidden = {"camera", "lens", "shot_id", "cut_id", "edit_target_seconds"}.intersection(scene)
        if forbidden:
            _problem(problems, "premature-shot-design", base, f"Stage 03 cannot own {sorted(forbidden)}")
        estimate = scene.get("estimated_edit_range_seconds")
        if (not isinstance(estimate, list) or len(estimate) != 2
                or not all(isinstance(value, (int, float)) and value > 0 for value in estimate)
                or estimate[0] > estimate[1]):
            _problem(problems, "scene-range", f"{base}.estimated_edit_range_seconds", "valid positive range required")
        events = scene.get("events")
        if not isinstance(events, list) or not events:
            _problem(problems, "events", f"{base}.events", "at least one dramatic event required")
            events = []
        for event in events:
            if isinstance(event, dict):
                _required_text(event, ("event_id", "action", "visible_change", "result_state"), base, problems)
                event_ids.append(event.get("event_id"))
        for requirement in scene.get("production_requirements") or []:
            if not isinstance(requirement, dict):
                continue
            rid = str(requirement.get("requirement_id") or "")
            if not rid.startswith("NEW-"):
                _problem(problems, "reference-debt-id", base, "new requirements must use NEW- IDs")
            _required_text(requirement, ("requirement_id", "name", "asset_class", "description",
                                         "reference_policy"), base, problems)
            requirement_ids.append(rid)
        for event in events:
            target = str((event or {}).get("target_subject_id") or "")
            if target.startswith("NEW-") and target not in requirement_ids:
                _problem(problems, "reference-debt", base, f"{target} is not registered in production_requirements")
    if len(scene_ids) != len(set(scene_ids)) or any(not value for value in scene_ids):
        _problem(problems, "scene-id", "content.sequences", "scene IDs must be unique and non-empty")
    if len(event_ids) != len(set(event_ids)) or any(not value for value in event_ids):
        _problem(problems, "event-id", "content.sequences", "event IDs must be unique and non-empty")
    if len(requirement_ids) != len(set(requirement_ids)) or any(not value for value in requirement_ids):
        _problem(problems, "reference-debt-id", "content.sequences",
                 "production requirement IDs must be unique and non-empty")


def _validate_stage04(attempt: Path, content: dict, problems: list[dict]) -> None:
    scenario = _stage_artifact(attempt, "03-scenario").get("content") or {}
    source_scenes = {str(scene.get("scene_id")): scene for scene in _scene_records(scenario)}
    source_events = {str(event.get("event_id")): event for scene in source_scenes.values()
                     for event in scene.get("events") or [] if isinstance(event, dict)}
    plans = content.get("scene_plans")
    if not isinstance(plans, list):
        _problem(problems, "scene-plans", "content.scene_plans", "scene plans must be a list")
        return
    seen_scenes, seen_events, shot_ids = set(), set(), []
    total = 0.0
    for p_index, plan in enumerate(plans):
        base = f"content.scene_plans[{p_index}]"
        if not isinstance(plan, dict):
            _problem(problems, "scene-plan", base, "scene plan must be an object")
            continue
        scene_id = str(plan.get("scene_id") or "")
        seen_scenes.add(scene_id)
        treatment = plan.get("treatment") or {}
        _required_text(treatment, ("intent", "pov", "blocking", "coverage_logic"), f"{base}.treatment", problems)
        for setup in plan.get("setups") or []:
            _required_text(setup, ("setup_id", "lighting_continuity"), f"{base}.setups", problems)
            for shot in setup.get("shots") or []:
                shot_base = f"{base}.shots"
                _required_text(shot, ("shot_id", "purpose", "composition", "frame_size"), shot_base, problems)
                shot_ids.append(shot.get("shot_id"))
                events = {str(value) for value in shot.get("event_ids") or []}
                if events - set(source_events):
                    _problem(problems, "event-binding", shot_base, f"unknown events: {sorted(events - set(source_events))}")
                seen_events.update(events)
                camera = shot.get("camera") or {}
                _required_text(camera, ("movement", "speed", "framing", "end", "angle", "rationale"),
                               f"{shot_base}.camera", problems)
                cast = [str(value) for value in shot.get("visible_cast_ids") or []]
                if len(cast) == 2 and shot.get("composition") not in {"two_shot", "over_the_shoulder"}:
                    _problem(problems, "cast-composition", shot_base,
                             "two visible people require two_shot or over_the_shoulder")
                timing = shot.get("timing") or {}
                value = timing.get("edit_target_seconds")
                if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
                    _problem(problems, "shot-time", f"{shot_base}.timing.edit_target_seconds", "positive authored duration required")
                elif shot.get("included_in_timeline", True):
                    total += float(value)
                _required_text(timing, ("temporal_mode", "dramatic_reason", "execution_method"),
                               f"{shot_base}.timing", problems)
                domains = timing.get("time_domains") or {}
                _required_text(domains, ("subject", "world", "camera"), f"{shot_base}.timing.time_domains", problems)
                performance = shot.get("performance") or {}
                if not isinstance(performance.get("phases"), list) or not performance.get("phases"):
                    _problem(problems, "performance", f"{shot_base}.performance.phases", "authored phases required")
    if set(source_scenes) != seen_scenes:
        _problem(problems, "scene-coverage", "content.scene_plans",
                 f"scene coverage differs: expected {sorted(source_scenes)}, got {sorted(seen_scenes)}")
    if set(source_events) - seen_events:
        _problem(problems, "event-coverage", "content.scene_plans", f"missing events: {sorted(set(source_events) - seen_events)}")
    if len(shot_ids) != len(set(shot_ids)) or any(not value for value in shot_ids):
        _problem(problems, "shot-id", "content.scene_plans", "shot IDs must be unique and non-empty")
    premise = _stage_artifact(attempt, "01-premise").get("content") or {}
    runtime = premise.get("runtime_contract") or {}
    if runtime.get("mode") == "fixed" and abs(total - float(runtime.get("target_seconds") or 0)) > 0.05:
        _problem(problems, "runtime-sum", "content.scene_plans",
                 f"timeline total {total:g}s does not equal fixed runtime {runtime.get('target_seconds')}s")


def _required_reference_debt(attempt: Path) -> set[str]:
    scenario = _stage_artifact(attempt, "03-scenario").get("content") or {}
    required = set()
    for scene in _scene_records(scenario):
        for item in scene.get("production_requirements") or []:
            if (item.get("reference_policy") not in {"prompt_only", "none"}
                    and item.get("asset_class") not in {"background_dressing", "offscreen_only"}):
                required.add(str(item.get("requirement_id")))
    return required


def _timeline_shots(attempt: Path) -> list[dict]:
    design = _stage_artifact(attempt, "04-shot-design").get("content") or {}
    return [shot for plan in design.get("scene_plans") or [] for setup in plan.get("setups") or []
            for shot in setup.get("shots") or [] if shot.get("included_in_timeline", True)]


def _validate_stage05(attempt: Path, content: dict, problems: list[dict],
                      warnings: list[dict], mode: str) -> None:
    references = content.get("references")
    if not isinstance(references, list):
        _problem(problems, "references", "content.references", "references must be a list")
        return
    fulfilled = {str(item.get("subject_or_requirement_id")) for item in references if isinstance(item, dict)}
    if _required_reference_debt(attempt) - fulfilled:
        _problem(problems, "reference-debt", "content.references",
                 f"unfulfilled debt: {sorted(_required_reference_debt(attempt) - fulfilled)}")
    sheet_content = _stage_artifact(attempt, "02-sheet").get("content") or {}
    sheet_by_subject = {str(item.get("subject_id")): item for item in sheet_content.get("boards") or []
                        if isinstance(item, dict)}
    if set(sheet_by_subject) - fulfilled:
        _problem(problems, "reference-sheet-coverage", "content.references",
                 f"missing approved Stage 02 boards: {sorted(set(sheet_by_subject) - fulfilled)}")
    preflight = content.get("global_reference_preflight") or {}
    if preflight.get("decision") != "pass":
        _problem(problems, "reference-preflight", "content.global_reference_preflight", "all references must pass first")
    reference_ids: set[str] = set()
    for index, reference in enumerate(references):
        base = f"content.references[{index}]"
        if not isinstance(reference, dict):
            _problem(problems, "reference", base, "reference must be an object")
            continue
        _required_text(reference, ("reference_id", "subject_or_requirement_id", "origin", "purpose"),
                       base, problems)
        reference_ids.add(str(reference.get("reference_id") or ""))
        if reference.get("origin") not in {"stage02", "stage05"}:
            _problem(problems, "reference-origin", f"{base}.origin", "origin must be stage02 or stage05")
        _validate_image(attempt, reference, base, problems, warnings)
        review = reference.get("review") or {}
        if review.get("decision") not in {"pass", "accepted_defect"}:
            _problem(problems, "reference-review", f"{base}.review", "selected reference must pass review")
        if not str(review.get("evidence") or "").strip():
            _problem(problems, "reference-review", f"{base}.review.evidence", "review evidence is required")
        if reference.get("origin") == "stage05":
            _validate_attempt_chain(attempt, reference, base, problems, mode)
            selected = next((item for item in reference.get("attempts") or []
                             if item.get("attempt") == reference.get("selected_attempt")), None)
            if selected and reference.get("selected_image") != selected.get("candidate_path"):
                _problem(problems, "image-selection", f"{base}.selected_image",
                         "selected image must equal the selected attempt candidate")
        else:
            source = sheet_by_subject.get(str(reference.get("subject_or_requirement_id") or ""))
            if not source:
                _problem(problems, "reference-origin", base,
                         "stage02 reference does not bind an approved Stage 02 board")
            elif reference.get("selected_image") != source.get("selected_image"):
                _problem(problems, "reference-drift", f"{base}.selected_image",
                         "reused reference path differs from the approved Stage 02 board")
    if len(reference_ids) != len(references) or "" in reference_ids:
        _problem(problems, "reference-id", "content.references", "reference IDs must be unique and non-empty")
    if set(str(value) for value in preflight.get("reference_ids") or []) != reference_ids:
        _problem(problems, "reference-preflight", "content.global_reference_preflight.reference_ids",
                 "preflight must bind every unique reference")
    completed = str(content.get("references_completed_at") or "").strip()
    started = str(content.get("plates_started_at") or "").strip()
    if not completed or not started:
        _problem(problems, "reference-order", "content",
                 "references_completed_at and plates_started_at are required")
    else:
        try:
            completed_at = datetime.fromisoformat(completed.replace("Z", "+00:00"))
            started_at = datetime.fromisoformat(started.replace("Z", "+00:00"))
            if completed_at > started_at:
                _problem(problems, "reference-order", "content", "plates started before reference completion")
        except (ValueError, TypeError):
            _problem(problems, "reference-order", "content", "timestamps must be ISO 8601")
    plates = content.get("plates")
    if not isinstance(plates, list):
        _problem(problems, "plates", "content.plates", "plates must be a list")
        return
    expected = {str(shot.get("shot_id")) for shot in _timeline_shots(attempt)}
    found = set()
    for index, plate in enumerate(plates):
        base = f"content.plates[{index}]"
        found.add(str(plate.get("shot_id") or ""))
        if plate.get("role") != "start":
            _problem(problems, "plate-role", f"{base}.role", "production creates start plates only")
        if plate.get("end_plate"):
            _problem(problems, "end-plate", f"{base}.end_plate", "end plates are forbidden in production")
        _validate_attempt_chain(attempt, plate, base, problems, mode)
        _validate_image(attempt, plate, base, problems, warnings)
        selected = next((item for item in plate.get("attempts") or []
                         if item.get("attempt") == plate.get("selected_attempt")), None)
        if selected and plate.get("selected_image") != selected.get("candidate_path"):
            _problem(problems, "image-selection", f"{base}.selected_image",
                     "selected image must equal the selected attempt candidate")
        if set(str(value) for value in plate.get("reference_ids") or []) - reference_ids:
            _problem(problems, "plate-reference", base, "plate binds an unknown reference")
        source_shot = next((shot for shot in _timeline_shots(attempt)
                            if str(shot.get("shot_id")) == str(plate.get("shot_id"))), {})
        required_subjects = {str(value) for value in source_shot.get("required_reference_subject_ids") or []}
        bound_subjects = {str(reference.get("subject_or_requirement_id")) for reference in references
                          if reference.get("reference_id") in (plate.get("reference_ids") or [])}
        if required_subjects - bound_subjects:
            _problem(problems, "plate-reference-coverage", base,
                     f"missing required reference subjects: {sorted(required_subjects - bound_subjects)}")
    if found != expected:
        _problem(problems, "plate-coverage", "content.plates",
                 f"plate coverage differs: expected {sorted(expected)}, got {sorted(found)}")


def _validate_stage055(attempt: Path, content: dict, problems: list[dict]) -> None:
    refinements = content.get("shots")
    if not isinstance(refinements, list):
        _problem(problems, "motion-prompt-shots", "content.shots", "shots must be a list")
        return
    source_shots = {str(shot.get("shot_id")): shot for shot in _timeline_shots(attempt)}
    expected = set(source_shots)
    plate_content = _stage_artifact(attempt, "05-plate").get("content") or {}
    plates = {str(item.get("shot_id")): item for item in plate_content.get("plates") or []
              if isinstance(item, dict)}
    references = {str(item.get("reference_id")): item for item in plate_content.get("references") or []
                  if isinstance(item, dict)}
    found = set()
    for index, refinement in enumerate(refinements):
        base = f"content.shots[{index}]"
        if not isinstance(refinement, dict):
            _problem(problems, "motion-prompt-shot", base, "shot refinement must be an object")
            continue
        shot_id = str(refinement.get("shot_id") or "")
        found.add(shot_id)
        _required_text(refinement, ("shot_id", "shot_intent", "final_c01_prompt",
                                    "refinement_rationale"), base, problems)
        scenario_context = refinement.get("scenario_context")
        if not isinstance(scenario_context, dict):
            _problem(problems, "scenario-context", f"{base}.scenario_context",
                     "scenario_context must be an object")
        else:
            _required_text(scenario_context, ("scene_id", "dramatic_function",
                                               "entry_to_exit_change"),
                           f"{base}.scenario_context", problems)
            if scenario_context.get("event_ids") != (source_shots.get(shot_id) or {}).get("event_ids"):
                _problem(problems, "event-binding-drift", f"{base}.scenario_context.event_ids",
                         "event IDs must match the Stage 04 shot contract exactly")
        source_plate = plates.get(shot_id) or {}
        if refinement.get("start_plate") != source_plate.get("selected_image"):
            _problem(problems, "plate-selection-drift", f"{base}.start_plate",
                     "prompt refinement must use the selected Stage 05 start plate")
        plate_path = _safe_path(attempt, refinement.get("start_plate"),
                                f"{base}.start_plate", problems)
        if plate_path and plate_path.is_file():
            if refinement.get("start_plate_sha256") != file_sha256(plate_path):
                _problem(problems, "plate-hash-drift", f"{base}.start_plate_sha256",
                         "start plate hash does not match the inspected file")

        bindings = refinement.get("reference_bindings")
        if not isinstance(bindings, list):
            _problem(problems, "reference-bindings", f"{base}.reference_bindings",
                     "reference_bindings must be a list")
            bindings = []
        expected_reference_ids = [str(value) for value in source_plate.get("reference_ids") or []]
        actual_reference_ids = [str(item.get("reference_id") or "")
                                for item in bindings if isinstance(item, dict)]
        if actual_reference_ids != expected_reference_ids:
            _problem(problems, "reference-binding-drift", f"{base}.reference_bindings",
                     "reference bindings must preserve the exact Stage 05 plate reference order")
        for binding_index, binding in enumerate(bindings):
            binding_base = f"{base}.reference_bindings[{binding_index}]"
            if not isinstance(binding, dict):
                _problem(problems, "reference-binding", binding_base,
                         "reference binding must be an object")
                continue
            _required_text(binding, ("reference_id", "path", "sha256"), binding_base, problems)
            reference = references.get(str(binding.get("reference_id") or "")) or {}
            if binding.get("path") != reference.get("selected_image"):
                _problem(problems, "reference-path-drift", f"{binding_base}.path",
                         "reference path differs from the selected Stage 05 reference")
            reference_path = _safe_path(attempt, binding.get("path"), f"{binding_base}.path", problems)
            if (reference_path and reference_path.is_file()
                    and binding.get("sha256") != file_sha256(reference_path)):
                _problem(problems, "reference-hash-drift", f"{binding_base}.sha256",
                         "reference hash does not match the inspected file")

        observation = refinement.get("plate_observation")
        if not isinstance(observation, dict):
            _problem(problems, "plate-observation", f"{base}.plate_observation",
                     "plate_observation must be an object")
        else:
            _required_text(observation, ("visible_start_state", "spatial_relations",
                                         "contact_and_occupancy",
                                         "composition_and_motion_affordances"),
                           f"{base}.plate_observation", problems)

        status = refinement.get("realization_status")
        if status not in {"ready", "ready_with_adaptation"}:
            _problem(problems, "realization-status", f"{base}.realization_status",
                     "status must be ready or ready_with_adaptation; Stage 05 owns plate rejection")
        _required_text(refinement, ("adaptation_reason", "generator_translation"), base, problems)

        realization = refinement.get("motion_realization")
        if not isinstance(realization, dict):
            _problem(problems, "motion-realization", f"{base}.motion_realization",
                     "motion_realization must be an object")
        else:
            _required_text(realization, ("opening_transition", "performance_direction",
                                         "world_response", "camera_execution",
                                         "shooting_technique_translation", "temporal_execution",
                                         "ending_state"),
                           f"{base}.motion_realization", problems)
            phases = realization.get("ordered_action_phases")
            if not isinstance(phases, list) or not phases:
                _problem(problems, "action-phases",
                         f"{base}.motion_realization.ordered_action_phases",
                         "at least one ordered action phase is required")
            else:
                for phase_index, phase in enumerate(phases):
                    phase_base = f"{base}.motion_realization.ordered_action_phases[{phase_index}]"
                    if not isinstance(phase, dict):
                        _problem(problems, "action-phase", phase_base,
                                 "action phase must be an object")
                        continue
                    _required_text(phase, ("phase", "action", "visible_result"),
                                   phase_base, problems)

        constraints = refinement.get("continuity_constraints")
        if (not isinstance(constraints, list) or not constraints
                or any(not str(value or "").strip() for value in constraints)):
            _problem(problems, "continuity-constraints", f"{base}.continuity_constraints",
                     "at least one non-empty continuity constraint is required")
    if found != expected:
        _problem(problems, "motion-prompt-coverage", "content.shots",
                 f"motion prompt coverage differs: expected {sorted(expected)}, got {sorted(found)}")


def _validate_stage06(attempt: Path, content: dict, problems: list[dict], mode: str) -> None:
    jobs = content.get("shots")
    if not isinstance(jobs, list):
        _problem(problems, "motion-shots", "content.shots", "shots must be a list")
        return
    expected = {str(shot.get("shot_id")) for shot in _timeline_shots(attempt)}
    plates = _stage_artifact(attempt, "05-plate").get("content") or {}
    selected_plates = {str(item.get("shot_id")): item.get("selected_image")
                       for item in plates.get("plates") or [] if isinstance(item, dict)}
    prompt_content = _stage_artifact(attempt, "05.5-motion-prompt").get("content") or {}
    prompt_refinements = {str(item.get("shot_id")): item for item in prompt_content.get("shots") or []
                          if isinstance(item, dict)}
    found = set()
    for index, job in enumerate(jobs):
        base = f"content.shots[{index}]"
        shot_id = str(job.get("shot_id") or "")
        found.add(shot_id)
        if job.get("start_plate") != selected_plates.get(shot_id):
            _problem(problems, "plate-selection-drift", f"{base}.start_plate",
                     "motion input differs from the selected Stage 05 start plate")
        _safe_path(attempt, job.get("start_plate"), f"{base}.start_plate", problems)
        candidates = job.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            _problem(problems, "candidates", f"{base}.candidates", "C01 is required")
            continue
        if len(candidates) > MAX_ATTEMPTS:
            _problem(problems, "candidate-limit", f"{base}.candidates", "more than C10")
        ids = [item.get("candidate_id") for item in candidates]
        want = [f"C{number:02d}" for number in range(1, len(candidates) + 1)]
        if ids != want:
            _problem(problems, "candidate-order", f"{base}.candidates", "candidate IDs must be contiguous from C01")
        approved_c01_prompt = (prompt_refinements.get(shot_id) or {}).get("final_c01_prompt")
        if candidates[0].get("prompt") != approved_c01_prompt:
            _problem(problems, "c01-prompt-drift", f"{base}.candidates[0].prompt",
                     "C01 prompt must equal the approved Stage 05.5 final prompt verbatim")
        strategies = [str(item.get("variation_strategy") or "") for item in candidates[1:]]
        if any(not value for value in strategies) or len(strategies) != len(set(strategies)):
            _problem(problems, "candidate-variation", f"{base}.candidates", "each retry needs a distinct strategy")
        for c_index, candidate in enumerate(candidates):
            cbase = f"{base}.candidates[{c_index}]"
            _required_text(candidate, ("candidate_id", "prompt", "variation_strategy"), cbase, problems)
            _safe_path(attempt, candidate.get("video_path"), f"{cbase}.video_path", problems)
            review = candidate.get("review") or {}
            if review.get("decision") not in {"pass", "fail", "accepted_defect"}:
                _problem(problems, "candidate-review", f"{cbase}.review.decision",
                         "candidate review decision is required")
            if review.get("decision") == "accepted_defect" and not (
                    mode == "fast_track" and candidate.get("candidate_id") == "C10"):
                _problem(problems, "accepted-defect-authority", cbase,
                         "accepted_defect is allowed only for C10 in explicit fast-track mode")
            if not str(review.get("evidence") or "").strip():
                _problem(problems, "candidate-review", f"{cbase}.review.evidence",
                         "candidate review evidence is required")
            if c_index and (candidates[c_index - 1].get("review") or {}).get("decision") != "fail":
                _problem(problems, "retry-without-failure", cbase,
                         "a retry may exist only after the immediately prior candidate failed")
        if job.get("selected_candidate") not in ids:
            _problem(problems, "candidate-selection", f"{base}.selected_candidate", "selection is absent")
        elif job.get("selected_candidate") != ids[-1]:
            _problem(problems, "candidate-selection", f"{base}.selected_candidate",
                     "generation must stop at and select the final candidate")
        else:
            decision = (candidates[-1].get("review") or {}).get("decision")
            if decision not in {"pass", "accepted_defect"}:
                _problem(problems, "candidate-selection", base,
                         "selected candidate must pass or carry an authorized accepted defect")
    if found != expected:
        _problem(problems, "motion-coverage", "content.shots",
                 f"motion coverage differs: expected {sorted(expected)}, got {sorted(found)}")


def _validate_stage07(attempt: Path, content: dict, problems: list[dict]) -> None:
    timeline = content.get("timeline")
    if not isinstance(timeline, list) or not timeline:
        _problem(problems, "timeline", "content.timeline", "non-empty timeline required")
        return
    expected = [str(shot.get("shot_id")) for shot in _timeline_shots(attempt)]
    actual = [str(item.get("shot_id")) for item in timeline]
    if actual != expected:
        _problem(problems, "timeline-order", "content.timeline", f"expected shot order {expected}, got {actual}")
    motion = _stage_artifact(attempt, "06-motion").get("content") or {}
    selected_sources = {}
    for job in motion.get("shots") or []:
        selected_id = job.get("selected_candidate")
        selected = next((item for item in job.get("candidates") or []
                         if item.get("candidate_id") == selected_id), {})
        selected_sources[str(job.get("shot_id"))] = selected.get("video_path")
    total = 0.0
    for index, segment in enumerate(timeline):
        base = f"content.timeline[{index}]"
        _safe_path(attempt, segment.get("source_video"), f"{base}.source_video", problems)
        if segment.get("source_video") != selected_sources.get(str(segment.get("shot_id"))):
            _problem(problems, "motion-selection-drift", f"{base}.source_video",
                     "timeline source differs from the selected Stage 06 candidate")
        duration, rate = segment.get("edit_seconds"), segment.get("playback_rate")
        if not isinstance(duration, (int, float)) or duration <= 0:
            _problem(problems, "edit-time", f"{base}.edit_seconds", "positive duration required")
        else:
            total += float(duration)
        if not isinstance(rate, (int, float)) or rate <= 0:
            _problem(problems, "playback-rate", f"{base}.playback_rate", "positive rate required")
        _required_text(segment, ("editorial_reason",), base, problems)
    premise = _stage_artifact(attempt, "01-premise").get("content") or {}
    runtime = premise.get("runtime_contract") or {}
    if runtime.get("mode") == "fixed" and abs(total - float(runtime.get("target_seconds") or 0)) > 0.05:
        _problem(problems, "runtime-sum", "content.timeline", "edit total differs from fixed runtime")
    _safe_path(attempt, content.get("output_video"), "content.output_video", problems)


def _validate_stage08(attempt: Path, content: dict, problems: list[dict]) -> None:
    receipts = content.get("stage_receipts")
    if not isinstance(receipts, list):
        _problem(problems, "stage-receipts", "content.stage_receipts", "receipt list required")
        return
    by_stage = {str(item.get("stage_id")): item for item in receipts if isinstance(item, dict)}
    for stage_id in list(STAGE_BY_ID)[:-1]:
        if stage_id not in by_stage:
            _problem(problems, "stage-receipt", "content.stage_receipts", f"missing {stage_id}")
            continue
        path = _safe_path(attempt, by_stage[stage_id].get("path"),
                          f"content.stage_receipts.{stage_id}", problems)
        if path and path.is_file() and by_stage[stage_id].get("sha256") != file_sha256(path):
            _problem(problems, "stage-receipt-drift", f"content.stage_receipts.{stage_id}", "receipt hash changed")
    _safe_path(attempt, content.get("master_video"), "content.master_video", problems)
    dimensions = content.get("review_dimensions")
    if not isinstance(dimensions, list) or not dimensions:
        _problem(problems, "review-dimensions", "content.review_dimensions",
                 "at least one evidence-backed review dimension is required")
    else:
        for index, dimension in enumerate(dimensions):
            base = f"content.review_dimensions[{index}]"
            if not isinstance(dimension, dict):
                _problem(problems, "review-dimension", base, "review dimension must be an object")
                continue
            _required_text(dimension, ("dimension", "evidence"), base, problems)
            if dimension.get("decision") not in {"pass", "fail"}:
                _problem(problems, "review-dimension", f"{base}.decision", "decision must be pass or fail")
    defects = content.get("defects")
    if not isinstance(defects, list):
        _problem(problems, "defects", "content.defects", "defects must be a list")
    else:
        for index, defect in enumerate(defects):
            base = f"content.defects[{index}]"
            if not isinstance(defect, dict):
                _problem(problems, "defect", base, "defect must be an object")
                continue
            _required_text(defect, ("defect_id", "class", "evidence", "owner_stage",
                                    "disposition", "authority"), base, problems)
            if defect.get("disposition") not in {"fixed", "rejected", "accepted"}:
                _problem(problems, "defect-disposition", f"{base}.disposition",
                         "disposition must be fixed, rejected, or accepted")
    release = content.get("release_decision") or {}
    if not isinstance(release.get("release_eligible"), bool):
        _problem(problems, "release", "content.release_decision.release_eligible", "boolean required")
    if release.get("external_publish_authorized") is not False:
        receipt = _safe_path(attempt, release.get("human_release_receipt"),
                             "content.release_decision.human_release_receipt", problems)
        if not receipt:
            _problem(problems, "release-authority", "content.release_decision",
                     "external publishing requires a separate human release receipt")


def validate_artifact(attempt: Path, stage_id: str, artifact: dict,
                      *, mode: str = "normal") -> dict:
    if stage_id not in STAGE_BY_ID:
        raise ValueError(f"unknown stage: {stage_id}")
    problems: list[dict] = []
    warnings: list[dict] = []
    content = _validate_common(artifact, stage_id, problems)
    try:
        if stage_id == "01-premise":
            _validate_stage01(content, problems)
        elif stage_id == "02-sheet":
            _validate_stage02(attempt, content, problems, warnings, mode)
        elif stage_id == "03-scenario":
            _validate_stage03(content, problems)
        elif stage_id == "04-shot-design":
            _validate_stage04(attempt, content, problems)
        elif stage_id == "05-plate":
            _validate_stage05(attempt, content, problems, warnings, mode)
        elif stage_id == "05.5-motion-prompt":
            _validate_stage055(attempt, content, problems)
        elif stage_id == "06-motion":
            _validate_stage06(attempt, content, problems, mode)
        elif stage_id == "07-edit":
            _validate_stage07(attempt, content, problems)
        elif stage_id == "08-review":
            _validate_stage08(attempt, content, problems)
    except ValueError as error:
        _problem(problems, "upstream", stage_id, str(error))
    return {
        "schema_version": "llm-stage-integrity-report.v1",
        "pipeline_version": PIPELINE_VERSION,
        "stage_id": stage_id,
        "artifact_sha256": canonical_sha256(artifact),
        "problems": problems,
        "warnings": warnings,
        "form_ok": not problems,
    }


def validate_critique(stage_id: str, critique: dict, artifact_sha256: str) -> dict:
    problems: list[dict] = []
    if critique.get("schema_version") != CRITIQUE_SCHEMA:
        _problem(problems, "schema", "schema_version", f"must be {CRITIQUE_SCHEMA}")
    if critique.get("stage_id") != stage_id:
        _problem(problems, "stage", "stage_id", f"must be {stage_id}")
    if critique.get("artifact_sha256") != artifact_sha256:
        _problem(problems, "artifact-drift", "artifact_sha256", "critique binds a different artifact")
    _required_text(critique, ("reviewer", "reviewed_at", "summary"), "critique", problems)
    decision = critique.get("decision")
    if decision not in {"pass", "fail"}:
        _problem(problems, "decision", "decision", "must be pass or fail")
    expected = [item[0] for item in CRITIC_CRITERIA[stage_id]]
    criteria = critique.get("criteria")
    if not isinstance(criteria, list):
        _problem(problems, "criteria", "criteria", "criteria must be a list")
        criteria = []
    actual = [item.get("criterion_id") for item in criteria if isinstance(item, dict)]
    if actual != expected:
        _problem(problems, "criteria", "criteria", f"criterion order must be {expected}")
    statuses = []
    for index, item in enumerate(criteria):
        status = item.get("status") if isinstance(item, dict) else None
        statuses.append(status)
        if status not in {"pass", "fail"}:
            _problem(problems, "criterion-status", f"criteria[{index}].status", "must be pass or fail")
        if not str((item or {}).get("evidence") or "").strip():
            _problem(problems, "criterion-evidence", f"criteria[{index}].evidence", "concrete evidence required")
    if decision == "pass" and (not statuses or any(value != "pass" for value in statuses)):
        _problem(problems, "decision", "decision", "pass requires every criterion to pass")
    if decision == "fail" and not any(value == "fail" for value in statuses):
        _problem(problems, "decision", "decision", "fail requires at least one failed criterion")
    classes = critique.get("failure_classes") or []
    if not isinstance(classes, list):
        _problem(problems, "failure-class", "failure_classes", "failure_classes must be a list")
        classes = []
    if any(value not in {"quality", "safety", "authority", "contract"} for value in classes):
        _problem(problems, "failure-class", "failure_classes", "unsupported failure class")
    if decision == "fail" and not classes:
        _problem(problems, "failure-class", "failure_classes", "failed critiques require a failure class")
    if decision == "pass" and classes:
        _problem(problems, "failure-class", "failure_classes", "passed critiques cannot carry failure classes")
    accepted = critique.get("accepted_defects") or []
    if not isinstance(accepted, list) or any(not str(value or "").strip() for value in accepted):
        _problem(problems, "accepted-defects", "accepted_defects",
                 "accepted_defects must be a list of non-empty descriptions")
    if decision == "pass" and accepted:
        _problem(problems, "accepted-defects", "accepted_defects",
                 "a passed critique cannot carry accepted defects")
    return {"ok": not problems, "problems": problems, "decision": decision,
            "failed_criteria": [item.get("criterion_id") for item in criteria
                                if isinstance(item, dict) and item.get("status") == "fail"]}
