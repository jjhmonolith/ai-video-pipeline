"""Executable human-gate contracts for the AI video pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .execution_mode import FAST_TRACK_MODE, NORMAL_MODE


class GateContractError(ValueError):
    """Raised when a persisted gate artifact violates the contract."""


def _require(condition: bool, field: str) -> None:
    if not condition:
        raise GateContractError(field)


def load_catalog(path: Path | str) -> Dict[str, Any]:
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    _require(payload.get("schema_version") == "1.0.0", "schema_version")
    gates = payload.get("gates")
    _require(isinstance(gates, list), "gates")
    _require([g.get("gate_id") for g in gates] == [f"G{i}" for i in range(1, 11)], "gates.order")
    required = {
        "gate_id", "name", "owner_roles", "stages", "trigger_dimensions",
        "required_evidence", "question_contract", "output_fields", "authority",
    }
    for index, gate in enumerate(gates):
        _require(required <= set(gate), f"gates.{index}.fields")
        for field in ("owner_roles", "stages", "trigger_dimensions", "required_evidence", "output_fields"):
            _require(isinstance(gate[field], list) and gate[field], f"gates.{index}.{field}")
        _require(gate["question_contract"].get("single_decision") is True, f"gates.{index}.question_contract")
        _require(gate["authority"] in {"human_required", "human_release_only"}, f"gates.{index}.authority")
    return payload


def resolve_required_gates(catalog: Dict[str, Any], event: Dict[str, Any]) -> Dict[str, Any]:
    stage = event.get("stage")
    dimensions = set(event.get("dimensions", []))
    matches: List[str] = []
    for gate in catalog["gates"]:
        if stage in gate["stages"] and dimensions.intersection(gate["trigger_dimensions"]):
            matches.append(gate["gate_id"])

    reasons: List[str] = []
    for key in ("hero_take", "critic_disagreement", "release", "culture_risk", "rights_risk"):
        if event.get(key):
            reasons.append(key)
    margin = event.get("ai_margin")
    threshold = catalog.get("policy", {}).get("close_pair_threshold_5pt", 0.5)
    if isinstance(margin, (int, float)) and margin <= threshold:
        reasons.append("close_ai_margin")

    execution_mode = event.get("execution_mode", NORMAL_MODE)
    _require(execution_mode in {NORMAL_MODE, FAST_TRACK_MODE}, "execution_mode")
    fast_track = execution_mode == FAST_TRACK_MODE
    human_required = bool(matches) and not fast_track
    return {
        "gate_ids": matches,
        "human_required": human_required,
        "auto_approve_allowed": not human_required,
        "execution_mode": execution_mode,
        "resolution_mode": "ai_fast_track" if fast_track and matches else "human" if matches else "none",
        "accepted_defect_record_required": fast_track and bool(matches),
        "external_side_effects_authorized": False,
        "reasons": reasons,
    }


def validate_judgment_packet(packet: Dict[str, Any], catalog: Dict[str, Any]) -> List[str]:
    gate_ids = {gate["gate_id"] for gate in catalog["gates"]}
    _require(packet.get("gate_id") in gate_ids, "gate_id")
    for field in (
        "decision_id", "scope_ids", "shot_or_scene_purpose", "locked_quality_rules",
        "options", "ai_recommendation", "why_human_needed", "one_question", "answer_modes",
    ):
        _require(field in packet, field)
    _require(isinstance(packet["scope_ids"], list) and packet["scope_ids"], "scope_ids")
    _require(isinstance(packet["options"], list) and len(packet["options"]) >= 2, "options")
    ids: List[str] = []
    for index, option in enumerate(packet["options"]):
        for field in ("id", "asset", "strength", "loss", "detected_defects", "downstream_cost"):
            _require(field in option and option[field] not in (None, ""), f"options.{index}.{field}")
        ids.append(option["id"])
    _require(len(ids) == len(set(ids)), "options.ids")
    _require(packet["ai_recommendation"] in ids, "ai_recommendation")
    question = packet["one_question"].strip()
    _require(question.endswith("?"), "one_question")
    _require(question.count("?") == 1, "one_question.single_decision")
    _require(set(packet["answer_modes"]) <= {"select", "combine", "preserve_and_change", "free_text"}, "answer_modes")
    return []


def validate_feedback_delta(delta: Dict[str, Any]) -> List[str]:
    required = (
        "gate_id", "scope_ids", "keep", "change", "forbid", "priority_order",
        "accepted_defects", "regeneration_scope", "verification_question", "user_words",
    )
    for field in required:
        _require(field in delta, field)
    _require(delta["gate_id"] in {f"G{i}" for i in range(1, 11)}, "gate_id")
    for field in ("scope_ids", "keep", "change", "forbid", "priority_order", "accepted_defects"):
        _require(isinstance(delta[field], list), field)
    _require(bool(delta["scope_ids"]), "scope_ids")
    _require(bool(delta["priority_order"]), "priority_order")
    _require(bool(str(delta["user_words"]).strip()), "user_words")
    _require(str(delta["verification_question"]).strip().endswith("?"), "verification_question")
    return []
