"""Compile shot cards into both prompt packs, so they cannot drift apart.

A production take needs one approved start plate. It also receives every
relevant canonical stage-02 sheet and, when stage 04 requires one, an approved
multi-view/multi-state interaction-manual board. The semantic end state remains
a QA target rather than a generated H3 last frame.

    shot card ─┬─> image prompts ──> start plate ─┐
               │                                  ├─> H3 (first_frame, references, text)
               └─> video prompt ─────────────┘

Writing the two packs by hand breaks this. It already happened once: the takes
were restructured into longer ones in the video pack while the cards kept the
old eight-shot list, and a plate was left that no take referenced. The cards
are the source; both packs are generated.

States are shared only when the design says they are shared.  Forcing every
end state to become the next start state was correct for one locked-off scene,
but wrong across a cut to a new angle or room.  Current cards own independent
state pairs by default and may intentionally reuse a state id.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .contract import Contract


def collect_states(cards: list[dict]) -> list[str]:
    """Every distinct state named by the cards, in the order takes reach them."""
    ordered: list[str] = []
    for card in cards:
        pair = card.get("state_pair") or card
        anchor_policy = ((card.get("h3_generation") or {}).get("anchor_policy")
                         or (card.get("motion_control") or {}).get("anchor_policy")
                         or "first_only")
        guide_states = [item.get("state_id") for item in
                        (card.get("motion_control") or {}).get("guide_plan", [])]
        conditioned = [pair.get("start_state_id"), *guide_states]
        if anchor_policy == "paired":
            conditioned.append(pair.get("end_state_id"))
        for state in conditioned:
            if state and state not in ordered:
                ordered.append(state)
    return ordered


def compile_plate_chain(cards: list[dict], states: dict, look: dict) -> dict:
    used = collect_states(cards)
    unknown = [s for s in used if s not in states]
    if unknown:
        raise ValueError(f"카드가 정의되지 않은 상태를 참조한다: {unknown}")

    plates = []
    for state_id in used:
        spec = states[state_id]
        entry = {
            "id": state_id,
            "mode": spec.get("mode", "edit" if spec.get("from") else "create"),
            "used_by": ", ".join(
                f"{c.get('shot_id', c.get('take_id'))}"
                for c in cards
                if state_id in collect_states([c])
            ),
            "prompt": spec["prompt"],
            "required_reference_subject_ids": spec.get("required_reference_subject_ids", []),
            "required_interaction_manual_ids": spec.get("required_interaction_manual_ids", []),
            "reference_locks": spec.get("reference_locks", []),
            "geometry_locks": spec.get("geometry_locks", []),
            "screen_direction_contract": spec.get("screen_direction_contract"),
            "edit_scope": spec.get("edit_scope"),
        }
        if spec.get("from"):
            entry["from"] = spec["from"]
        plates.append(entry)

    reference_manuals = []
    seen_manuals = set()
    for card in cards:
        plan = card.get("supplemental_reference_plan") or {}
        for manual in plan.get("manuals") or []:
            manual_id = manual.get("manual_id")
            if manual_id and manual_id not in seen_manuals:
                reference_manuals.append(manual)
                seen_manuals.add(manual_id)

    qa_targets = [
        (card.get("state_pair") or card).get("end_state_id")
        for card in cards
        if (card.get("state_pair") or card).get("end_state_usage") == "qa_target_only"
        and (card.get("state_pair") or card).get("end_state_id")
    ]
    orphans = [s for s in states if s not in used and s not in qa_targets]
    return {
        "pack_id": look.get("pack_id", "stage05-plate-pack"),
        "model": look.get("model"), "size": look.get("size"),
        "quality": look.get("quality"),
        "purpose": look.get("purpose", "H3 state and guide plates"),
        "set_description": look.get("set_description"),
        "global_constraints": look.get("global_constraints", []),
        "reference_status": look.get("reference_status"),
        "edit_constraints": look.get(
            "edit_constraints", ["edit only allowed_change; preserve every invariant"]),
        "compiled_from": "shot-cards.json",
        "execution_order": [
            "render and approve required reference_manuals from canonical stage-02 sheets",
            "render and approve start plates from canonical stage-02 sheets plus approved manuals",
            "resolve screen-direction annotations on approved start plates",
        ],
        "qa_target_states": qa_targets,
        "orphan_states": orphans,
        "reference_manuals": reference_manuals,
        "plates": plates,
    }


def compile_shot_pack(cards: list[dict], motion: dict) -> dict:
    """The video prompt is compiled after the plates exist, not alongside them.

    Production conditioning is first-only. The semantic end state remains in
    the card for QA, but is not compiled as an H3 last frame. Research cards may
    opt into `paired` explicitly. A card may therefore carry `observed` and
    `motion_prompt_amendment`, filled in after looking at the plates, and the
    amendment replaces the prompt while both stay on the record.
    """
    shots = []
    for card in cards:
        amendment = card.get("motion_prompt_amendment")
        pair = card.get("state_pair") or card
        generation = card.get("h3_generation") or {}
        control = card.get("motion_control") or {}
        requirements = card.get("reference_requirements") or {}
        manual_plan = card.get("supplemental_reference_plan") or {}
        anchor_policy = (generation.get("anchor_policy")
                         or control.get("anchor_policy") or "first_only")
        manual_ids = [item.get("manual_id") for item in manual_plan.get("manuals") or []
                      if item.get("manual_id")]
        manual_pending = bool(
            manual_plan.get("required")
            and (manual_plan.get("generation_blocked_until_approved_manuals")
                 or any((item.get("approval") or {}).get("status") != "approved"
                        for item in manual_plan.get("manuals") or []))
        )
        direction_pending = bool(
            (control.get("screen_direction_contract") or {}).get(
                "generation_blocked_until_resolved")
        )
        temporal_pending = bool(generation.get("generation_blocked"))
        shots.append({
            "shot": card.get("shot_id", card.get("take_id")),
            "sequence_id": card.get("sequence_id"),
            "scene_id": card.get("scene_id"),
            "setup_id": card.get("setup_id"),
            "included_in_timeline": card.get("included_in_timeline", True),
            "edit_seconds": card.get("edit_seconds", card.get("seconds")),
            "generation_seconds": generation.get(
                "requested_seconds", card.get("edit_seconds", card.get("seconds"))),
            "native_frames": generation.get("native_frames"),
            "temporal_design": card.get("temporal_design"),
            "retime_plan": generation.get("retime_plan"),
            "runtime": generation.get("runtime", motion.get("runtime")),
            "h3_route": generation.get("route", motion.get("route")),
            "anchor_policy": anchor_policy,
            "first_plate": pair.get("start_state_id"),
            "last_plate": pair.get("end_state_id") if anchor_policy == "paired" else None,
            "guide_plan": control.get("guide_plan", []),
            "changing_variable": pair.get("changing_variable", card.get("changing_variable")),
            "invariants": pair.get("invariants", []),
            "allowed_change": pair.get("allowed_change", []),
            "camera_policy": card.get("camera_policy"),
            "semantic_tracks": control.get("subject_tracks", []),
            "screen_direction_contract": control.get("screen_direction_contract"),
            "generation_blocked": direction_pending or manual_pending or temporal_pending,
            "generation_block_reasons": list(filter(None, [
                "screen_direction_annotation_pending" if direction_pending else None,
                "interaction_manual_generation_or_approval_pending" if manual_pending else None,
                "temporal_capability_debt" if temporal_pending else None,
            ])),
            "required_stage02_sheet_subject_ids": requirements.get(
                "canonical_stage02_sheet_subject_ids", []),
            "canonical_stage02_sheets_required": requirements.get(
                "canonical_stage02_sheets_required", True),
            "required_interaction_manual_ids": manual_ids,
            "reference_policy": {
                "whole_stage02_boards_required": requirements.get("whole_boards_required", True),
                "supplemental_manuals_replace_canonical_boards": False,
                "h3_reference_image_limit": requirements.get("h3_reference_image_limit", 9),
            },
            "reference_locks": pair.get("reference_locks", []),
            "geometry_locks": pair.get("geometry_locks", []),
            "plate_acceptance": card.get("plate_acceptance"),
            "candidate_policy": card.get("candidate_policy"),
            "prompt": amendment["prompt"] if amendment else card["motion_prompt"],
            "prompt_source": "amended_after_look" if amendment else "card",
            "observed_in_plates": card.get("observed"),
            "amendment_reason": amendment["reason"] if amendment else None,
            "prompt_before_amendment": card["motion_prompt"] if amendment else None,
        })
    return {
        "pack_id": motion.get("pack_id", "stage06-h3-shot-pack"),
        "video_engine": motion.get("video_engine", motion.get("runtime")),
        "other_video_engines_allowed": False,
        "note": motion.get(
            "note", "semantic tracks are QA contracts; H3 consumes text and image anchors"),
        "compiled_from": "shot-cards.json",
        "global_constraints": motion.get("global_constraints", []),
        "total_edit_seconds": sum(float(s["edit_seconds"]) for s in shots
                                  if s.get("included_in_timeline", True)),
        "total_capture_seconds": sum(float(s.get("generation_seconds") or 0) for s in shots),
        "shots": shots,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="shot card에서 두 프롬프트 팩을 생성")
    parser.add_argument("attempt", type=Path)
    args = parser.parse_args()

    contract = Contract.load(args.attempt)
    shot_stage = contract.stage_for("shot_design", "04-shot-design")
    plate_stage = contract.stage_for("plate", "05-plate")
    motion_stage = contract.stage_for("motion", "06-motion")

    cards_path = args.attempt / shot_stage / "output" / "shot-cards.json"
    source = json.loads(cards_path.read_text(encoding="utf-8"))
    cards = source.get("shots") or source.get("takes") or []

    plate_stage_name = contract.stage_for("plate", "05-plate")
    plan = contract.image_plan("plate")
    look = source.get("look") or {
        "pack_id": f"{source.get('design_id', 'SHOT-DESIGN')}-PLATES",
        "model": contract.image_model,
        "size": plan.api_size,
        "quality": contract.image_quality("plate"),
        "purpose": "H3 start/end/guide state plates",
        "global_constraints": contract.clause_ids(plate_stage_name),
        "reference_status": source.get("reference_status"),
    }
    motion = source.get("motion") or {
        "pack_id": f"{source.get('design_id', 'SHOT-DESIGN')}-H3",
        "runtime": source.get("engine_policy", {}).get("video_engine"),
        "video_engine": source.get("engine_policy", {}).get("video_engine"),
        "global_constraints": contract.clause_ids(contract.stage_for("motion", "06-motion")),
    }
    plate_pack = compile_plate_chain(cards, source["states"], look)
    shot_pack = compile_shot_pack(cards, motion)

    plate_out = args.attempt / plate_stage / "prompts" / "plate-chain.json"
    motion_out = args.attempt / motion_stage / "prompts" / "shot-pack.json"
    for path, payload in ((plate_out, plate_pack), (motion_out, shot_pack)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"테이크 {len(cards)}개 -> 상태 {len(plate_pack['plates'])}개, "
          f"총 {shot_pack['total_edit_seconds']}초")
    if plate_pack["orphan_states"]:
        print(f"어느 테이크도 쓰지 않는 상태: {plate_pack['orphan_states']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
