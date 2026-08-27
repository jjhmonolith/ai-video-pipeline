"""03-scenario: design sequences, scenes, events, and reference debt.

Stage 03 is a screenplay/narrative-design stage, not a shot-list compiler.  It
decides what happens, why the scene exists, whose experience organizes it, and
which state enters and leaves the scene.  It may estimate a scene's editorial
range and pacing, but it does not choose lenses, camera moves, shot boundaries,
or exact shot seconds.  Those are Stage 04 directorial and editorial decisions.

The approved Stage-02 references are a canonical starting vocabulary, not a
ban on storytelling.  A scenario may invent a needed prop, location detail, or
interaction after the story problem becomes clear.  It must record that choice
as reference debt so Stage 04 can classify it and Stage 05 can create the
missing production reference before any start plate is generated.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .contract import Contract, ContractError, load as load_contract
from .research import DEFAULT_MODEL, _client
from .lifecycle import read_direction_impact, read_premise_state
from .generation_harness import (
    MAX_GENERATION_ATTEMPTS,
    attempt_record,
    harness_contract,
    retry_prompt,
)
from .execution_mode import load_execution_mode

STAGE_ROLE = "scenario"
STAGE_FALLBACK = "03-scenario"

SCENARIO_SCHEMA = "narrative-design.v3"
REFERENCE_CLASSES = {
    "recurring_canonical_asset",
    "scene_only_hero_prop",
    "interaction_target",
    "sublocation_detail",
    "background_dressing",
    "offscreen_only",
}

WRITER_RULES = """
계약과 지시사항을 따르는 영상의 시퀀스와 신을 설계한다. 이것은 촬영표가 아니다.

반드시 지킬 경계:
- 시퀀스 → 신 → 드라마틱 이벤트의 계층으로 쓴다.
- 신마다 intent, role, POV owner, dramatic question, entry state, exit state를 먼저 쓴다.
- 카메라, 렌즈, 앵글, 구도, shot/cut 번호, 정확한 shot 초수는 쓰지 않는다.
- Stage 1의 runtime_contract를 그대로 인용한다. 신에는 estimated_edit_range_seconds와
  pacing/temporal_intent만 적고, 모든 비트 합을 총 길이에 억지로 맞추지 않는다.
- 사건량과 시간 범위가 맞는지 서사적으로 설명한다. 초당 행동 수 같은 기계 공식은 쓰지 않는다.
- 슬로모션, 시간정지, bullet-time/3D orbit, 타임랩스, 속도 램프처럼 현실 시간과
  편집 시간이 다른 아이디어는 temporal_intent에 후보와 극적 이유만 적는다.
  실행 방식과 정확한 길이는 Stage 4가 결정한다.
- 승인된 정의와 보드에 없는 새 소품·장소 세부·행위를 발명해도 된다. 다만 중요하거나
  반복되거나 상호작용하는 새 요소는 production_requirements에 반드시 등록한다.
- 새 요소는 recurring_canonical_asset, scene_only_hero_prop, interaction_target,
  sublocation_detail, background_dressing, offscreen_only 중 하나로 분류한다.
  앞의 네 종류는 Stage 5 이전에 새 reference가 필요하다. background_dressing은
  prompt-only, offscreen_only는 image 불필요다.
- 새 요소를 기존 Stage-01 subject id인 것처럼 위장하지 않는다. `NEW-`로 시작하는 id를 쓴다.
- 대사는 onscreen_spoken/voiceover/none으로 구분한다. H3 생성 음성은 사용하지 않는다.
- 물리적 상호작용은 actor, target, 시작·중간·완료 상태, 고정부와 이동부를 적는다.
  정의에 없는 치수나 도구 용량은 발명하지 말고 production requirement의 해결 항목으로 남긴다.

