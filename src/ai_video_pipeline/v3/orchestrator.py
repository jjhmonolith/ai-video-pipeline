"""Persistent stage orchestration without creative generation logic."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .integrity import (
    canonical_sha256,
    file_sha256,
    load_json,
    stage02_authoring_inputs,
    validate_artifact,
    validate_critique,
)
from .specs import (
    CRITIC_CRITERIA,
    DEFAULT_NORMAL_HUMAN_GATES,
    MAX_ATTEMPTS,
    PIPELINE_VERSION,
    RECEIPT_SCHEMA,
    STAGES,
    STAGE_BY_ID,
    STAGE_INDEX,
    STATE_SCHEMA,
    VARIATION_STRATEGIES,
)


class OrchestratorError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def state_path(attempt: Path) -> Path:
    return attempt.resolve() / "pipeline-state.json"


def load_state(attempt: Path) -> dict:
    path = state_path(attempt)
    state = load_json(path, "pipeline state")
    if state.get("schema_version") != STATE_SCHEMA or state.get("pipeline_version") != PIPELINE_VERSION:
        raise OrchestratorError("unsupported pipeline state")
    if Path(str(state.get("attempt") or "")).resolve() != attempt.resolve():
        raise OrchestratorError("pipeline state is bound to another attempt")
    return state


def _write_state(attempt: Path, state: dict) -> None:
    path = state_path(attempt)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def initialize(attempt: Path, direction: str, *, mode: str = "normal",
               by: str = "user", reason: str = "new production") -> dict:
    attempt = attempt.resolve()
    if state_path(attempt).exists():
        raise OrchestratorError(f"pipeline already initialized: {state_path(attempt)}")
    if mode not in {"normal", "fast_track"}:
        raise OrchestratorError("mode must be normal or fast_track")
    if not direction.strip():
        raise OrchestratorError("verbatim user direction is required")
    if mode == "fast_track" and (not by.strip() or not reason.strip()):
        raise OrchestratorError("fast_track requires explicit user attribution and reason")
    attempt.mkdir(parents=True, exist_ok=True)
    stages = {item["id"]: {
        "status": "pending", "attempts": [], "artifact": None,
        "receipt": None, "last_feedback": [], "accepted_defects": [],
    } for item in STAGES}
    state = {
        "schema_version": STATE_SCHEMA,
        "pipeline_version": PIPELINE_VERSION,
        "attempt": str(attempt),
        "attempt_id": attempt.name,
        "created_at": _now(),
        "updated_at": _now(),
        "direction": {"verbatim": direction, "given_by": by},
        "mode": {
            "name": mode, "set_by": by, "reason": reason, "set_at": _now(),
            "external_side_effects_authorized": False,
        },
        "normal_human_gates": list(DEFAULT_NORMAL_HUMAN_GATES),
        "current_stage": STAGES[0]["id"],
        "status": "running",
        "active_work": None,
        "stages": stages,
        "events": [{"at": _now(), "event": "pipeline_initialized", "mode": mode}],
    }
    _write_state(attempt, state)
    return state


def _input_receipts(attempt: Path, stage_id: str) -> list[dict]:
    index = STAGE_INDEX[stage_id]
    out = []
    for item in STAGES[:index]:
        path = attempt / item["id"] / "receipt.json"
        if not path.is_file():
            raise OrchestratorError(f"upstream receipt missing: {path}")
        out.append({"stage_id": item["id"], "path": str(path.relative_to(attempt)),
                    "sha256": file_sha256(path)})
    return out


def work_order(attempt: Path) -> dict:
    attempt = attempt.resolve()
    state = load_state(attempt)
    if state.get("status") == "complete":
        return {"status": "complete", "attempt": str(attempt)}
    if state.get("active_work"):
        return state["active_work"]
    stage_id = state.get("current_stage")
    stage = state["stages"][stage_id]
    if stage["status"] in {"human_gate", "blocked", "awaiting_critic"}:
        return {"status": stage["status"], "stage_id": stage_id,
                "last_feedback": stage.get("last_feedback") or []}
    number = len(stage["attempts"]) + 1
    if number > MAX_ATTEMPTS:
        stage["status"] = "blocked"
        state["status"] = "blocked"
        _write_state(attempt, state)
        return {"status": "blocked", "stage_id": stage_id, "reason": "attempt limit exhausted"}
    work_dir = attempt / stage_id / "qa" / "attempts" / f"A{number:02d}"
    work_dir.mkdir(parents=True, exist_ok=True)
    order = {
        "schema_version": "llm-stage-work-order.v1",
        "status": "author_required",
        "pipeline_version": PIPELINE_VERSION,
        "attempt": str(attempt),
        "attempt_id": state["attempt_id"],
        "stage_id": stage_id,
        "stage_skill": STAGE_BY_ID[stage_id]["skill"],
        "stage_skill_path": str((Path(".agents/skills") / STAGE_BY_ID[stage_id]["skill"] / "SKILL.md")),
        "question": STAGE_BY_ID[stage_id]["question"],
        "attempt_number": number,
        "variation_strategy": VARIATION_STRATEGIES[number - 1],
        "direction": state["direction"],
        "mode": state["mode"],
        "input_receipts": _input_receipts(attempt, stage_id),
        "failed_criteria": stage.get("last_feedback") or [],
        "artifact_path": str((work_dir / "artifact.json").relative_to(attempt)),
        "validation_path": str((work_dir / "integrity.json").relative_to(attempt)),
        "critique_path": str((work_dir / "critique.json").relative_to(attempt)),
        "author_contract": {
            "schema_version": "llm-stage-artifact.v1",
            "pipeline_version": PIPELINE_VERSION,
            "stage_id": stage_id,
            "attempt_id": state["attempt_id"],
            "input_receipts": _input_receipts(attempt, stage_id),
            "creative_decisions": "array of explicit choices and reasons",
            "content": "stage-owned object defined by the selected stage skill",
        },
        "critic_criteria": [
            {"criterion_id": key, "description": description}
            for key, description in CRITIC_CRITERIA[stage_id]
        ],
    }
    if stage_id == "02-sheet":
        order["stage_inputs"] = stage02_authoring_inputs(attempt)
    state["active_work"] = order
    stage["status"] = "running"
    state["updated_at"] = _now()
    state["events"].append({"at": _now(), "event": "work_order_created",
                            "stage_id": stage_id, "attempt_number": number})
    _write_state(attempt, state)
    return order


def _input_receipt_problems(expected: list[dict], actual: Any) -> list[dict]:
    if actual != expected:
        return [{"code": "input-receipt-drift", "path": "input_receipts",
                 "message": "artifact input receipts differ from the work order"}]
    return []


def _work_order_binding_problems(state: dict, order: dict, artifact: dict) -> list[dict]:
    problems = []
    if artifact.get("attempt_id") != order.get("attempt_id"):
        problems.append({"code": "attempt-binding", "path": "attempt_id",
                         "message": "artifact attempt_id differs from the work order"})
    if order.get("stage_id") == "01-premise":
        direction = ((artifact.get("content") or {}).get("direction") or {}).get("verbatim")
        if direction != state["direction"]["verbatim"]:
            problems.append({"code": "direction-drift", "path": "content.direction.verbatim",
                             "message": "Stage 01 must preserve the initialized direction verbatim"})
    return problems


def submit(attempt: Path) -> dict:
    attempt = attempt.resolve()
    state = load_state(attempt)
    order = state.get("active_work")
    if not order or order.get("status") != "author_required":
        raise OrchestratorError("no active author work order")
    stage_id = order["stage_id"]
    artifact_path = attempt / order["artifact_path"]
    artifact = load_json(artifact_path, "stage artifact")
    report = validate_artifact(attempt, stage_id, artifact, mode=state["mode"]["name"])
    report["problems"] = (
        _input_receipt_problems(order["input_receipts"], artifact.get("input_receipts"))
        + _work_order_binding_problems(state, order, artifact)
        + report["problems"]
    )
    report["form_ok"] = not report["problems"]
    validation_path = attempt / order["validation_path"]
    validation_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    stage = state["stages"][stage_id]
    record = {
        "attempt": order["attempt_number"],
        "variation_strategy": order["variation_strategy"],
        "artifact_path": order["artifact_path"],
        "artifact_sha256": report["artifact_sha256"],
        "validation_path": order["validation_path"],
        "validation_sha256": file_sha256(validation_path),
        "form_ok": report["form_ok"],
        "critic": None,
    }
    stage["attempts"].append(record)
    state["active_work"] = None
    if not report["form_ok"]:
        stage["status"] = "needs_repair" if order["attempt_number"] < MAX_ATTEMPTS else "blocked"
        stage["last_feedback"] = report["problems"]
        if stage["status"] == "blocked":
            state["status"] = "blocked"
        state["events"].append({"at": _now(), "event": "integrity_failed",
                                "stage_id": stage_id, "attempt_number": order["attempt_number"]})
        _write_state(attempt, state)
        return {"status": stage["status"], "stage_id": stage_id,
                "attempt_number": order["attempt_number"], "problems": report["problems"]}
    stage["status"] = "awaiting_critic"
    stage["last_feedback"] = []
    stage["pending_critique"] = {
        "artifact_path": order["artifact_path"],
        "artifact_sha256": report["artifact_sha256"],
        "critique_path": order["critique_path"],
        "criteria": order["critic_criteria"],
    }
    state["events"].append({"at": _now(), "event": "integrity_passed",
                            "stage_id": stage_id, "attempt_number": order["attempt_number"]})
    _write_state(attempt, state)
    return {"status": "critic_required", "stage_id": stage_id,
            "artifact_sha256": report["artifact_sha256"],
            "critique_path": order["critique_path"], "criteria": order["critic_criteria"]}


def _seal(attempt: Path, state: dict, stage_id: str, *, resolution: str,
          accepted_defects: list | None = None, approved_by: str | None = None) -> dict:
    stage = state["stages"][stage_id]
    latest = stage["attempts"][-1]
    candidate = attempt / latest["artifact_path"]
    output = attempt / stage_id / "output" / "stage-artifact.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(candidate, output)
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "pipeline_version": PIPELINE_VERSION,
        "stage_id": stage_id,
        "created_at": _now(),
        "attempt_id": state["attempt_id"],
        "artifact_path": str(output.relative_to(attempt)),
        "artifact_sha256": canonical_sha256(load_json(output, "promoted artifact")),
        "author_attempt": latest["attempt"],
        "validation_path": latest["validation_path"],
        "critique_path": (latest.get("critic") or {}).get("path"),
        "resolution": resolution,
        "approved_by": approved_by,
        "accepted_defects": accepted_defects or [],
        "input_receipts": load_json(output).get("input_receipts") or [],
        "external_side_effects_authorized": False,
    }
    receipt_path = attempt / stage_id / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    stage.update({"status": "passed", "artifact": str(output.relative_to(attempt)),
                  "receipt": str(receipt_path.relative_to(attempt)),
                  "accepted_defects": accepted_defects or [], "pending_critique": None})
    index = STAGE_INDEX[stage_id]
    if index == len(STAGES) - 1:
        state["current_stage"] = None
        state["status"] = "complete"
    else:
        state["current_stage"] = STAGES[index + 1]["id"]
        state["status"] = "running"
    state["events"].append({"at": _now(), "event": "stage_sealed",
                            "stage_id": stage_id, "resolution": resolution})
    state["updated_at"] = _now()
    _write_state(attempt, state)
    return {"status": state["status"], "stage_id": stage_id,
            "receipt": str(receipt_path), "next_stage": state.get("current_stage")}


def review(attempt: Path, review_path: Path | None = None) -> dict:
    attempt = attempt.resolve()
    state = load_state(attempt)
    stage_id = state.get("current_stage")
    stage = state["stages"][stage_id]
    if stage.get("status") != "awaiting_critic" or not stage.get("pending_critique"):
        raise OrchestratorError("stage is not awaiting a critic")
    pending = stage["pending_critique"]
    path = review_path.resolve() if review_path else attempt / pending["critique_path"]
    try:
        path.relative_to(attempt)
    except ValueError as error:
        raise OrchestratorError("critique must remain inside the production attempt") from error
    critique = load_json(path, "stage critique")
    check = validate_critique(stage_id, critique, pending["artifact_sha256"])
    if not check["ok"]:
        return {"status": "critic_retry_required", "stage_id": stage_id,
                "problems": check["problems"], "critique_path": str(path)}
    latest = stage["attempts"][-1]
    latest["critic"] = {"path": str(path.relative_to(attempt)),
                         "sha256": file_sha256(path), "decision": critique["decision"]}
    number = latest["attempt"]
    if critique["decision"] == "fail":
        feedback = [{"code": "critic-failure", "path": item.get("criterion_id"),
                     "message": item.get("evidence")}
                    for item in critique.get("criteria") or [] if item.get("status") == "fail"]
        classes = set(critique.get("failure_classes") or ["quality"])
        accepted = list(critique.get("accepted_defects") or [])
        if number == MAX_ATTEMPTS and state["mode"]["name"] == "fast_track" and classes <= {"quality"} and accepted:
            return _seal(attempt, state, stage_id, resolution="fast_track_attempt_10",
                         accepted_defects=accepted, approved_by=critique.get("reviewer"))
        stage["status"] = "needs_repair" if number < MAX_ATTEMPTS else "human_gate"
        stage["last_feedback"] = feedback
        stage["pending_critique"] = None
        if number == MAX_ATTEMPTS:
            state["status"] = "human_gate"
        state["events"].append({"at": _now(), "event": "critic_failed",
                                "stage_id": stage_id, "attempt_number": number})
        _write_state(attempt, state)
        return {"status": stage["status"], "stage_id": stage_id,
                "attempt_number": number, "feedback": feedback}
    if state["mode"]["name"] == "normal" and stage_id in state["normal_human_gates"]:
        stage["status"] = "human_gate"
        stage["pending_approval"] = {
            "artifact_sha256": pending["artifact_sha256"],
            "summary": critique.get("summary"),
            "critique_path": str(path.relative_to(attempt)),
        }
        stage["pending_critique"] = None
        state["status"] = "human_gate"
        _write_state(attempt, state)
        return {"status": "human_gate", "stage_id": stage_id,
                "artifact_sha256": pending["artifact_sha256"],
                "summary": critique.get("summary")}
    return _seal(attempt, state, stage_id, resolution="ai_fast_track" if state["mode"]["name"] == "fast_track" else "ai_preflight",
                 approved_by=critique.get("reviewer"))


def approve(attempt: Path, stage_id: str, *, by: str, decision: str,
            feedback: str = "") -> dict:
    attempt = attempt.resolve()
    state = load_state(attempt)
    if state.get("current_stage") != stage_id or state["stages"][stage_id].get("status") != "human_gate":
        raise OrchestratorError("the requested stage is not at a human gate")
    if decision not in {"approve", "revise", "reject"} or not by.strip():
        raise OrchestratorError("decision must be approve, revise, or reject and reviewer is required")
    stage = state["stages"][stage_id]
    if decision == "approve":
        return _seal(attempt, state, stage_id, resolution="human_approved", approved_by=by)
    if decision == "revise" and len(stage["attempts"]) < MAX_ATTEMPTS:
        stage["status"] = "needs_repair"
        stage["last_feedback"] = [{"code": "human-revision", "path": stage_id,
                                   "message": feedback or "human requested revision"}]
        stage["pending_approval"] = None
        state["status"] = "running"
        _write_state(attempt, state)
        return {"status": "needs_repair", "stage_id": stage_id,
                "feedback": stage["last_feedback"]}
    stage["status"] = "blocked"
    stage["last_feedback"] = [{"code": "human-rejected", "path": stage_id,
                               "message": feedback or "human rejected artifact"}]
    state["status"] = "blocked"
    _write_state(attempt, state)
    return {"status": "blocked", "stage_id": stage_id, "feedback": stage["last_feedback"]}


def set_mode(attempt: Path, mode: str, *, by: str, reason: str) -> dict:
    attempt = attempt.resolve()
    state = load_state(attempt)
    if mode not in {"normal", "fast_track"} or not by.strip() or not reason.strip():
        raise OrchestratorError("valid mode, explicit user, and reason are required")
    state["mode"] = {"name": mode, "set_by": by, "reason": reason,
                     "set_at": _now(), "external_side_effects_authorized": False}
    state["events"].append({"at": _now(), "event": "mode_changed", "mode": mode, "by": by})
    if state.get("active_work"):
        state["active_work"]["mode"] = state["mode"]
    state["updated_at"] = _now()
    stage_id = state.get("current_stage")
    if (mode == "fast_track" and stage_id
            and state["stages"][stage_id].get("status") == "human_gate"
            and state["stages"][stage_id].get("pending_approval")):
        return _seal(attempt, state, stage_id, resolution="explicit_fast_track_mode_switch",
                     approved_by=by)
    _write_state(attempt, state)
    return state["mode"]
