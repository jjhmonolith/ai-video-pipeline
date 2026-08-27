"""Read-only projection of one v3 attempt into a dashboard graph.

The production artifacts remain the authority.  This module never invents a
creative relationship from a filename: semantic edges come from receipt
bindings, entity ids, or exact media paths recorded in stage artifacts.  A
filesystem scan is used only to expose files that no artifact references.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .orchestrator import load_state
from .specs import STAGES


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".m4v"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
TEXT_EXTENSIONS = {".json", ".md", ".txt", ".csv", ".tsv", ".log"}
KNOWN_FILE_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS | AUDIO_EXTENSIONS | TEXT_EXTENSIONS

STAGE_TITLES = {
    "01-premise": "Premise",
    "02-sheet": "Reference Sheets",
    "03-scenario": "Scenario",
    "04-shot-design": "Shot Design",
    "05-plate": "References & Plates",
    "05.5-motion-prompt": "Motion Prompt",
    "06-motion": "Motion",
    "07-edit": "Edit",
    "08-review": "Review",
}


def _json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else {"value": value}


def _safe_relative(attempt: Path, value: str | Path) -> str | None:
    raw = Path(value)
    resolved = raw.resolve() if raw.is_absolute() else (attempt / raw).resolve()
    try:
        relative = resolved.relative_to(attempt.resolve())
    except ValueError:
        return None
    return relative.as_posix()


def _file_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    if suffix in AUDIO_EXTENSIONS:
        return "audio"
    if suffix in TEXT_EXTENSIONS:
        return "text"
    return "file"


def describe_file(attempt: Path, relative: str) -> dict:
    safe = _safe_relative(attempt, relative)
    if safe is None:
        return {"path": str(relative), "exists": False, "unsafe": True, "kind": "file"}
    path = attempt / safe
    result = {
        "path": safe,
        "name": path.name,
        "exists": path.is_file(),
        "kind": _file_kind(path),
        "mime": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
    }
    if path.is_file():
        result["bytes"] = path.stat().st_size
        result["modified_ns"] = path.stat().st_mtime_ns
    return result


def _walk(value: Any, prefix: str = "") -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield path, item
            yield from _walk(item, path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            path = f"{prefix}[{index}]"
            yield path, item
            yield from _walk(item, path)


def extract_prompts(value: Any) -> list[dict]:
    prompts: list[dict] = []
    seen: set[str] = set()
    for path, item in _walk(value):
        key = path.rsplit(".", 1)[-1].lower()
        if isinstance(item, str) and "prompt" in key and item.strip():
            digest = hashlib.sha256(item.encode("utf-8")).hexdigest()
            if digest not in seen:
                seen.add(digest)
                prompts.append({"label": path, "text": item, "sha256": digest})
    return prompts


def extract_paths(attempt: Path, value: Any) -> list[dict]:
    files: list[dict] = []
    seen: set[str] = set()
    for json_path, item in _walk(value):
        if not isinstance(item, str):
            continue
        candidate = Path(item)
        if candidate.suffix.lower() not in KNOWN_FILE_EXTENSIONS:
            continue
        relative = _safe_relative(attempt, item)
        if relative is None or relative in seen:
            continue
        seen.add(relative)
        record = describe_file(attempt, relative)
        record["binding"] = json_path
        files.append(record)
    return files


def extract_attempts(attempt: Path, value: Any) -> list[dict]:
    records: list[dict] = []
    if not isinstance(value, dict) or not isinstance(value.get("attempts"), list):
        return records
    selected = value.get("selected_attempt") or value.get("selected_candidate")
    for index, item in enumerate(value["attempts"], start=1):
        if not isinstance(item, dict):
            continue
        attempt_id = item.get("attempt") or item.get("candidate_id") or index
        candidate = item.get("candidate_path") or item.get("video_path")
        records.append({
            "id": str(attempt_id),
            "selected": str(attempt_id) == str(selected),
            "decision": item.get("decision") or (item.get("review") or {}).get("decision"),
            "variation_strategy": item.get("variation_strategy"),
            "prompt": item.get("prompt"),
            "candidate": describe_file(attempt, candidate) if isinstance(candidate, str) else None,
            "review": item.get("review"),
            "raw": item,
        })
    return records


@dataclass
class GraphBuilder:
    attempt: Path
    nodes: dict[str, dict] = field(default_factory=dict)
    edges: dict[str, dict] = field(default_factory=dict)
    handled_files: set[str] = field(default_factory=set)
    entity: dict[tuple[str, str], str] = field(default_factory=dict)
    media_owner: dict[str, str] = field(default_factory=dict)
    media_owner_priority: dict[str, int] = field(default_factory=dict)

    def node(
        self,
        node_id: str,
        *,
        stage_id: str,
        kind: str,
        title: str,
        subtitle: str = "",
        status: str = "available",
        detail: Any = None,
        attempts: list[dict] | None = None,
        files: list[dict] | None = None,
        prompts: list[dict] | None = None,
        entity_keys: Iterable[tuple[str, str]] = (),
    ) -> str:
        safe_id = node_id.replace(" ", "-")
        if safe_id in self.nodes:
            suffix = 2
            while f"{safe_id}:{suffix}" in self.nodes:
                suffix += 1
            safe_id = f"{safe_id}:{suffix}"
        detail_value = detail if detail is not None else {}
        linked_files = files if files is not None else extract_paths(self.attempt, detail_value)
        linked_prompts = prompts if prompts is not None else extract_prompts(detail_value)
        attempt_history = attempts if attempts is not None else extract_attempts(self.attempt, detail_value)
        owner_priority = {
            "image-candidate": 100,
            "video-candidate": 100,
            "master-video": 100,
            "reference-board": 80,
            "reference": 80,
            "start-plate": 80,
            "motion-job": 40,
            "sealed-artifact": 10,
            "stage-attempt": 10,
        }.get(kind, 0)

        def register_media_owner(path: str) -> None:
            if owner_priority >= self.media_owner_priority.get(path, -1):
                self.media_owner[path] = safe_id
                self.media_owner_priority[path] = owner_priority

        for record in linked_files:
            path = record.get("path")
            if isinstance(path, str) and not record.get("unsafe"):
                self.handled_files.add(path)
                if record.get("kind") in {"image", "video", "audio"}:
                    register_media_owner(path)
        for record in attempt_history:
            candidate = record.get("candidate") or {}
            path = candidate.get("path")
            if isinstance(path, str) and not candidate.get("unsafe"):
                self.handled_files.add(path)
                register_media_owner(path)
        self.nodes[safe_id] = {
            "id": safe_id,
            "stage_id": stage_id,
            "kind": kind,
            "title": title,
            "subtitle": subtitle,
            "status": status,
            "detail": detail_value,
            "prompts": linked_prompts,
            "files": linked_files,
            "attempts": attempt_history,
        }
        for key in entity_keys:
            self.entity[key] = safe_id
        return safe_id

    def edge(self, source: str | None, target: str | None, kind: str, label: str) -> None:
        if not source or not target or source == target:
            return
        edge_id = f"{source}|{target}|{kind}|{label}"
        self.edges[edge_id] = {
            "id": edge_id,
            "source": source,
            "target": target,
            "kind": kind,
            "label": label,
        }

    def lookup(self, *keys: tuple[str, str]) -> str | None:
        for key in keys:
            if key in self.entity:
                return self.entity[key]
        return None


def _stage_source(builder: GraphBuilder, stage_id: str, state: dict) -> tuple[str, dict | None]:
    stage_state = state["stages"].get(stage_id) or {}
    sealed_path = builder.attempt / stage_id / "output" / "stage-artifact.json"
    if sealed_path.is_file():
        artifact = _json(sealed_path)
        node_id = builder.node(
            f"{stage_id}:sealed-artifact",
            stage_id=stage_id,
            kind="sealed-artifact",
            title="Sealed stage artifact",
            subtitle="output/stage-artifact.json",
            status="passed",
            detail=artifact,
            files=[describe_file(builder.attempt, sealed_path.relative_to(builder.attempt).as_posix())],
        )
        builder.handled_files.add(sealed_path.relative_to(builder.attempt).as_posix())
        return node_id, artifact

    attempts = stage_state.get("attempts") or []
    if attempts:
        path_value = attempts[-1].get("artifact_path")
        if isinstance(path_value, str):
            artifact = _json(builder.attempt / path_value)
            return f"{stage_id}:attempt:A{int(attempts[-1].get('attempt') or len(attempts)):02d}", artifact
    active = state.get("active_work") or {}
    if active.get("stage_id") == stage_id:
        artifact_path = active.get("artifact_path")
        artifact = _json(builder.attempt / artifact_path) if isinstance(artifact_path, str) else None
        return f"{stage_id}:work:A{int(active.get('attempt_number') or 1):02d}", artifact
    return f"{stage_id}:state", None


def _base_stage_nodes(builder: GraphBuilder, state: dict) -> dict[str, tuple[str, dict | None]]:
    sources: dict[str, tuple[str, dict | None]] = {}
    receipt_nodes: dict[str, str] = {}

    for spec in STAGES:
        stage_id = spec["id"]
        stage_state = state["stages"].get(stage_id) or {}
        state_node = builder.node(
            f"{stage_id}:state",
            stage_id=stage_id,
            kind="stage-state",
            title=STAGE_TITLES[stage_id],
            subtitle=spec["question"],
            status=str(stage_state.get("status") or "pending"),
            detail={"stage": spec, "state": stage_state},
        )

        previous_attempt: str | None = None
        for record in stage_state.get("attempts") or []:
            number = int(record.get("attempt") or 1)
            artifact_path = record.get("artifact_path")
            artifact = _json(builder.attempt / artifact_path) if isinstance(artifact_path, str) else None
            linked_files = []
            if isinstance(artifact_path, str):
                linked_files.append(describe_file(builder.attempt, artifact_path))
                builder.handled_files.add(artifact_path)
            critic = record.get("critic") or {}
            if record.get("form_ok") is False or critic.get("decision") == "fail":
                attempt_status = "failed"
            elif critic.get("decision") == "pass":
                attempt_status = "passed"
            else:
                attempt_status = "running"
            attempt_node = builder.node(
                f"{stage_id}:attempt:A{number:02d}",
                stage_id=stage_id,
                kind="stage-attempt",
                title=f"Stage attempt A{number:02d}",
                subtitle=str(record.get("variation_strategy") or ""),
                status=attempt_status,
                detail={"record": record, "artifact": artifact},
                files=linked_files + extract_paths(builder.attempt, artifact or {}),
                prompts=extract_prompts(artifact or {}),
            )
            builder.edge(state_node, attempt_node, "attempt", f"A{number:02d}")

            validation_path = record.get("validation_path")
            validation_node: str | None = None
            if isinstance(validation_path, str):
                validation = _json(builder.attempt / validation_path)
                validation_node = builder.node(
                    f"{stage_id}:integrity:A{number:02d}", stage_id=stage_id,
                    kind="integrity-report", title=f"Integrity A{number:02d}",
                    subtitle="form pass" if (validation or {}).get("form_ok") else "form failure",
                    status="passed" if (validation or {}).get("form_ok") else "failed",
                    detail=validation,
                    files=[describe_file(builder.attempt, validation_path)],
                )
                builder.handled_files.add(validation_path)
                builder.edge(attempt_node, validation_node, "validation", "deterministic integrity")

            critic_path = critic.get("path")
            if isinstance(critic_path, str):
                critique = _json(builder.attempt / critic_path)
                critic_node = builder.node(
                    f"{stage_id}:critic:A{number:02d}", stage_id=stage_id,
                    kind="critic-review", title=f"Critic A{number:02d}",
                    subtitle=str((critique or {}).get("summary") or "fresh-context review"),
                    status=str((critique or {}).get("decision") or critic.get("decision") or "available"),
                    detail=critique,
                    files=[describe_file(builder.attempt, critic_path)],
                )
                builder.handled_files.add(critic_path)
                builder.edge(validation_node or attempt_node, critic_node, "review", "fresh-context critic")
            if previous_attempt:
                builder.edge(previous_attempt, attempt_node, "retry", "retry after failure")
            previous_attempt = attempt_node

        active = state.get("active_work") or {}
        if active.get("stage_id") == stage_id:
            number = int(active.get("attempt_number") or 1)
            work_path = active.get("artifact_path")
            work_node = builder.node(
                f"{stage_id}:work:A{number:02d}",
                stage_id=stage_id,
                kind="active-work",
                title=f"Active work A{number:02d}",
                subtitle=str(active.get("variation_strategy") or "author required"),
                status="running",
                detail=active,
                files=extract_paths(builder.attempt, active),
            )
            builder.edge(previous_attempt or state_node, work_node, "work-order", "active work order")

        source_node, artifact = _stage_source(builder, stage_id, state)
        sources[stage_id] = (source_node, artifact)
        if source_node != state_node:
            builder.edge(previous_attempt or state_node, source_node, "promotion", "selected stage output")

        receipt_path = builder.attempt / stage_id / "receipt.json"
        if receipt_path.is_file():
            receipt = _json(receipt_path)
            receipt_node = builder.node(
                f"{stage_id}:receipt",
                stage_id=stage_id,
                kind="receipt",
                title="Stage receipt",
                subtitle=str((receipt or {}).get("resolution") or "receipt.json"),
                status="passed",
                detail=receipt,
                files=[describe_file(builder.attempt, receipt_path.relative_to(builder.attempt).as_posix())],
            )
            builder.handled_files.add(receipt_path.relative_to(builder.attempt).as_posix())
            builder.edge(source_node, receipt_node, "receipt", "sealed evidence")
            receipt_nodes[stage_id] = receipt_node

    for node in list(builder.nodes.values()):
        if node["kind"] == "stage-attempt":
            receipt_inputs = ((node.get("detail") or {}).get("artifact") or {}).get("input_receipts") or []
        elif node["kind"] in {"sealed-artifact", "active-work"}:
            receipt_inputs = (node.get("detail") or {}).get("input_receipts") or []
        else:
            continue
        for item in receipt_inputs or []:
            if not isinstance(item, dict):
                continue
            upstream = receipt_nodes.get(str(item.get("stage_id")))
            builder.edge(upstream, node["id"], "input-receipt", "direct stage input")
    return sources


def _project_stage01(builder: GraphBuilder, source: str, artifact: dict) -> None:
    content = artifact.get("content") or {}
    contract = builder.node(
        "01-premise:production-contract",
        stage_id="01-premise", kind="production-contract", title="Production contract",
        subtitle=str(((content.get("direction") or {}).get("interpretation") or "creative contract")),
        status="passed", detail=content,
    )
    builder.edge(source, contract, "output", "creative production contract")
    for key, title in (
        ("runtime_contract", "Runtime contract"),
        ("frame", "Generation frame"),
        ("delivery_frame", "Delivery frame"),
    ):
        if isinstance(content.get(key), dict):
            node = builder.node(
                f"01-premise:{key}", stage_id="01-premise", kind=key,
                title=title, subtitle=json.dumps(content[key], ensure_ascii=False),
                detail=content[key],
            )
            builder.edge(contract, node, "definition", key)
    for item in content.get("subjects") or []:
        if not isinstance(item, dict):
            continue
        subject_id = str(item.get("subject_id") or "subject")
        node = builder.node(
            f"01-premise:subject:{subject_id}", stage_id="01-premise", kind="subject",
            title=subject_id, subtitle=f"{item.get('kind', 'subject')} · {item.get('purpose', '')}",
            detail=item, entity_keys=(("subject", subject_id),),
        )
        builder.edge(contract, node, "definition", "subject definition")


def _project_stage02(builder: GraphBuilder, source: str, artifact: dict) -> None:
    content = artifact.get("content") or {}
    for board in content.get("boards") or []:
        if not isinstance(board, dict):
            continue
        board_id = str(board.get("board_id") or board.get("subject_id") or "board")
        subject_id = str(board.get("subject_id") or "")
        node = builder.node(
            f"02-sheet:board:{board_id}", stage_id="02-sheet", kind="reference-board",
            title=board_id, subtitle=f"subject {subject_id} · selected {board.get('selected_attempt', '—')}",
            status="selected" if board.get("selected_image") else "available", detail=board,
            entity_keys=(("board", board_id), ("board-subject", subject_id)),
        )
        builder.edge(source, node, "output", "reference board")
        builder.edge(builder.lookup(("subject", subject_id)), node, "input", "subject definition")
        meta = board.get("structured_meta_prompt") or {}
        for panel in meta.get("panel_plan") or []:
            if not isinstance(panel, dict):
                continue
            panel_id = str(panel.get("panel_id") or "panel")
            panel_node = builder.node(
                f"02-sheet:panel:{board_id}:{panel_id}", stage_id="02-sheet", kind="board-panel",
                title=panel_id, subtitle=str(panel.get("purpose") or "panel"), detail=panel,
            )
            builder.edge(node, panel_node, "contains", "panel plan")
        for item in board.get("attempts") or []:
            if not isinstance(item, dict):
                continue
            number = item.get("attempt") or 1
            candidate = builder.node(
                f"02-sheet:board:{board_id}:A{int(number):02d}", stage_id="02-sheet",
                kind="image-candidate", title=f"{board_id} · A{int(number):02d}",
                subtitle=str(item.get("variation_strategy") or ""),
                status="selected" if number == board.get("selected_attempt") else str(item.get("decision") or "available"),
                detail=item,
            )
            builder.edge(node, candidate, "candidate", "image attempt")
    review = content.get("cross_board_review")
    if isinstance(review, dict):
        review_node = builder.node(
            "02-sheet:cross-board-review", stage_id="02-sheet", kind="cross-board-review",
            title="Cross-board review", subtitle=str(review.get("decision") or ""),
            status=str(review.get("decision") or "available"), detail=review,
        )
        for key, node_id in builder.entity.items():
            if key[0] == "board":
                builder.edge(node_id, review_node, "review", "cross-board consistency")


def _project_stage03(builder: GraphBuilder, source: str, artifact: dict) -> None:
    content = artifact.get("content") or {}
    for sequence in content.get("sequences") or []:
        if not isinstance(sequence, dict):
            continue
        sequence_id = str(sequence.get("sequence_id") or "sequence")
        sequence_node = builder.node(
            f"03-scenario:sequence:{sequence_id}", stage_id="03-scenario", kind="sequence",
            title=sequence_id, subtitle=str(sequence.get("intent") or ""), detail=sequence,
            entity_keys=(("sequence", sequence_id),),
        )
        builder.edge(source, sequence_node, "output", "sequence")
        for scene in sequence.get("scenes") or []:
            if not isinstance(scene, dict):
                continue
            scene_id = str(scene.get("scene_id") or "scene")
            scene_node = builder.node(
                f"03-scenario:scene:{scene_id}", stage_id="03-scenario", kind="scene",
                title=scene_id, subtitle=str(scene.get("slugline") or scene.get("intent") or ""),
                detail=scene, entity_keys=(("scene", scene_id),),
            )
            builder.edge(sequence_node, scene_node, "contains", "scene")
            for event in scene.get("events") or []:
                if not isinstance(event, dict):
                    continue
                event_id = str(event.get("event_id") or "event")
                event_node = builder.node(
                    f"03-scenario:event:{event_id}", stage_id="03-scenario", kind="event",
                    title=event_id, subtitle=str(event.get("action") or ""), detail=event,
                    entity_keys=(("event", event_id),),
                )
                builder.edge(scene_node, event_node, "contains", "dramatic event")
                for key in ("actor_subject_id", "target_subject_id"):
                    subject_id = event.get(key)
                    if isinstance(subject_id, str):
                        builder.edge(builder.lookup(("subject", subject_id)), event_node, "input", key)
            for requirement in scene.get("production_requirements") or []:
                if not isinstance(requirement, dict):
                    continue
                requirement_id = str(requirement.get("requirement_id") or "requirement")
                requirement_node = builder.node(
                    f"03-scenario:requirement:{requirement_id}", stage_id="03-scenario",
                    kind="reference-debt", title=requirement_id,
                    subtitle=str(requirement.get("name") or requirement.get("description") or ""),
                    status="required", detail=requirement,
                    entity_keys=(("requirement", requirement_id),),
                )
                builder.edge(scene_node, requirement_node, "requires", "new reference debt")


def _project_stage04(builder: GraphBuilder, source: str, artifact: dict) -> None:
    content = artifact.get("content") or {}
    for plan in content.get("scene_plans") or []:
        if not isinstance(plan, dict):
            continue
        scene_id = str(plan.get("scene_id") or "scene")
        plan_node = builder.node(
            f"04-shot-design:scene-plan:{scene_id}", stage_id="04-shot-design", kind="scene-plan",
            title=f"{scene_id} treatment", subtitle=str((plan.get("treatment") or {}).get("intent") or ""),
            detail=plan, entity_keys=(("scene-plan", scene_id),),
        )
        builder.edge(source, plan_node, "output", "scene treatment")
        builder.edge(builder.lookup(("scene", scene_id)), plan_node, "input", "scenario scene")
        for setup in plan.get("setups") or []:
            if not isinstance(setup, dict):
                continue
            setup_id = str(setup.get("setup_id") or "setup")
            setup_node = builder.node(
                f"04-shot-design:setup:{setup_id}", stage_id="04-shot-design", kind="setup",
                title=setup_id, subtitle=str(setup.get("camera_position") or ""), detail=setup,
                entity_keys=(("setup", setup_id),),
            )
            builder.edge(plan_node, setup_node, "contains", "camera setup")
            for shot in setup.get("shots") or []:
                if not isinstance(shot, dict):
                    continue
                shot_id = str(shot.get("shot_id") or "shot")
                timing = shot.get("timing") or {}
                shot_node = builder.node(
                    f"04-shot-design:shot:{shot_id}", stage_id="04-shot-design", kind="shot",
                    title=shot_id,
                    subtitle=f"{shot.get('composition', '')} · {timing.get('edit_target_seconds', '—')}s",
                    detail=shot, entity_keys=(("shot", shot_id),),
                )
                builder.edge(setup_node, shot_node, "contains", "shot")
                for event_id in shot.get("event_ids") or []:
                    builder.edge(builder.lookup(("event", str(event_id))), shot_node, "input", "event binding")
                for subject_id in shot.get("required_reference_subject_ids") or []:
                    upstream = builder.lookup(("subject", str(subject_id)), ("requirement", str(subject_id)))
                    builder.edge(upstream, shot_node, "input", "required reference")


def _project_stage05(builder: GraphBuilder, source: str, artifact: dict) -> None:
    content = artifact.get("content") or {}
    reference_nodes: list[str] = []
    for reference in content.get("references") or []:
        if not isinstance(reference, dict):
            continue
        reference_id = str(reference.get("reference_id") or "reference")
        bound_id = str(reference.get("subject_or_requirement_id") or "")
        reference_node = builder.node(
            f"05-plate:reference:{reference_id}", stage_id="05-plate", kind="reference",
            title=reference_id, subtitle=f"{reference.get('origin', '')} · {bound_id}",
            status=str((reference.get("review") or {}).get("decision") or "available"),
            detail=reference, entity_keys=(("reference", reference_id), ("reference-bound", bound_id)),
        )
        reference_nodes.append(reference_node)
        builder.edge(source, reference_node, "output", "reviewed reference")
        builder.edge(
            builder.lookup(("subject", bound_id), ("requirement", bound_id), ("board-subject", bound_id)),
            reference_node, "input", "identity or reference debt",
        )
        for item in reference.get("attempts") or []:
            if not isinstance(item, dict):
                continue
            number = int(item.get("attempt") or 1)
            candidate = builder.node(
                f"05-plate:reference:{reference_id}:A{number:02d}", stage_id="05-plate",
                kind="image-candidate", title=f"{reference_id} · A{number:02d}",
                subtitle=str(item.get("variation_strategy") or ""),
                status="selected" if number == reference.get("selected_attempt") else str(item.get("decision") or "available"),
                detail=item,
            )
            builder.edge(reference_node, candidate, "candidate", "reference image attempt")

    preflight = content.get("global_reference_preflight")
    if isinstance(preflight, dict):
        preflight_node = builder.node(
            "05-plate:reference-preflight", stage_id="05-plate", kind="reference-preflight",
            title="Global reference preflight", subtitle=str(preflight.get("decision") or ""),
            status=str(preflight.get("decision") or "available"), detail=preflight,
        )
        for reference_node in reference_nodes:
            builder.edge(reference_node, preflight_node, "review", "reference barrier")

    for plate in content.get("plates") or []:
        if not isinstance(plate, dict):
            continue
        shot_id = str(plate.get("shot_id") or "shot")
        plate_node = builder.node(
            f"05-plate:plate:{shot_id}", stage_id="05-plate", kind="start-plate",
            title=f"{shot_id} start plate", subtitle=f"selected A{plate.get('selected_attempt', '—')}",
            status="selected" if plate.get("selected_image") else "available", detail=plate,
            entity_keys=(("plate", shot_id),),
        )
        builder.edge(source, plate_node, "output", "approved start plate")
        builder.edge(builder.lookup(("shot", shot_id)), plate_node, "input", "shot contract")
        for reference_id in plate.get("reference_ids") or []:
            builder.edge(builder.lookup(("reference", str(reference_id))), plate_node, "input", "bound reference")
        for item in plate.get("attempts") or []:
            if not isinstance(item, dict):
                continue
            number = int(item.get("attempt") or 1)
            candidate = builder.node(
                f"05-plate:plate:{shot_id}:A{number:02d}", stage_id="05-plate",
                kind="image-candidate", title=f"{shot_id} plate · A{number:02d}",
                subtitle=str(item.get("variation_strategy") or ""),
                status="selected" if number == plate.get("selected_attempt") else str(item.get("decision") or "available"),
                detail=item,
            )
            builder.edge(plate_node, candidate, "candidate", "plate image attempt")


def _project_stage055(builder: GraphBuilder, source: str, artifact: dict) -> None:
    for shot in (artifact.get("content") or {}).get("shots") or []:
        if not isinstance(shot, dict):
            continue
        shot_id = str(shot.get("shot_id") or "shot")
        prompt_node = builder.node(
            f"05.5-motion-prompt:shot:{shot_id}", stage_id="05.5-motion-prompt",
            kind="motion-prompt", title=f"{shot_id} final C01 prompt",
            subtitle=str(shot.get("realization_status") or ""), status="passed", detail=shot,
            entity_keys=(("motion-prompt", shot_id),),
        )
        builder.edge(source, prompt_node, "output", "plate-grounded prompt")
        builder.edge(builder.lookup(("shot", shot_id)), prompt_node, "input", "shot intent")
        builder.edge(builder.lookup(("plate", shot_id)), prompt_node, "input", "approved start plate")
        for binding in shot.get("reference_bindings") or []:
            if isinstance(binding, dict):
                builder.edge(builder.lookup(("reference", str(binding.get("reference_id")))), prompt_node,
                             "input", "reference binding")


def _project_stage06(builder: GraphBuilder, source: str, artifact: dict) -> None:
    content = artifact.get("content") or {}
    job_nodes: list[str] = []
    for job in content.get("shots") or []:
        if not isinstance(job, dict):
            continue
        shot_id = str(job.get("shot_id") or "shot")
        job_node = builder.node(
            f"06-motion:shot:{shot_id}", stage_id="06-motion", kind="motion-job",
            title=f"{shot_id} motion", subtitle=f"selected {job.get('selected_candidate', '—')}",
            status="selected" if job.get("selected_candidate") else "available", detail=job,
            entity_keys=(("motion-job", shot_id),),
        )
        job_nodes.append(job_node)
        builder.edge(source, job_node, "output", "motion job")
        builder.edge(builder.lookup(("motion-prompt", shot_id)), job_node, "input", "final motion prompt")
        builder.edge(builder.lookup(("plate", shot_id)), job_node, "input", "start plate")
        for candidate in job.get("candidates") or []:
            if not isinstance(candidate, dict):
                continue
            candidate_id = str(candidate.get("candidate_id") or "candidate")
            video_node = builder.node(
                f"06-motion:shot:{shot_id}:{candidate_id}", stage_id="06-motion", kind="video-candidate",
                title=f"{shot_id} · {candidate_id}", subtitle=str(candidate.get("variation_strategy") or ""),
                status="selected" if candidate_id == str(job.get("selected_candidate"))
                else str((candidate.get("review") or {}).get("decision") or "available"),
                detail=candidate, entity_keys=(("video-candidate", f"{shot_id}:{candidate_id}"),),
            )
            builder.edge(job_node, video_node, "candidate", "motion take")
    review = content.get("cross_shot_review")
    if isinstance(review, dict):
        review_node = builder.node(
            "06-motion:cross-shot-review", stage_id="06-motion", kind="cross-shot-review",
            title="Cross-shot review", subtitle=str(review.get("decision") or ""),
            status=str(review.get("decision") or "available"), detail=review,
        )
        for job_node in job_nodes:
            builder.edge(job_node, review_node, "review", "cross-shot consistency")


def _project_stage07(builder: GraphBuilder, source: str, artifact: dict) -> None:
    content = artifact.get("content") or {}
    segments: list[str] = []
    for index, segment in enumerate(content.get("timeline") or [], start=1):
        if not isinstance(segment, dict):
            continue
        shot_id = str(segment.get("shot_id") or f"segment-{index}")
        segment_node = builder.node(
            f"07-edit:segment:{index:03d}:{shot_id}", stage_id="07-edit", kind="edit-segment",
            title=f"{index:02d} · {shot_id}", subtitle=f"{segment.get('edit_seconds', '—')}s",
            detail=segment, entity_keys=(("edit-segment", f"{index}:{shot_id}"),),
        )
        segments.append(segment_node)
        builder.edge(source, segment_node, "output", "timeline segment")
        builder.edge(builder.lookup(("shot", shot_id)), segment_node, "input", "shot timing")
        source_video = segment.get("source_video")
        if isinstance(source_video, str):
            relative = _safe_relative(builder.attempt, source_video)
            builder.edge(builder.media_owner.get(relative or ""), segment_node, "input", "selected motion take")
    output_video = content.get("output_video")
    if isinstance(output_video, str):
        master = builder.node(
            "07-edit:master", stage_id="07-edit", kind="master-video",
            title="Editorial master", subtitle=Path(output_video).name,
            status=str((content.get("master_review") or {}).get("decision") or "available"),
            detail={"output_video": output_video, "master_review": content.get("master_review")},
            entity_keys=(("master", "current"),),
        )
        for segment_node in segments:
            builder.edge(segment_node, master, "assembly", "edited into master")


def _project_stage08(builder: GraphBuilder, source: str, artifact: dict) -> None:
    content = artifact.get("content") or {}
    review_node = builder.node(
        "08-review:final-review", stage_id="08-review", kind="final-review",
        title="Evidence-backed review", subtitle="master + upstream receipts",
        status="passed" if not content.get("defects") else "warning", detail=content,
        entity_keys=(("review", "final"),),
    )
    builder.edge(source, review_node, "output", "final review")
    master_path = content.get("master_video")
    if isinstance(master_path, str):
        relative = _safe_relative(builder.attempt, master_path)
        builder.edge(builder.media_owner.get(relative or "") or builder.lookup(("master", "current")),
                     review_node, "input", "master video")
    for receipt in content.get("stage_receipts") or []:
        if isinstance(receipt, dict):
            builder.edge(f"{receipt.get('stage_id')}:receipt", review_node, "input", "upstream receipt")
    for index, dimension in enumerate(content.get("review_dimensions") or [], start=1):
        if not isinstance(dimension, dict):
            continue
        node = builder.node(
            f"08-review:dimension:{index:02d}", stage_id="08-review", kind="review-dimension",
            title=str(dimension.get("dimension") or f"dimension {index}"),
            subtitle=str(dimension.get("decision") or ""),
            status=str(dimension.get("decision") or "available"), detail=dimension,
        )
        builder.edge(review_node, node, "contains", "review dimension")
    for index, defect in enumerate(content.get("defects") or [], start=1):
        detail = defect if isinstance(defect, dict) else {"defect": defect}
        node = builder.node(
            f"08-review:defect:{index:02d}", stage_id="08-review", kind="defect",
            title=f"Defect {index:02d}", subtitle=str(detail.get("description") or detail.get("defect") or ""),
            status="failed", detail=detail,
        )
        builder.edge(review_node, node, "finding", "remaining defect")
    release = content.get("release_decision")
    if isinstance(release, dict):
        release_node = builder.node(
            "08-review:release-decision", stage_id="08-review", kind="release-decision",
            title="Internal release eligibility",
            subtitle="eligible" if release.get("release_eligible") else "not eligible",
            status="passed" if release.get("release_eligible") else "blocked", detail=release,
        )
        builder.edge(review_node, release_node, "decision", "release boundary")


PROJECTORS = {
    "01-premise": _project_stage01,
    "02-sheet": _project_stage02,
    "03-scenario": _project_stage03,
    "04-shot-design": _project_stage04,
    "05-plate": _project_stage05,
    "05.5-motion-prompt": _project_stage055,
    "06-motion": _project_stage06,
    "07-edit": _project_stage07,
    "08-review": _project_stage08,
}


def _unreferenced_files(builder: GraphBuilder) -> None:
    skip_names = {".DS_Store"}
    for spec in STAGES:
        stage_id = spec["id"]
        directory = builder.attempt / stage_id
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.name in skip_names or any(part.startswith(".") for part in path.relative_to(directory).parts):
                continue
            relative = path.relative_to(builder.attempt).as_posix()
            if relative in builder.handled_files:
                continue
            record = describe_file(builder.attempt, relative)
            file_node = builder.node(
                f"{stage_id}:unreferenced:{relative}", stage_id=stage_id, kind="unreferenced-file",
                title=path.name, subtitle=relative, status="warning",
                detail={"reason": "file exists but no current artifact path binding references it", "file": record},
                files=[record],
            )
            builder.edge(f"{stage_id}:state", file_node, "unresolved", "unreferenced stage file")


def build_snapshot(attempt: Path) -> dict:
    """Return a JSON-serializable, read-only graph snapshot for one v3 attempt."""
    attempt = attempt.resolve()
    state = load_state(attempt)
    builder = GraphBuilder(attempt)
    state_relative = attempt / "pipeline-state.json"
    builder.handled_files.add(state_relative.relative_to(attempt).as_posix())
    sources = _base_stage_nodes(builder, state)

    for spec in STAGES:
        stage_id = spec["id"]
        source, artifact = sources[stage_id]
        if artifact:
            PROJECTORS[stage_id](builder, source, artifact)

    # Exact media-path bindings are resolved after all semantic projectors have
    # registered their owners.  This catches Stage 07/08 inputs without guessing
    # from a candidate filename.
    for node in list(builder.nodes.values()):
        for record in node.get("files") or []:
            path = record.get("path")
            if not isinstance(path, str):
                continue
            owner = builder.media_owner.get(path)
            if owner and owner != node["id"] and record.get("binding"):
                builder.edge(owner, node["id"], "media-input", str(record["binding"]))

    _unreferenced_files(builder)

    node_ids = set(builder.nodes)
    edges = [edge for edge in builder.edges.values()
             if edge["source"] in node_ids and edge["target"] in node_ids]
    stages = []
    for index, spec in enumerate(STAGES):
        stage_id = spec["id"]
        stage_state = state["stages"].get(stage_id) or {}
        stages.append({
            "id": stage_id,
            "title": STAGE_TITLES[stage_id],
            "question": spec["question"],
            "order": index,
            "status": stage_state.get("status") or "pending",
            "attempt_count": len(stage_state.get("attempts") or []),
            "node_count": sum(1 for node in builder.nodes.values() if node["stage_id"] == stage_id),
        })

    snapshot = {
        "schema_version": "v3-dashboard-snapshot.v1",
        "attempt": {
            "id": state.get("attempt_id"),
            "path": str(attempt),
            "pipeline_version": state.get("pipeline_version"),
            "status": state.get("status"),
            "current_stage": state.get("current_stage"),
            "mode": (state.get("mode") or {}).get("name"),
            "created_at": state.get("created_at"),
            "updated_at": state.get("updated_at"),
            "direction": state.get("direction"),
        },
        "stages": stages,
        "nodes": list(builder.nodes.values()),
        "edges": edges,
        "stats": {
            "nodes": len(builder.nodes),
            "edges": len(edges),
            "media": len({
                str(file.get("path"))
                for node in builder.nodes.values()
                for file in node.get("files") or []
                if file.get("kind") in {"image", "video", "audio"} and file.get("path")
            }),
            "prompts": sum(len(node.get("prompts") or []) for node in builder.nodes.values()),
            "unreferenced_files": sum(1 for node in builder.nodes.values()
                                      if node.get("kind") == "unreferenced-file"),
        },
    }
    encoded = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    snapshot["etag"] = hashlib.sha256(encoded).hexdigest()
    return snapshot