JSON 객체 하나만 반환한다. 최소 형식:
{
  "schema_version": "narrative-design.v3",
  "logline": "한 줄",
  "viewer_promise": "관객이 얻게 될 것",
  "acts": {"막 id": "역할"},
  "sequences": [{
    "id": "SQ01", "purpose": "시퀀스 목적", "dramatic_progression": "변화",
    "scenes": [{
      "id": "SC01", "act_id": "막 id", "slugline": "장소/시간",
      "where_subject_id": "기존 배경 id 또는 NEW id", "sublocation_id": "공간 node 또는 NEW id",
      "scene_intent": "이 신이 관객에게 일으킬 것", "scene_role": "서사 기능",
      "pov_owner": "인물 id/관객/객관", "dramatic_question": "이 신의 질문",
      "entry_state": "시작 상태", "exit_state": "끝 상태",
      "estimated_edit_range_seconds": [4, 9],
      "pacing": {"tempo": "압축/보통/유예", "reason": "사건량과 리듬의 이유"},
      "temporal_intent": {"candidate_modes": ["real_time"], "dramatic_reason": "이유"},
      "events": [{"id": "E01", "actor_subject_id": "id 또는 null",
        "action": "사건", "target_subject_id": "기존 또는 NEW id/null",
        "visible_change": "가시적 변화", "result_state": "완료 상태"}],
      "dialogue": {"mode": "onscreen_spoken/voiceover/none", "text": "", "language": "ko/null",
        "lip_sync_required": false},
      "cast_presence": [{"subject_id": "인물 id", "role": "actor/available"}],
      "object_roles": [{"subject_id": "기존 또는 NEW id", "role": "required_visible/available/interacted_with"}],
      "visual_focus": ["기존 또는 NEW id"],
      "production_requirements": [{"id": "NEW-...", "name": "새 요소명",
        "asset_class": "scene_only_hero_prop", "description": "형태와 서사 기능",
        "reference_policy": "full_sheet/scene_reference/action_reference/location_reference/prompt_only/none",
        "used_by_event_ids": ["E01"], "resolution_notes": ["Stage 4/5에서 결정할 사실"]}],
      "transition_in": "이전 신과 연결", "transition_out": "다음 신과 연결"
    }]
  }]
}
"""

SHARE_TOLERANCE = 0.12   # 막 비중이 이만큼 벗어나면 지적한다
KOREAN_CHARS_PER_SECOND = 4.0


class ScenarioError(RuntimeError):
    """The scenario could not be written, or contradicts what was declared."""


def stage_name(contract: Contract) -> str:
    return contract.stage_for(STAGE_ROLE, STAGE_FALLBACK)


def stage_dir(attempt: Path, contract: Contract) -> Path:
    return attempt / stage_name(contract)


def _subjects_dir(attempt: Path, contract: Contract) -> Path:
    where = contract.get("subjects", {}).get(
        "directory", f'{contract.stage_for("premise", "01-premise")}/output/subjects')
    return attempt / where


def _sheets_dir(attempt: Path, contract: Contract) -> Path:
    return attempt / contract.stage_for("sheet", "02-sheet") / "output" / "sheets"


def gather(attempt: Path, contract: Contract) -> tuple[dict, list[tuple[str, Path]]]:
    """Definitions as text, only human-approved selective crops as pictures."""
    state = read_premise_state(attempt, contract)
    if state.get("form_ok") is False:
        raise ScenarioError("01-premise form_ok=false라 새 시나리오를 생성할 수 없다")
    impact = read_direction_impact(attempt, contract)
    if not impact.get("downstream_allowed", True):
        raise ScenarioError(
            f"direction 영향 재검토가 {impact.get('unresolved_count', 0)}건 남아 있다")

    definitions, boards = {}, []
    folder = _subjects_dir(attempt, contract)
    sheet_stage = attempt / contract.stage_for("sheet", "02-sheet")
    semantic_path = sheet_stage / "qa" / "semantic-review.json"
    manifest_path = sheet_stage / "qa" / "panel-manifest.json"
    if not semantic_path.exists() or not manifest_path.exists():
        raise ScenarioError("02-sheet semantic review와 panel manifest가 없다")
    semantic = json.loads(semantic_path.read_text(encoding="utf-8"))
    if not semantic.get("reference_ready"):
        raise ScenarioError("02-sheet가 human_review_required라 새 시나리오의 이미지 입력으로 쓸 수 없다")
    panel_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    selected_identity: dict[str, Path] = {}
    selected_motion: dict[str, list[Path]] = {}
    for sheet in panel_manifest.get("sheets", []):
        for panel in sheet.get("panels", []):
            crop = panel.get("reference_crop_path")
            if (panel.get("review_status") == "approved"
                    and panel.get("safe_for_identity_reference") is True and crop):
                path = attempt / crop
                if path.is_file():
                    selected_identity.setdefault(sheet.get("subject_id"), path)
            if (panel.get("review_status") == "approved"
                    and panel.get("safe_for_motion_reference") is True and crop):
                bindings = (list(panel.get("binds_part_ids") or [])
                            + list(panel.get("binds_interaction_site_ids") or []))
                if not bindings:
                    raise ScenarioError(
                        f"{panel.get('panel_id')}: motion reference가 part/site id에 결속되지 않았다")
                path = attempt / crop
                if path.is_file():
                    selected_motion.setdefault(sheet.get("subject_id"), []).append(path)
    for name in sorted(contract.elements()):
        path = folder / f"{name}.json"
        if not path.exists():
            raise ScenarioError(f"{name}: 정의가 없다 {path}")
        spec = json.loads(path.read_text(encoding="utf-8"))
        definitions[name] = {k: v for k, v in spec.items()
                             if k not in {"provenance", "evidence", "decisions",
                                          "evidence_context_legacy"}}
        board = selected_identity.get(name)
        if board is None:
            raise ScenarioError(f"{name}: 승인된 selective reference crop이 없다")
        boards.append((f"{name}:identity_reference", board))
        for motion_board in selected_motion.get(name, []):
            if motion_board != board:
                boards.append((f"{name}:motion_affordance_reference", motion_board))
    return definitions, boards


def iter_scenes(story: dict) -> list[dict]:
    """Return Stage-03 narrative units while preserving legacy attempts.

    New work is scene based.  Historical ``beats`` remain readable so old
    attempts can be audited and migrated without rewriting their artifacts.
    """
    scenes: list[dict] = []
    for sequence in story.get("sequences") or []:
        if not isinstance(sequence, dict):
            continue
        for scene in sequence.get("scenes") or []:
            if isinstance(scene, dict):
                row = dict(scene)
                row.setdefault("sequence_id", sequence.get("id"))
                scenes.append(row)
    if scenes:
        return scenes
    return [dict(beat) for beat in story.get("beats") or [] if isinstance(beat, dict)]


def _scene_range(scene: dict) -> tuple[float, float]:
    raw = scene.get("estimated_edit_range_seconds")
    if isinstance(raw, list) and len(raw) == 2:
        low, high = raw
        if all(isinstance(value, (int, float)) and not isinstance(value, bool)
               for value in (low, high)):
            return float(low), float(high)
    legacy = scene.get("seconds")
    if isinstance(legacy, (int, float)) and not isinstance(legacy, bool):
        return float(legacy), float(legacy)
    return 0.0, 0.0


def _scenario_estimated_range(story: dict) -> list[float]:
    ranges = [_scene_range(scene) for scene in iter_scenes(story)]
    return [round(sum(item[0] for item in ranges), 3),
            round(sum(item[1] for item in ranges), 3)]


def _runtime_bounds(contract: Contract) -> tuple[float | None, float | None]:
    runtime = contract.runtime_contract
    mode = runtime.get("mode")
    if mode == "fixed":
        target = float(runtime["target_seconds"])
        return target, target
    if mode == "range":
        return float(runtime["min_seconds"]), float(runtime["max_seconds"])
    return None, None


def write(attempt: Path, contract: Contract, model: str | None = None,
          generation_attempt: int = 1, correction: str = "") -> dict:
    from .premise import full_direction

    definitions, boards = gather(attempt, contract)
    runtime = contract.runtime_contract
    clauses = contract.clause_text(stage_name(contract)) or contract.clause_text("05-plate")

    structure = contract.scenario_structure()
    acts_text = "\n".join(
        f'  {a["id"]}: {a.get("must", "")}'
        for a in structure.get("acts", []))

    base_prompt = "\n\n".join([
        WRITER_RULES,
        "Stage 1 runtime contract:\n" + json.dumps(runtime, ensure_ascii=False, indent=2),
        f'막 구조 [{structure.get("structure_id","custom")}]. '
        f'맞는 형식: {structure.get("fits","")}\n' + acts_text,
        "지시사항:\n" + full_direction(attempt),
        "요소 정의:\n" + json.dumps(definitions, ensure_ascii=False, indent=2),
        "지켜야 할 조항:\n" + (clauses or "(없음)"),
        "아래 이미지는 각 요소별 사람 승인 selective reference crop이다. 순서는 "
        + ", ".join(name for name, _ in boards),
    ])
    effective_prompt = retry_prompt(
        base_prompt, generation_attempt, correction,
        failed_criteria=[line for line in correction.splitlines() if line.strip()],
        allowed_revisions=(
            "sequence, scene and event structure owned by Stage 03",
            "scene intent, POV, dramatic question, pacing range and temporal intent",
            "story-motivated NEW production requirements and their reference-debt classification",
        ))
    content = [{"type": "input_text", "text": effective_prompt}]
    for _, path in boards:
        encoded = base64.b64encode(path.read_bytes()).decode()
        content.append({"type": "input_image",
                        "image_url": f"data:image/png;base64,{encoded}"})

    client = _client()
    response = client.responses.create(
        model=model or contract.text_model or DEFAULT_MODEL,
        input=[{"role": "user", "content": content}],
        text={"format": {"type": "json_object"}})

    story = json.loads(response.output_text)
    story["schema_version"] = SCENARIO_SCHEMA
    story["scenario_id"] = f"{contract.data['contract_id']}-SCENARIO"
    story["written_at"] = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    story["written_by"] = model or contract.text_model or DEFAULT_MODEL
    story["boards_seen"] = [name for name, _ in boards]
    story["runtime_contract"] = runtime
    story["estimated_edit_range_seconds"] = _scenario_estimated_range(story)
    story["contract"] = contract.receipt_block(stage_name(contract))
    story["_harness_effective_prompt"] = effective_prompt
    return story


def _speech_seconds(beat: dict) -> float:
    dialogue = beat.get("dialogue") or {}
    if dialogue:
        if dialogue.get("mode") in {"none", "silent"}:
            return 0.0
        text = str(dialogue.get("text", ""))
    else:
        text = str(beat.get("line", ""))
    count = len(re.findall(r"[0-9A-Za-z가-힣]", text))
    return round(count / KOREAN_CHARS_PER_SECOND, 2) if count else 0.0


def _action_units(beat: dict) -> int:
    explicit = beat.get("sub_beats")
    if isinstance(explicit, list) and explicit:
        return max(1, len(explicit))
    text = str(beat.get("what_happens", ""))
    # This is a conservative language-level estimate, not a genre action list.
    clauses = [p for p in re.split(r"[,.。]|(?:하고|하며|이어|다가|자\s)", text) if p.strip()]
    return max(1, len(clauses))


def _check_legacy(story: dict, contract: Contract) -> dict:
    """Does the story fit the length, the structure, and the rhythm it declared?"""
    beats = story.get("beats", [])
    want = int(contract.get("duration_seconds", 60))
    total = sum(int(b.get("seconds", 0)) for b in beats)
    elements = contract.elements()
    structure = contract.scenario_structure()
    acts = {a["id"]: a for a in structure.get("acts", [])}
    pacing = structure.get("pacing", {})

    problems = []
    warnings = []
    beat_budgets = []
    if total != want:
        problems.append(f"비트 합 {total}초, 계약 {want}초")

    # 막 순서와 누락
    seen_order = [b.get("purpose") for b in beats]
    unknown = [p for p in seen_order if p not in acts]
    if unknown:
        problems.append(f"선언되지 않은 막: {sorted(set(unknown))}. 있는 것 {list(acts)}")
    missing = [a for a in acts if a not in seen_order]
    if missing:
        problems.append(f"쓰이지 않은 막: {missing}")
    known = [p for p in seen_order if p in acts]
    expected = [a for a in acts if a in known]
    if known and [a for a in dict.fromkeys(known)] != expected:
        problems.append(f"막 순서가 어긋났다: {list(dict.fromkeys(known))} 대 {expected}")

    # 막별 비중과 비트 길이 범위
    for act_id, rules in acts.items():
        mine = [b for b in beats if b.get("purpose") == act_id]
        if not mine:
            continue
        share = sum(int(b.get("seconds", 0)) for b in mine) / max(total, 1)
        target = float(rules.get("share", 0))
        if target and abs(share - target) > SHARE_TOLERANCE:
            problems.append(f"{act_id}: 비중 {share:.0%}, 계약 {target:.0%}")
        low, high = rules.get("beat_seconds", [3, 10])
        for beat in mine:
            length = int(beat.get("seconds", 0))
            if not low <= length <= high:
                problems.append(f"{beat.get('id','?')}: {length}초. {act_id} 는 {low}-{high}초")

    # 리듬. 같은 속도로 끝까지 가면 관객이 딴생각을 시작한다
    lengths = [int(b.get("seconds", 0)) for b in beats]
    if pacing.get("require_variation") and lengths:
        distinct = len(set(lengths))
        want_distinct = int(pacing.get("min_distinct_lengths", 3))
        if distinct < want_distinct:
            problems.append(f"길이가 {distinct}종뿐이다. {want_distinct}종 이상")
        ratio = max(lengths) / max(min(lengths), 1)
        want_ratio = float(pacing.get("min_ratio", 1.5))
        if ratio < want_ratio:
            problems.append(f"최장 대 최단 {ratio:.2f}배. {want_ratio}배 이상")

    # 길이를 정당화했는가. 분량이 안 맞으면 모델이 남는 시간을 지어낸다
    unjustified = [b.get("id", "?") for b in beats if not (b.get("why_this_long") or "").strip()]
    if unjustified:
        problems.append(f"why_this_long 이 빈 비트: {unjustified}")

    for beat in beats:
        bid = beat.get("id", "?")
        where_value = beat.get("where_subject_id", beat.get("where"))
        for field, value, kinds in (("where_subject_id", where_value, {"setting"}),
                                    ("who", beat.get("who"), {"character"}),
                                    ("objects", beat.get("objects"), {"subject"})):
            names = [value] if isinstance(value, str) else list(value or [])
            for name in names:
                if name not in elements:
                    problems.append(f"{bid}.{field}: 선언되지 않은 요소 {name!r}")
                elif elements[name].get("kind") not in kinds:
                    problems.append(
                        f"{bid}.{field}: {name} 은 {elements[name].get('kind')} 다")

    used = {n for b in beats for n in
            ([b.get("where_subject_id", b.get("where"))]
             if isinstance(b.get("where_subject_id", b.get("where")), str)
             else list(b.get("where_subject_id", b.get("where")) or []))
            + list(b.get("who") or []) + list(b.get("objects") or [])}
    unused = sorted(set(elements) - used)
    if unused:
        problems.append(f"정의했는데 한 컷에도 안 나오는 요소: {unused}")

    graph = contract.spatial_graph
    nodes = {n.get("id"): n for n in graph.get("nodes", []) if isinstance(n, dict)}
    edges = {(e.get("from"), e.get("to")) for e in graph.get("edges", [])}
    previous_place = None
    all_visible_cast = []
    for beat in beats:
        bid = beat.get("id", "?")
        length = float(beat.get("seconds", 0) or 0)
        speech = _speech_seconds(beat)
        action_units = _action_units(beat)
        action_seconds = round(action_units * 1.15, 2)
        breathing = 0.5 if speech else 0.25
        place = beat.get("sublocation_id")
        transition = 0.75 if previous_place and place and place != previous_place else 0.0
        required = round(speech + action_seconds + breathing + transition, 2)
        beat_budgets.append({"beat_id": bid, "speech_duration": speech,
                             "action_units": action_units,
                             "action_time_budget": action_seconds,
                             "breathing_allowance": breathing,
                             "transition_allowance": transition,
                             "required_seconds": required,
                             "allocated_seconds": length})
        if required > length:
            warnings.append({"code": "beat-time-overflow", "beat_id": bid,
                             "message": f"추정 필요 {required:.2f}초가 배정 {length:.2f}초를 넘는다"})
        if action_units > max(2, int(length // 2)):
            warnings.append({"code": "action-overcrowded", "beat_id": bid,
                             "message": f"가시적 행동 단위 {action_units}개가 {length:g}초에 과밀하다"})
        if not beat.get("primary_action") or not beat.get("primary_visible_change"):
            warnings.append({"code": "atomic-fields-missing", "beat_id": bid,
                             "message": "primary_action/primary_visible_change 재구조화 필요"})
        if not place:
            warnings.append({"code": "sublocation-missing", "beat_id": bid,
                             "message": "sublocation_id가 없어 공간 연속성을 검증할 수 없다"})
        elif place not in nodes:
            warnings.append({"code": "sublocation-unknown", "beat_id": bid,
                             "message": f"계약 spatial graph에 {place!r}가 없다"})
        if previous_place and place and previous_place != place:
            if (previous_place, place) not in edges and (place, previous_place) not in edges:
                warnings.append({"code": "spatial-edge-missing", "beat_id": bid,
                                 "message": f"{previous_place}->{place} 연결이 정의되지 않았다"})
            if not beat.get("transition_requirement"):
                warnings.append({"code": "transition-missing", "beat_id": bid,
                                 "message": "장소 이동의 서사 전환 요구가 없다"})
        previous_place = place or previous_place
        focus = beat.get("visual_focus")
        all_visible_cast.append(tuple(sorted(focus if isinstance(focus, list)
                                             else beat.get("who") or [])))
        if beat.get("who") and not beat.get("cast_presence"):
            warnings.append({"code": "cast-presence-role-missing", "beat_id": bid,
                             "message": "등장 인물의 actor/available 상태가 분리되지 않았다"})
        if beat.get("objects") and not beat.get("object_roles"):
            warnings.append({"code": "object-visibility-role-missing", "beat_id": bid,
                             "message": "사물의 required_visible/available/interacted_with 역할이 없다"})
        for entry in beat.get("cast_presence") or []:
            sid = entry.get("subject_id") if isinstance(entry, dict) else None
            if sid not in elements or elements.get(sid, {}).get("kind") != "character":
                warnings.append({"code": "cast-presence-invalid", "beat_id": bid,
                                 "message": f"cast_presence 요소 {sid!r} 오류"})
        for entry in beat.get("object_roles") or []:
            sid = entry.get("subject_id") if isinstance(entry, dict) else None
            role = entry.get("role") if isinstance(entry, dict) else None
            if sid not in elements or elements.get(sid, {}).get("kind") != "subject" \
                    or role not in {"required_visible", "available", "interacted_with"}:
                warnings.append({"code": "object-role-invalid", "beat_id": bid,
                                 "message": f"object_roles 요소/역할 {sid!r}/{role!r} 오류"})
        for sub_beat in beat.get("sub_beats") or []:
            required_sub = {"id", "actor_subject_id", "action", "result_state", "split_after"}
            if not isinstance(sub_beat, dict) or required_sub - set(sub_beat):
                warnings.append({"code": "sub-beat-contract-incomplete", "beat_id": bid,
                                 "message": "sub_beat에 id/actor/action/result_state/split_after가 모두 필요하다"})
        interacted = [entry for entry in beat.get("object_roles") or []
                      if isinstance(entry, dict) and entry.get("role") == "interacted_with"]
        interactions = beat.get("interaction_contracts") or []
        if interacted and not interactions:
            warnings.append({"code": "interaction-contract-missing", "beat_id": bid,
                             "message": "도구·대상 part, 결과 상태와 고정부가 없어 접촉 동작을 설계할 수 없다"})
        required_interaction = {
            "sub_beat_id", "actor_subject_id", "target_subject_id", "target_part_id",
            "result_state", "fixed_part_ids", "moving_part_ids",
        }
        for interaction in interactions:
            if (not isinstance(interaction, dict)
                    or required_interaction - set(interaction)
                    or not interaction.get("fixed_part_ids")
                    or not interaction.get("moving_part_ids")):
                warnings.append({"code": "interaction-contract-incomplete", "beat_id": bid,
                                 "message": (
                                     "interaction contract의 actor/target/result/fixed/moving parts가 "
                                     "불완전하다"
                                 )})
                continue
            interaction_type = interaction.get("interaction_type")
            if not interaction_type:
                interaction_type = "mechanical_tool_contact"
                warnings.append({"code": "interaction-type-missing", "beat_id": bid,
                                 "message": "interaction_type이 없어 legacy mechanical로 해석한다"})
            if interaction_type not in {
                "mechanical_tool_contact", "articulated_mechanism", "assembly_sequence"
            }:
                warnings.append({"code": "interaction-type-invalid", "beat_id": bid,
                                 "message": f"지원하지 않는 interaction_type: {interaction_type}"})
                continue
            if interaction_type == "articulated_mechanism":
                kinematic = interaction.get("kinematic_contract") or {}
                missing_kinematic = [field for field in (
                    "motion_type", "axis_or_track_part_id", "start_state", "mid_state", "end_state"
                ) if kinematic.get(field) in (None, "", [])]
                if missing_kinematic:
                    warnings.append({
                        "code": "interaction-kinematic-contract-invalid", "beat_id": bid,
                        "message": f"관절 기구의 축/트랙과 시작·중간·완료 상태가 없다: {missing_kinematic}",
                    })
                continue
            if interaction_type == "assembly_sequence":
                interface = interaction.get("interface_contract") or {}
                missing_interface = [field for field in (
                    "moving_part_id", "receiving_part_id", "alignment_relation",
                    "engagement_motion", "start_state", "mid_state", "end_state"
                ) if interface.get(field) in (None, "", [])]
                if missing_interface:
                    warnings.append({
                        "code": "interaction-interface-contract-invalid", "beat_id": bid,
                        "message": f"조립 인터페이스와 순서 상태가 없다: {missing_interface}",
                    })
                continue
            if not interaction.get("tool_subject_id") or not interaction.get("tool_part_id"):
                warnings.append({"code": "interaction-tool-contract-incomplete", "beat_id": bid,
                                 "message": "mechanical_tool_contact의 tool subject/part가 없다"})
                continue
            fit = interaction.get("fit_contract") or {}
            capacity = fit.get("tool_capacity_mm")
            extent = fit.get("target_extent_mm")
            minimum = fit.get("minimum_capacity_ratio")
            numeric_fit = all(isinstance(value, (int, float)) and not isinstance(value, bool)
                              for value in (capacity, extent, minimum))
            if (not fit.get("tool_capacity_part_id")
                    or not fit.get("target_extent_part_id")
                    or not numeric_fit or extent <= 0 or capacity / extent < minimum
                    or minimum < 1.15):
                warnings.append({"code": "interaction-fit-contract-invalid", "beat_id": bid,
                                 "message": "도구 용량/대상 치수와 최소 1.15 용량비가 확인되지 않았다"})
            axis = interaction.get("axis_contract") or {}
            target_angle = axis.get("target_angle_deg")
            max_error = axis.get("max_error_deg")
            if (not axis.get("tool_action_plane_part_id")
                    or not axis.get("target_axis_part_id")
                    or axis.get("relation") != "perpendicular"
                    or not isinstance(target_angle, (int, float))
                    or isinstance(target_angle, bool)
                    or abs(float(target_angle) - 90.0) > 0.001
                    or not isinstance(max_error, (int, float))
                    or isinstance(max_error, bool)
                    or not 0 < float(max_error) <= 5.0):
                warnings.append({"code": "interaction-axis-contract-invalid", "beat_id": bid,
                                 "message": "도구 작용면–대상 축 90도와 최대 5도 오차가 확인되지 않았다"})
            projection = interaction.get("projection_contract") or {}
            if (projection.get("mechanical_truth_over_tool_hero_view") is not True
                    or projection.get("hero_three_quarter_tool_view_forbidden") is not True):
                warnings.append({"code": "interaction-projection-contract-invalid", "beat_id": bid,
                                 "message": "기계적 정렬보다 도구 과시 사선 구도를 우선할 위험이 있다"})
        dialogue = beat.get("dialogue") or {}
        mode = dialogue.get("mode")
        if mode == "spoken":
            warnings.append({"code": "legacy-dialogue-mode", "beat_id": bid,
                             "message": "spoken을 onscreen_spoken 또는 voiceover로 구분해야 한다"})
        if mode == "onscreen_spoken" and (
                not dialogue.get("language") or dialogue.get("lip_sync_required") is not True):
            warnings.append({"code": "onscreen-dialogue-contract-incomplete", "beat_id": bid,
                             "message": "화면 발화는 language와 lip_sync_required=true가 필요하다"})
        if mode == "voiceover" and dialogue.get("lip_sync_required") is not False:
            warnings.append({"code": "voiceover-lipsync-invalid", "beat_id": bid,
                             "message": "voiceover는 lip_sync_required=false여야 한다"})
        if mode in {"none", "silent"} and str(dialogue.get("text", "")).strip():
            warnings.append({"code": "silent-dialogue-has-text", "beat_id": bid,
                             "message": "none/silent dialogue에는 text가 없어야 한다"})
        spoken_text = str((beat.get("dialogue") or {}).get("text", beat.get("line", "")))
        if re.search(r"\d", spoken_text) and not beat.get("numeric_claims"):
            warnings.append({"code": "numeric-claim-origin-missing", "beat_id": bid,
                             "message": "발화 수치가 fictional design spec인지 외부 사실인지 기록되지 않았다"})

    if len(beats) > 2 and all_visible_cast and len(set(all_visible_cast)) == 1 \
            and all_visible_cast[0]:
        warnings.append({"code": "visual-focus-monotony", "beat_id": None,
                         "message": "모든 비트의 visual focus가 같아 비진행자/삽입 커버리지를 검토한다"})

    if beats:
        first = beats[0]
        hook_text = " ".join(str(first.get(k, "")) for k in
                             ("primary_action", "primary_visible_change", "what_happens", "line"))
        hook_signal = first.get("hook_signal")
        substantive = bool(hook_signal) or bool(re.search(
            r"[?!?]|열리|나타나|발견|움직|흐르|떨어|멈추|시작|공개|보여", hook_text))
        if not substantive:
            warnings.append({"code": "weak-hook-substance", "beat_id": first.get("id"),
                             "message": "purpose 라벨 외에 첫 장면의 사건·질문·움직임 근거가 약하다"})

    return {
        "structure": structure.get("structure_id", "custom"),
        "beats": len(beats), "designed_seconds": want, "total_seconds": total,
        "beat_lengths": lengths,
        "distinct_lengths": len(set(lengths)),
        "longest_over_shortest": round(max(lengths) / max(min(lengths), 1), 2) if lengths else 0,
        "acts_used": list(dict.fromkeys(known)),
        "unused_elements": unused,
        "beat_budgets": beat_budgets,
        "warnings": warnings,
        "problems": problems, "ok": not problems,
    }


def _check_scene_design(story: dict, contract: Contract) -> dict:
    scenes = iter_scenes(story)
    elements = contract.elements()
    acts = {item["id"] for item in contract.acts()}
    problems: list[str] = []
    warnings: list[dict] = []
    scene_ids: set[str] = set()
    event_ids: set[str] = set()
    new_requirements: dict[str, dict] = {}
    act_order: list[str] = []
    spatial_nodes = {str(item.get("id")) for item in contract.spatial_graph.get("nodes") or []
                     if isinstance(item, dict) and item.get("id")}

    if story.get("schema_version") != SCENARIO_SCHEMA:
        problems.append(f"schema_version은 {SCENARIO_SCHEMA} 이어야 한다")
    if not scenes:
        problems.append("sequence 안에 scene이 없다")

    # Recurring new assets may be declared in one scene and used in another.
    # Collect the project-local namespace before validating scene references.
    for scene in scenes:
        for item in scene.get("production_requirements") or []:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            rid = str(item["id"])
            if rid in new_requirements and new_requirements[rid] != item:
                problems.append(f"{rid}: 서로 다른 새 요소 정의가 중복된다")
            new_requirements[rid] = item

    required_scene_fields = {
        "id", "act_id", "scene_intent", "scene_role", "pov_owner",
        "dramatic_question", "entry_state", "exit_state", "events",
        "estimated_edit_range_seconds", "pacing", "temporal_intent",
    }
    for scene in scenes:
        sid = str(scene.get("id") or "?")
        missing = sorted(required_scene_fields - set(scene))
        if missing:
            problems.append(f"{sid}: scene 필드 누락 {missing}")
        if sid in scene_ids:
            problems.append(f"scene id 중복 {sid}")
        scene_ids.add(sid)
        act_id = str(scene.get("act_id") or scene.get("purpose") or "")
        if act_id:
            act_order.append(act_id)
        if acts and act_id not in acts:
            problems.append(f"{sid}: 선언되지 않은 act {act_id!r}")

        low, high = _scene_range(scene)
        if low <= 0 or high < low:
            problems.append(f"{sid}: estimated_edit_range_seconds가 유효하지 않다")
        pacing = scene.get("pacing") or {}
        if not str(pacing.get("reason") or "").strip():
            problems.append(f"{sid}: 사건량과 리듬을 설명하는 pacing.reason이 없다")
        temporal = scene.get("temporal_intent") or {}
        if not temporal.get("candidate_modes") or not temporal.get("dramatic_reason"):
            problems.append(f"{sid}: temporal_intent 후보와 극적 이유가 없다")

        requirements = scene.get("production_requirements") or []
        local_new: set[str] = set()
        for item in requirements:
            rid = str((item or {}).get("id") or "")
            if not rid.startswith("NEW-"):
                problems.append(f"{sid}: 새 production requirement id는 NEW-로 시작해야 한다: {rid!r}")
                continue
            local_new.add(rid)
            asset_class = item.get("asset_class")
            if asset_class not in REFERENCE_CLASSES:
                problems.append(f"{rid}: asset_class 오류 {asset_class!r}")
            policy = item.get("reference_policy")
            expected = {
                "recurring_canonical_asset": "full_sheet",
                "scene_only_hero_prop": "scene_reference",
                "interaction_target": "action_reference",
                "sublocation_detail": "location_reference",
                "background_dressing": "prompt_only",
                "offscreen_only": "none",
            }.get(asset_class)
            if expected and policy != expected:
                problems.append(f"{rid}: {asset_class} reference_policy는 {expected}여야 한다")

        for event in scene.get("events") or []:
            eid = str((event or {}).get("id") or "")
            if not eid or eid in event_ids:
                problems.append(f"{sid}: event id 누락 또는 중복 {eid!r}")
            event_ids.add(eid)
            for field in ("action", "visible_change", "result_state"):
                if not str((event or {}).get(field) or "").strip():
                    problems.append(f"{eid or sid}: {field}가 없다")

        referenced = set()
        where_value = scene.get("where_subject_id")
        if isinstance(where_value, str) and where_value:
            referenced.add(where_value)
        sublocation = scene.get("sublocation_id")
        if (isinstance(sublocation, str) and sublocation and sublocation not in spatial_nodes
                and sublocation not in new_requirements):
            warnings.append({"code": "sublocation-reference-debt", "scene_id": sid,
                             "message": f"{sublocation!r}는 기존 spatial node가 아니므로 새 장소 reference 결속을 확인한다"})
        for entry in (scene.get("cast_presence") or []) + (scene.get("object_roles") or []):
            if isinstance(entry, dict) and entry.get("subject_id"):
                referenced.add(str(entry["subject_id"]))
        referenced.update(str(value) for value in scene.get("visual_focus") or [])
        for event in scene.get("events") or []:
            for field in ("actor_subject_id", "target_subject_id"):
                value = (event or {}).get(field)
                if value:
                    referenced.add(str(value))
        undeclared = sorted(value for value in referenced
                            if value not in elements and value not in new_requirements
                            and value not in {"audience", "objective", "viewer"})
        if undeclared:
            problems.append(f"{sid}: 기존 정의도 production requirement도 아닌 요소 {undeclared}")

        for requirement in requirements:
            declared_events = set(requirement.get("used_by_event_ids") or [])
            unknown_events = declared_events - event_ids
            if unknown_events:
                warnings.append({"code": "reference-debt-event-unresolved", "scene_id": sid,
                                 "message": f"{requirement.get('id')}의 event 결속 확인 필요: {sorted(unknown_events)}"})

    observed_acts = list(dict.fromkeys(act_order))
    expected_acts = [item["id"] for item in contract.acts()]
    if expected_acts and observed_acts != expected_acts:
        problems.append(f"act 순서/누락 오류: {observed_acts} 대 {expected_acts}")

    estimated = _scenario_estimated_range(story)
    runtime_low, runtime_high = _runtime_bounds(contract)
    if runtime_low is not None and (estimated[1] < runtime_low or estimated[0] > runtime_high):
        warnings.append({
            "code": "scene-range-misses-runtime", "scene_id": None,
            "message": (
                f"신 추정 범위 {estimated[0]:g}-{estimated[1]:g}초가 Stage 1 runtime "
                f"{runtime_low:g}-{runtime_high:g}초를 포함하지 않는다. 정확한 배분은 Stage 4가 결정한다"
            ),
        })

    return {
        "schema_version": "narrative-design-check.v3",
        "structure": "sequence_scene_event",
        "sequences": len(story.get("sequences") or []),
        "scenes": len(scenes),
        "events": len(event_ids),
        "runtime_contract": contract.runtime_contract,
        "estimated_edit_range_seconds": estimated,
        "reference_debt_count": len(new_requirements),
        "reference_debt": list(new_requirements.values()),
        "warnings": warnings,
        "problems": problems,
        "ok": not problems,
    }


def check(story: dict, contract: Contract) -> dict:
    """Validate current scene design or audit a preserved legacy beat scenario."""
    if story.get("sequences") or story.get("schema_version") == SCENARIO_SCHEMA:
        return _check_scene_design(story, contract)
    report = _check_legacy(story, contract)
    report["schema_version"] = "legacy-scenario-check.v2"
    report["migration_required"] = True
    report["warnings"].append({
        "code": "legacy-beat-timing-model", "beat_id": None,
        "message": "기존 beat/seconds 산출물이다. 새 생성은 sequence/scene/event와 Stage 4 timing을 사용한다",
    })
    return report


def run(attempt: Path, model: str | None = None, force: bool = False) -> dict:
    contract = load_contract(attempt)
    target = stage_dir(attempt, contract) / "output" / "scenario.json"
    existing = json.loads(target.read_text(encoding="utf-8")) if target.exists() else None
    existing_report = check(existing, contract) if existing else None
    should_generate = (
        force or existing is None
        or existing.get("schema_version") != SCENARIO_SCHEMA
        or bool((existing_report or {}).get("problems"))
    )
    harness_attempts = []
    if should_generate:
        if existing is not None and not force:
            archive = (stage_dir(attempt, contract) / "rejected" /
                       f"scenario-before-auto-repair-{datetime.now().strftime('%Y%m%dT%H%M%S')}.json")
            archive.parent.mkdir(parents=True, exist_ok=True)
            archive.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        correction = ""
        story = None
        report = None
        for number in range(1, MAX_GENERATION_ATTEMPTS + 1):
            try:
                candidate = write(attempt, contract, model, number, correction)
                effective_prompt = str(candidate.pop("_harness_effective_prompt"))
                candidate_report = check(candidate, contract)
                failed = list(candidate_report.get("problems") or [])
                decision = "pass" if not failed else "fail"
                feedback = "\n".join(failed)
            except ScenarioError:
                raise
            except Exception as error:  # model/JSON transport failures are retryable here
                candidate = None
                candidate_report = None
                effective_prompt = retry_prompt(
                    "scenario generation request", number, correction)
                failed = [f"generation error: {type(error).__name__}: {error}"]
                decision = "fail"
                feedback = failed[0]
            harness_attempts.append(attempt_record(
                number, effective_prompt, decision, feedback, failed))
            if decision == "pass":
                story, report = candidate, candidate_report
                break
            correction = (
                "Repair every validator finding below while preserving the complete scenario contract:\n" +
                "\n".join(f"- {item}" for item in failed))
        if story is None or report is None:
            raise ScenarioError(
                f"scenario가 {MAX_GENERATION_ATTEMPTS}회 변주·검증 뒤에도 통과하지 못했다: "
                + "; ".join(harness_attempts[-1]["failed_criteria"]))
        story["generation_harness"] = {
            **harness_contract(
                "stage03_scenario_design", harness_attempts[0]["effective_prompt_sha256"],
                ("scenario semantic validator has no problems",),
                exhaustion_policy="report_attempt_10_with_unresolved_findings",
                execution_mode=load_execution_mode(attempt)["mode"]),
            "attempts": harness_attempts,
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(story, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        story, report = existing, existing_report
    semantic = stage_dir(attempt, contract).parent / contract.stage_for("sheet", "02-sheet") / "qa" / "semantic-review.json"
    if semantic.exists():
        sheet_state = json.loads(semantic.read_text(encoding="utf-8"))
        if not sheet_state.get("reference_ready"):
            report["warnings"].append({"code": "sheet-reference-not-ready", "beat_id": None,
                                       "message": "시트 semantic review가 끝나지 않아 전체 보드를 안전한 참조로 간주할 수 없다"})
    receipt = stage_dir(attempt, contract) / "receipt.json"
    receipt.write_text(json.dumps({
        "receipt_id": f"{contract.data['contract_id']}-SCENARIO",
        "contract": contract.receipt_block(stage_name(contract)),
        "written_by": story.get("written_by"),
        "boards_seen": story.get("boards_seen", []),
        "scenario_sha256": hashlib.sha256(
            json.dumps(story, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16],
        "check": report,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"path": str(target), "logline": story.get("logline"),
            "lesson": story.get("lesson"), **report}


def audit_existing(attempt: Path) -> dict:
    """Validate a historical scenario without rewriting its scenario or receipt."""
    contract = load_contract(attempt)
    target = stage_dir(attempt, contract) / "output" / "scenario.json"
    if not target.exists():
        raise ScenarioError(f"기존 scenario가 없다: {target}")
    story = json.loads(target.read_text(encoding="utf-8"))
    report = check(story, contract)
    semantic = attempt / contract.stage_for("sheet", "02-sheet") / "qa" / "semantic-review.json"
    if semantic.exists() and not json.loads(semantic.read_text(encoding="utf-8")).get("reference_ready"):
        report["warnings"].append({"code": "sheet-reference-not-ready", "beat_id": None,
                                   "message": "시트 semantic review가 완료되지 않았다"})
    out = stage_dir(attempt, contract) / "qa" / "semantic-check.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "schema_version": "scenario-semantic-check.v1",
        "checked_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "contract": contract.receipt_block(stage_name(contract)),
        "upstream_state": read_premise_state(attempt, contract),
        "scenario": str(target.relative_to(attempt)),
        "does_not_rewrite_original_receipt": True,
        **report,
    }
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"path": str(out), **report}


def main() -> int:
    parser = argparse.ArgumentParser(description="정의와 시트를 보고 시나리오를 쓴다")
    parser.add_argument("attempt", type=Path)
    parser.add_argument("--model")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--audit-only", action="store_true",
                        help="기존 시나리오와 영수증을 바꾸지 않고 semantic QA만 쓴다")
    args = parser.parse_args()

    try:
        result = audit_existing(args.attempt) if args.audit_only else run(
            args.attempt, args.model, args.force)
    except (ScenarioError, ContractError) as error:
        print(json.dumps({"ok": False, "problem": str(error)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
