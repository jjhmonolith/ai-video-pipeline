"""04-shot-design: direct scenes, then compile executable H3 shot contracts.

The scenario owns *what happens*.  This stage owns the smallest photographic
unit that can show it without asking H3 to invent the missing time: duration,
start state, semantic end target, performance, one camera instruction, H3
conditioning route, and the measurements used to select a candidate.

The motion JSON in a shot card is deliberately not described as a native H3
trajectory input.  H3 accepts text plus image anchors.  Production uses a
first-frame anchor only; the end state remains a QA target, not a generated
plate or H3 last frame.  Semantic tracks and a change budget are an authoring/QA
contract: stage 05 turns selected states into plates, stage 06 turns the route
into H3 inputs, and review measures the result against the same contract.  That
distinction prevents a plausible-looking JSON file from pretending to control
the model directly.

The creative layer is authored before the production compiler.  It chooses
scene treatment, blocking, setups, shots, edit contribution, temporal mode and
execution method.  The deterministic layer only checks that decision and maps
it to valid H3 frames, handles, trim/retime notes, prompts and QA contracts.  It
must never recover a missing artistic duration with a seconds-per-action rule.

Stage 04 also decides whether the start plate and the canonical stage-02 sheets
are sufficient to explain the action.  A hard-to-infer interaction receives a
supplemental interaction-manual specification: multiple truthful views,
multiple observable states, a clean H3 reference board prompt, and a separate
annotated QA overlay plan.  Stage 05 renders and approves those assets; it does
not improvise their content.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .contract import Contract, ContractError, load as load_contract
from .h3_runtime import PROFILE_ID, snap_length
from .lifecycle import read_direction_impact, read_premise_state
from .generation_harness import (
    HARNESS_SCHEMA,
    MAX_GENERATION_ATTEMPTS,
    VARIATION_STRATEGIES,
    attempt_record,
    harness_contract,
    retry_prompt,
    variation_strategy,
)
from .execution_mode import FAST_TRACK_MODE, load_execution_mode
from .research import DEFAULT_MODEL, _client
from .scenario import SCENARIO_SCHEMA, iter_scenes
from .shot_grammar_gate import (
    ANGLES,
    CAMERA_PARTS,
    COMPOSITIONS,
    MOVEMENTS,
    SIZES,
)

STAGE_ROLE = "shot_design"
STAGE_FALLBACK = "04-shot-design"
SCHEMA_VERSION = "shot-design.v2"
LEGACY_SCHEMA_VERSION = "shot-design.v1"
H3_ROUTES = {"i2v", "fl2va", "guided_fl2va", "self_mined_fl2va"}
CAMERA_POLICIES = {
    "locked", "natural", "soft_follow", "directed",
    "prompt_only_small", "prompt_only_free",  # legacy cards
}
MOTION_CLASSES = {"rigid", "articulated", "deformable", "state_change", "ambient"}
EXACT_ROUTES = {"fl2va", "guided_fl2va", "self_mined_fl2va"}
TEMPORAL_MODES = {
    "real_time", "slow_motion", "extreme_slow_motion", "speed_ramp",
    "time_freeze", "bullet_time_orbit", "timelapse", "hyperlapse",
    "compressed_montage", "elliptical_time", "reverse_motion",
    "loop_or_repetition", "subjective_time", "simultaneous_split_time",
}
TEMPORAL_EXECUTION_METHODS = {"model_native", "post_retime", "hybrid"}

DIRECTOR_RULES = """
You are the director, cinematographer and picture editor for Stage 04. The Stage 03
input is a sequence/scene/event narrative design, not a shot list. Work in this order:
1) write a directorial treatment for every scene: intent, POV, blocking, coverage logic;
2) create setups, then shots; 3) assign exact editorial timing and temporal treatment.

Rules:
- A setup is one camera/light configuration. A shot is one editorial view. A take is a
  generation attempt of that same shot. Never use C01/C02 as different angles.
- Decide durations by dramatic purpose, performance, camera behavior and temporal design.
  Never use a fixed seconds-per-action formula.
- `edit_target_seconds` is the planned final contribution. `included_in_timeline=false`
  marks coverage generated as an alternate and excludes it from the planned runtime.
- Generation may be longer than edit contribution. Declare head/tail handles and a
  temporal mode. Slow motion, freeze, bullet-time orbit, speed ramps, time lapse and
  subjective time have separate subject/world/camera time domains.
- `execution_method` is model_native, post_retime or hybrid. Do not silently replace an
  unsupported idea: declare capability_debt with the exact missing capability.
- Camera has exactly one primary movement, plus speed, framing behavior and end condition.
- Two visible people require a two-shot or a clearly named over-the-shoulder composition.
- New Stage-03 production requirements remain bound to their scene and shot. Classify
  which reference must be fulfilled before plates.
- Return JSON only.

Schema:
{"schema_version":"directorial-plan.v2","scenes":[{"scene_id":"SC01",
"treatment":{"intent":"","pov":"","blocking":"","coverage_logic":""},
"setups":[{"setup_id":"SU01","lighting_continuity":"","shots":[{
"shot_id":"S01","event_ids":["E01"],"purpose":"","included_in_timeline":true,
"visible_cast_ids":[],"visible_object_ids":[],
"camera":{"movement":"스태틱 샷","speed":"","framing":"","end":"","angle":"아이 레벨"},
"frame_size":"미디엄 샷","composition":"싱글",
"performance":{"action_phases":[{"phase":"anticipation","description":"","normalized_range":[0,0.2]},
{"phase":"action","description":"","normalized_range":[0.2,0.8]},
{"phase":"settle","description":"","normalized_range":[0.8,1]}]},
"timing":{"edit_target_seconds":4.5,"tolerance_seconds":0.4,
"head_handle_seconds":0.4,"tail_handle_seconds":0.6,"temporal_mode":"real_time",
"dramatic_reason":"","execution_method":"model_native","source_playback_rate":1.0,
"time_domains":{"subject":"real_time","world":"real_time","camera":"real_time"},
"speed_curve":[{"at":0,"rate":1},{"at":1,"rate":1}],"camera_time":"continuous",
"capability_debt":[]},"reference_requirement_ids":[]}]}]}]}
"""

_STATE_CHANGE = re.compile(
    r"열|닫|돌리|멎|멈|흐름|감|조이|풀|닦|꺼내|놓|들|가리키|손짓|시선|미소|"
    r"통과|건너|걷|이동|올라|내려|나타나|공개|바라"
)
_MULTI_ACTION = re.compile(
    r"[,.。]|(?:하고|하며|으며|면서|이어|다가|차례로)|(?:고[,，]?\s+)|(?:자\s|뒤\s)"
)
_AMBIENT = re.compile(r"흔들|반짝|물결|바람|빛|호흡|깜빡|흐르")
_RIGID = re.compile(r"밸브|문|패널|공구|가방|렌치|테이프|관|파이프|손전등")
_DEFORMABLE = re.compile(r"물|천|머리|옷|연기|커튼|식재")
_TRANSIT = re.compile(
    r"걷|걸어|걸으|걸음|보행|이동|통과|건너|문턱.{0,12}넘|경계.{0,12}넘|"
    r"올라오|내려오|올라가|내려가|들어가|들어오|들어와|나가|"
    r"향해\s*가|따라\s*이동"
)
_MECHANICAL_MANUAL = re.compile(
    r"렌치|플라이어|니퍼|드라이버|스패너|토크|피팅|연결부|"
    r"나사부|나사\s*연결"
)
_PROFESSIONAL_TOOL = re.compile(r"렌치|플라이어|니퍼|드라이버|스패너|토크")
_ASSEMBLY_MANUAL = re.compile(
    r"PTFE|테이프.*(?:감|두르)|맞물|조립|분해|끌우|삽입|체결|결합"
)
_MECHANICAL_ACTUATION = re.compile(
    r"맞물|조립|분해|풀|푼|푼|조이|조여|조임|감고|감아|물리|끌어"
)
_ARTICULATED_MANUAL = re.compile(
    r"밸브|패널|힌지|레일|레버|기어|잠금|"
    r"열리|닫히|펼쳐|접히|회전|슬라이드"
)
_ARTICULATED_ACTUATION = re.compile(
    r"열어|열고|열자|열리|연다|닫아|닫고|닫자|닫히|닫는|돌려|돌리|회전|"
    r"슬라이드|펼쳐|펼친|접히|접는|잠그|잠가|잠긴"
)


class ShotDesignError(RuntimeError):
    """Stage 04 cannot safely create or validate shot cards."""


def stage_name(contract: Contract) -> str:
    return contract.stage_for(STAGE_ROLE, STAGE_FALLBACK)


def stage_dir(attempt: Path, contract: Contract) -> Path:
    return attempt / stage_name(contract)


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _sha(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _list(value: Any) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?。])\s+", text) if part.strip()]


def _action_units(beat: dict) -> list[str]:
    explicit = beat.get("sub_beats") or []
    if explicit:
        return [str(item.get("action", "")).strip() for item in explicit
                if isinstance(item, dict) and str(item.get("action", "")).strip()]
    text = str(beat.get("what_happens", ""))
    sentences = _sentences(text)
    if not sentences:
        return [str(beat.get("primary_action", "행동을 수행한다"))]
    return sentences


def _split_beat(beat: dict) -> list[dict]:
    """Split an overloaded beat without changing its story time.

    Scenario beats are narrative units, not necessarily safe H3 generations.
    Stage 04 may therefore photograph one beat as several shots.  Around three
    seconds per visible action is the target; a short beat remains one shot.
    """
    units = _action_units(beat)
    text = str(beat.get("what_happens", ""))
    explicit = bool(beat.get("sub_beats"))
    sentences = _sentences(text)
    clause_count = min(len([part for part in _MULTI_ACTION.split(text) if part.strip()]), 5)
    if explicit:
        atomization_source = "stage03_sub_beats"
    elif len(sentences) > 1:
        atomization_source = "sentence_boundaries"
    elif clause_count > 1:
        atomization_source = "unresolved_compound_sentence"
    else:
        atomization_source = "single_action"
    seconds = float(beat.get("seconds", 0))
    wanted = max(1, round(seconds / 3.0))
    count = min(len(units), wanted)
    if count <= 1:
        segment = dict(beat)
        segment["_stage04_atomization"] = {
            "source": atomization_source,
            "declared_units": max(len(units), clause_count),
            "segments_created": 1,
            # Stage 03's explicit sub-beat is the authoritative atomic action
            # contract.  Conjunctions in the explanatory prose often describe
            # invariants or the completed state, not extra actions.  Only
            # legacy beats without explicit sub-beats fall back to the prose
            # clause heuristic.
            "manual_segmentation_required": not explicit and clause_count > 1,
        }
        return [segment]

    grouped: list[list[str]] = [[] for _ in range(count)]
    for index, action in enumerate(units):
        bucket = min(count - 1, index * count // len(units))
        grouped[bucket].append(action)

    # Tenths keep the cards readable while the final segment absorbs rounding.
    base = int(seconds * 10) // count / 10
    durations = [base] * count
    durations[-1] = round(seconds - sum(durations[:-1]), 1)
    out = []
    explicit_records = [item for item in beat.get("sub_beats") or []
                        if isinstance(item, dict)]
    explicit_cursor = 0
    for index, (actions, duration) in enumerate(zip(grouped, durations), start=1):
        segment = dict(beat)
        action = ". ".join(actions).strip()
        if action and action[-1] not in ".!?":
            action += "."
        segment["seconds"] = duration
        segment["what_happens"] = action
        segment["primary_action"] = action
        segment["primary_visible_change"] = action
        if explicit_records:
            segment_records = [dict(item) for item in
                               explicit_records[explicit_cursor:explicit_cursor + len(actions)]]
            segment["sub_beats"] = segment_records
            explicit_cursor += len(actions)
            sub_ids = {item.get("id") for item in segment["sub_beats"]}
            segment["interaction_contracts"] = [
                dict(item) for item in beat.get("interaction_contracts") or []
                if isinstance(item, dict)
                and (not item.get("sub_beat_id") or item.get("sub_beat_id") in sub_ids)
            ]
            if len(segment_records) == 1:
                record = segment_records[0]
                for field in (
                    "camera_design", "supplemental_reference_requirement",
                    "visual_focus", "cast_presence", "object_roles", "who", "objects",
                    "has_host", "has_driver", "start_state_description",
                ):
                    if record.get(field) is not None:
                        segment[field] = record[field]
        else:
            segment["sub_beats"] = [{"action": item, "split_after": True}
                                    for item in actions]
        segment["beat_segment"] = {"index": index, "count": count,
                                   "parent_seconds": seconds}
        segment["_stage04_atomization"] = {
            "source": atomization_source,
            "declared_units": max(len(units), clause_count),
            "segments_created": count,
            "manual_segmentation_required": len(actions) > 1,
        }
        # Dialogue belongs to the edit/audio plan across the parent beat.  Do
        # not ask H3 to repeat it in every visual segment.
        if index > 1:
            segment["line"] = ""
            if segment.get("dialogue"):
                segment["dialogue"] = {
                    "mode": "none", "text": "", "language": None,
                    "lip_sync_required": False,
                }
        out.append(segment)
    return out


def _characters(beat: dict, contract: Contract) -> list[str]:
    values = [entry.get("subject_id") for entry in beat.get("cast_presence") or []
              if isinstance(entry, dict)]
    # Stage 03 may explicitly declare an empty visible cast for exterior
    # vehicle coverage even though the parent narrative beat has occupants.
    # In that case `who` is story presence, not photographic visibility.
    if "cast_presence" not in beat:
        values.extend(_list(beat.get("who")))
    return list(dict.fromkeys(v for v in values
                              if contract.elements().get(v, {}).get("kind") == "character"))


def _objects(beat: dict, contract: Contract) -> list[str]:
    values = [entry.get("subject_id") for entry in beat.get("object_roles") or []
              if isinstance(entry, dict)]
    values.extend(_list(beat.get("objects")))
    return list(dict.fromkeys(v for v in values
                              if contract.elements().get(v, {}).get("kind") == "subject"))


def _where(beat: dict) -> str:
    value = beat.get("where_subject_id", beat.get("where", ""))
    return value if isinstance(value, str) else (value[0] if value else "")


def _lighting_contract(definitions: dict[str, dict], where: str, beat: dict) -> dict:
    """Compile setting light into a world-space, shot-usable contract.

    Stage 01 owns the look. Stage 04 must propagate it explicitly instead of
    assuming that an image model will recover time of day and shadow behavior
    from a location board. Cameras may move, but the sun may not move with them.
    """
    setting = definitions.get(where) or {}
    declared = setting.get("lighting") or {}
    if isinstance(declared, str):
        declared = {"primary": declared}
    elif not isinstance(declared, dict):
        declared = {}
    text = str(beat.get("what_happens") or beat.get("primary_action") or "")
    requirement = beat.get("supplemental_reference_requirement") or {}
    architecture = setting.get("architecture")
    setting_text = " ".join(str(setting.get(key) or "") for key in (
        "concept", "topology", "architecture", "materials"))
    interior = (
        str(requirement.get("manual_type") or "") == "cabin_occupancy"
        or bool(re.search(r"실내|콕핏|운전석|조수석|대시보드", text))
    )
    architectural_interior = bool(architecture) or bool(re.search(
        r"penthouse|residence|interior|salon|kitchen|bedroom|gallery|suite|펜트하우스|주거|살롱|주방|침실",
        setting_text,
        re.IGNORECASE,
    ))
    space = "cabin" if interior else ("interior" if architectural_interior else "exterior")
    if space == "cabin":
        shadow_rules = [
            "sunlight enters through the physically correct windshield and side windows",
            "dashboard, helmet and belt shadows follow the same exterior sun direction",
            "use soft ambient skylight fill so both faces remain readable without a studio key-light look",
        ]
    elif space == "interior":
        shadow_rules = [
            "feet, furniture and architectural contact shadows remain attached to their surfaces",
            "concealed practical fixtures keep fixed positions, color and intensity across the shot",
            "glass reflections remain physically coherent and reveal no crew or lighting equipment",
        ]
    else:
        shadow_rules = [
            "subject and ground contact shadows remain physically attached",
            "shadow direction and softness remain consistent with the approved setting reference",
            "material highlights retain texture without clipped glare or crushed shade",
        ]
    return {
        "source_subject_id": where,
        "primary": str(declared.get("primary") or "match the approved setting reference"),
        "shadow": str(declared.get("shadow") or "physically coherent contact shadows"),
        "weather": str(declared.get("weather") or "match the approved setting reference"),
        "space": space,
        "world_space_rules": [
            "one fixed world-space lighting direction and color across the entire shot",
            "camera-relative relighting or key-side flipping is forbidden",
            "exposure may protect faces and material highlights but may not change light direction",
        ],
        "shot_shadow_rules": shadow_rules,
    }


def _lighting_prompt(contract: dict) -> str:
    return (
        f"primary={contract.get('primary')}; shadow={contract.get('shadow')}; "
        f"weather={contract.get('weather')}; space={contract.get('space')}; "
        + "; ".join(contract.get("world_space_rules") or [])
        + "; "
        + "; ".join(contract.get("shot_shadow_rules") or [])
    )


def _sublocation(beat: dict, contract: Contract) -> str:
    if beat.get("sublocation_id"):
        return str(beat["sublocation_id"])
    owner = _where(beat)
    nodes = [n.get("id") for n in contract.spatial_graph.get("nodes", [])
             if n.get("where_subject_id") == owner]
    # Historical 03 outputs did not carry sublocation_id.  Preserve that fact:
    # choosing the owner's only node is deterministic; choosing among several
    # is explicitly an unresolved design inference, not a fake continuity fact.
    return nodes[0] if len(nodes) == 1 else "unresolved"


def _all_clause_text(contract: Contract, stage: str, beat: dict,
                     chars: list[str]) -> tuple[list[str], str]:
    """Resolve conditional prompt clauses from the current scenario beat."""
    conditions = {
        flag: bool(beat[flag]) if flag in beat else (bool(chars) if flag == "has_host" else False)
        for flag in contract.condition_flags
    }
    records: list[dict] = []
    for kind in (None, "character" if chars else None):
        for record in contract.clauses_for(stage, conditions, subject_kind=kind):
            if record["id"] not in {item["id"] for item in records}:
                records.append(record)
    return [item["id"] for item in records], " ".join(item["text"] for item in records)


def reference_status(attempt: Path, contract: Contract) -> dict:
    sheet = attempt / contract.stage_for("sheet", "02-sheet")
    semantic_path = sheet / "qa" / "semantic-review.json"
    manifest_path = sheet / "qa" / "panel-manifest.json"
    ready = False
    canonical_boards: dict[str, dict] = {}
    approved: dict[str, list[str]] = {}
    approved_motion: dict[str, list[dict]] = {}
    if semantic_path.exists():
        ready = bool(json.loads(semantic_path.read_text(encoding="utf-8")).get("reference_ready"))
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for sheet_record in manifest.get("sheets", []):
            subject_id = sheet_record.get("subject_id")
            for panel in sheet_record.get("panels", []):
                path = panel.get("reference_crop_path")
                if (panel.get("review_status") == "approved"
                        and panel.get("safe_for_identity_reference") is True and path):
                    approved.setdefault(subject_id, []).append(path)
                if (panel.get("review_status") == "approved"
                        and panel.get("safe_for_motion_reference") is True and path):
                    part_ids = list(panel.get("binds_part_ids") or [])
                    site_ids = list(panel.get("binds_interaction_site_ids") or [])
                    if part_ids or site_ids:
                        approved_motion.setdefault(subject_id, []).append({
                            "path": path,
                            "binds_part_ids": part_ids,
                            "binds_interaction_site_ids": site_ids,
                        })
    expected = sorted(contract.elements())
    for subject_id in expected:
        path = sheet / "output" / "sheets" / f"{subject_id}.png"
        if path.exists():
            canonical_boards[subject_id] = {
                "path": str(path.resolve()),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()[:16],
                "role": "canonical_stage02_reference_board",
            }
    missing = [sid for sid in expected if sid not in canonical_boards]
    return {
        "reference_ready": ready and not missing,
        "canonical_boards": canonical_boards,
        "canonical_boards_required_for_relevant_shots": True,
        "approved_selective_crops": approved,
        "approved_motion_affordance_crops": approved_motion,
        "missing_subjects": missing,
        "whole_boards_allowed": True,
        "whole_boards_required": True,
        "supplemental_references_replace_canonical_boards": False,
        "design_without_pixels_allowed": True,
        "plate_generation_allowed": ready and not missing,
        "reason": (
            "all canonical stage-02 boards exist and semantic review is ready"
            if ready and not missing else
            "shot design may proceed, but stage 05/H3 must wait for every relevant canonical "
            "stage-02 board and semantic approval"
        ),
    }


def gather(attempt: Path, contract: Contract) -> dict:
    state = read_premise_state(attempt, contract)
    if state.get("form_ok") is False:
        raise ShotDesignError("01-premise form_ok=false라 shot design을 만들 수 없다")
    impact = read_direction_impact(attempt, contract)
    # A shot *design* can be drafted against the persisted scenario even when
    # an older lifecycle receipt still asks for revalidation.  It cannot become
    # a production input silently: the state is carried into QA/receipt below
    # and keeps production_ready false.  This lets stage 04 be developed on
    # historical attempts without laundering their approvals.

    scenario_path = attempt / contract.stage_for("scenario", "03-scenario") / "output" / "scenario.json"
    if not scenario_path.exists():
        raise ShotDesignError(f"03-scenario output이 없다: {scenario_path}")
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))

    subjects_path = attempt / contract.get("subjects", {}).get(
        "directory", f'{contract.stage_for("premise", "01-premise")}/output/subjects')
    definitions = {}
    for subject_id in sorted(contract.elements()):
        path = subjects_path / f"{subject_id}.json"
        if not path.exists():
            raise ShotDesignError(f"요소 정의가 없다: {path}")
        definitions[subject_id] = json.loads(path.read_text(encoding="utf-8"))
    return {
        "scenario": scenario,
        "definitions": definitions,
        "reference_status": reference_status(attempt, contract),
        "premise_state": state,
        "direction_impact": impact,
    }


def _classify_purpose(beat: dict) -> str:
    text = f"{beat.get('purpose','')} {beat.get('what_happens','')}"
    if re.search(r"전경|공간|마을|야경|거실|등장|공개|포트폴리오|전체\s*맵|맵으로", text) \
            and not _STATE_CHANGE.search(text):
        return "establishing"
    if re.search(r"미소|바라|시선|마음|말|설명|마친", text):
        return "emotion"
    if re.search(r"세부|재질|확인창|연결부|물방울|디테일", text):
        return "insert"
    return "long_take" if float(beat.get("seconds", 0)) >= 10 else "action"


def _motion_complexity(beat: dict) -> tuple[str, int, bool]:
    text = str(beat.get("what_happens", ""))
    actions = _action_units(beat)
    clauses = [part for part in _MULTI_ACTION.split(text) if part.strip()]
    # Once Stage 03 provides explicit atomic actions, explanatory clauses in
    # `what_happens` must not inflate the executable action count.  The prose
    # can mention fixed parts, approach constraints and the final hold while
    # still describing one contracted action.
    units = (len(actions) if beat.get("sub_beats")
             else max(len(actions), min(len(clauses), 5)))
    exact = bool(_STATE_CHANGE.search(text))
    if _RIGID.search(text):
        motion_class = "rigid"
    elif _DEFORMABLE.search(text):
        motion_class = "deformable"
    elif exact:
        motion_class = "articulated"
    elif _AMBIENT.search(text):
        motion_class = "ambient"
    else:
        motion_class = "state_change"
    return motion_class, units, exact


def _route(beat: dict) -> tuple[str, str, int, bool]:
    motion_class, units, exact = _motion_complexity(beat)
    text = str(beat.get("what_happens", ""))
    if not exact or (motion_class == "ambient" and not _TRANSIT.search(text)):
        return "i2v", motion_class, units, False
    # The evaluated production policy is first-only. Exactness is carried by
    # semantic tracks and QA targets, not by forcing an end image into H3.
    return "i2v", motion_class, units, True


def _composition_for_cast(chars: list[str]) -> str:
    if len(chars) == 2:
        return "투샷"
    if len(chars) == 3:
        return "쓰리샷"
    return "싱글"


def _camera(beat: dict, exact: bool,
            chars: list[str] | None = None) -> tuple[dict, str, str, str]:
    chars = chars or []
    declared = beat.get("camera_design") or {}
    if isinstance(declared, dict) and declared.get("movement"):
        policy = str(declared.get("policy") or "directed")
        size = str(declared.get("frame_size") or "미디엄 풀샷")
        composition = str(declared.get("composition") or _composition_for_cast(chars))
        angle = str(declared.get("angle") or "아이 레벨")
        framing_detail = str(
            declared.get("framing") or "주 행동과 접촉 대상이 화면 안에서 계속 보인다"
        )
        framing = f"{size}, {composition}; {framing_detail}"
        return ({
            "movement": str(declared["movement"]),
            "amplitude": str(declared.get("amplitude") or
                             ("none" if policy == "locked" else "medium")),
            "speed": str(declared.get("speed") or "피사체의 속도와 방향을 명확히 읽게 한다"),
            "framing": framing,
            "end": str(declared.get("end") or "요청한 동작이 완결되는 구도에서 안정된다"),
            "angle": angle,
        }, policy, size, composition)

    text = str(beat.get("what_happens", ""))
    purpose = _classify_purpose(beat)
    # A subject's endpoint constraint does not imply a locked camera.  Transit
    # is decided first so H3 is not told both "walk away" and "freeze the view".
    if re.search(r"카메라.*(?:위와\s*뒤|빠지|풀백|줌\s*아웃|줌아웃)", text):
        movement = "드론 풀백"
        policy = "directed"
        speed = "위와 뒤로 천천히 물러나며 전체 구조가 한 번에 읽힐 때까지 일정하게"
        end = "전체 연결 맵과 엔드 프레임 여백이 함께 보이는 지점에서 안정된다"
    elif _TRANSIT.search(text):
        movement = "팔로우 샷"
        policy = "natural"
        speed = "피사체의 보행에 동기화된 작고 연속적인 움직임; 앞지르거나 뒤처지지 않는다"
        end = "피사체가 목적 지점에 도달할 때 자연스럽게 안정된다"
    elif exact:
        movement = "스태틱 샷"
        policy = "locked"
        speed = "고정, 속도 변화 없음"
        end = "시작과 같은 카메라 위치·높이·화각에서 끝난다"
    elif purpose in {"emotion", "establishing"}:
        movement = "슬로우 줌 인"
        policy = "prompt_only_small"
        speed = "거의 느껴지지 않을 만큼 느리고 일정하게"
        end = "프레이밍을 한 단계만 좁힌 지점에서 부드럽게 멈춘다"
    else:
        movement = "스태틱 샷"
        policy = "locked"
        speed = "고정, 속도 변화 없음"
        end = "처음 구도 그대로 끝난다"

    composition = _composition_for_cast(chars)
    if purpose == "insert":
        size, composition, angle = "클로즈업", "인서트", "아이 레벨"
    elif purpose == "establishing":
        size, angle = "롱샷", "아이 레벨"
    elif purpose == "emotion":
        size = "미디엄 샷" if len(chars) > 1 else "미디엄 클로즈업"
        angle = "아이 레벨"
    else:
        size, angle = "미디엄 풀샷", "아이 레벨"
    framing = f"{size}, {composition}; 주 행동과 접촉 대상이 화면 안에서 계속 보인다"
    return ({"movement": movement, "amplitude": "none" if policy == "locked" else "small",
             "speed": speed, "framing": framing, "end": end, "angle": angle},
            policy, size, composition)


def _state_text(beat: dict, position: str, actions: list[str]) -> str:
    action = str(beat.get("primary_action") or beat.get("what_happens") or "행동")
    change = str(beat.get("primary_visible_change") or action)
    if position == "start":
        explicit = str(beat.get("start_state_description") or "").strip()
        if explicit:
            return explicit
        return f"행동 직전. {action}을 시작할 준비가 되어 있고 변화는 아직 일어나지 않았다."
    if position == "mid":
        middle = actions[len(actions) // 2] if actions else action
        return f"동작이 진행 중인 관찰 가능한 중간 상태. {middle}"
    return f"요청한 변화만 완료된 직후. {change}"


def _guide_plan() -> list[dict]:
    """Production H3 conditioning: one approved first plate, never a last plate."""
    return [{"progress": 0.0, "state_role": "start", "h3_input": "first_frame"}]


def _performance(beat: dict, actions: list[str], seconds: float) -> dict:
    if not actions:
        actions = [str(beat.get("what_happens", "주 행동"))]
    count = len(actions)
    timeline = []
    for index, action in enumerate(actions):
        start = round(index / count, 2)
        end = round((index + 1) / count, 2)
        timeline.append({"from_progress": start, "to_progress": end,
                         "action": action, "must_be_observable": True})
    line = (beat.get("dialogue") or {}).get("text", beat.get("line", ""))
    return {
        "objective": str(beat.get("primary_action") or beat.get("purpose") or "beat 목적을 수행"),
        "start_pose": str(
            beat.get("start_state_description") or "첫 행동 직전의 안정된 준비 자세"
        ),
        "action_timeline": timeline,
        "end_pose": "마지막 변화가 읽히는 자세를 유지",
        "gaze": "행동 대상 우선; 대사가 있으면 문장 끝에서만 카메라",
        "dialogue": {"text": str(line or ""), "delivery_seconds": seconds},
        "rule": "준 것만 애니메이션한다. 타임라인 밖의 제스처·이동·소품 사용을 만들지 않는다.",
    }


def _invariants(beat: dict, chars: list[str], objects: list[str],
                camera_policy: str) -> list[str]:
    values = ["setting geometry", "lighting direction", "frame aspect"]
    if camera_policy == "locked":
        values.append("camera viewpoint")
    else:
        values.extend(["world-space setting geometry", "camera motion continuity"])
    if chars:
        values.extend(["character identity", "face", "wardrobe", "body proportions"])
    if objects:
        values.extend(["object identity", "object geometry", "object count"])
    return values


def _reference_locks(definitions: dict[str, dict], subject_ids: list[str]) -> list[dict]:
    """Bind visible design fields instead of relying on a generic identity noun."""
    preferred = {
        "character": ("identity", "appearance", "clothing", "wardrobe", "equipment",
                      "carried_items"),
        "subject": (
            "identity", "dimensions", "exterior_design", "interior",
            "wheels_and_brakes", "finish", "materials", "palette", "visual_style",
            "container", "contents", "organization",
        ),
        "setting": ("spatial_plan", "layout", "architecture", "infrastructure", "landmarks"),
    }
    locks = []
    for subject_id in dict.fromkeys(sid for sid in subject_ids if sid):
        spec = definitions.get(subject_id) or {}
        kind = str(spec.get("kind", "subject"))
        fields = [field for field in preferred.get(kind, ()) if field in spec]
        locks.append({
            "subject_id": subject_id,
            "definition_sha256": _sha(spec),
            "locked_fields": fields,
            "rule": "every visible value in these definition fields remains unchanged unless allowed_change names it",
        })
    return locks


def _geometry_locks(beat: dict, objects: list[str]) -> list[str]:
    text = str(beat.get("what_happens", ""))
    locks = [
        "pixel-register every region outside the allowed-change mask to the selected start plate",
        "preserve every non-moving subject bounding box, silhouette, part count, relative size and screen position",
    ]
    if re.search(r"밸브|valve", text, re.IGNORECASE):
        locks.append(
            "valve wheel center, outer diameter, rim thickness, spoke count and hub size are fixed; "
            "rotation may change spoke angle only inside the same outer silhouette"
        )
    for subject_id in dict.fromkeys(objects):
        locks.append(
            f"declared object '{subject_id}' preserves identity, geometry, silhouette and part count; "
            "only parts explicitly named by allowed_change may move or change state"
        )
    for interaction in beat.get("interaction_contracts") or []:
        if not isinstance(interaction, dict):
            continue
        target = interaction.get("target_part_id") or "unresolved target part"
        tool_part = interaction.get("tool_part_id") or "unresolved tool part"
        fixed = ", ".join(str(item) for item in interaction.get("fixed_part_ids") or [])
        result = interaction.get("result_state") or "declared result state"
        locks.append(
            f"only {tool_part} contacts {target}; only the part named by the result may change "
            f"to '{result}'; fixed parts [{fixed or 'unresolved'}] preserve position, axis and geometry"
        )
    return locks


def _screen_direction_contract(beat: dict, exact: bool, sublocation: str,
                               fast_track: bool = False) -> dict:
    required = bool(exact and _TRANSIT.search(str(beat.get("what_happens", ""))))
    if not required:
        return {"required": False, "status": "not_applicable",
                "generation_blocked_until_resolved": False}
    return {
        "required": True,
        "status": "pending_stage05_start_plate_annotation",
        "scene_space_intent": str(beat.get("what_happens", "")),
        "from_sublocation_id": sublocation,
        "to_sublocation_id": None,
        "start_center_normalized": None,
        "end_center_normalized": None,
        "screen_direction_vector": None,
        "depth_intent": None,
        "allowed_depth_intents": ["toward_camera", "away_from_camera", "constant_depth"],
        "generation_blocked_until_resolved": True,
        "resolution_rule": (
            "after selecting the start plate, the AI fast-track reviewer must mark start/end "
            "centers and depth intent; scene words such as 'toward the living room' do not "
            "define screen direction"
            if fast_track else
            "after selecting the start plate, a human must mark start/end centers and depth intent; "
            "scene words such as 'toward the living room' do not define screen direction"
        ),
    }


def _track(beat: dict, chars: list[str], objects: list[str], motion_class: str,
           exact: bool) -> list[dict]:
    if not exact:
        return []
    subjects = chars + objects
    if not subjects:
        subjects = ["scene-primary-motion"]
    path = "screen position follows the action described in the performance timeline"
    if _TRANSIT.search(str(beat.get("what_happens", ""))):
        path = "start and end screen positions must be annotated on the approved start plate"
    return [{
        "subject_id": sid,
        "motion_class": motion_class if sid in objects else "articulated",
        "control_mode": "semantic_track_for_plate_annotation_and_post_generation_QA",
        "path": path,
        "coordinates": "pending_stage05_plate_normalized_annotation",
        "visibility": "must remain visible unless the action explicitly creates occlusion",
        "tolerance": {"endpoint_normalized": 0.06, "wrong_direction_allowed": False,
                      "identity_drift_allowed": False},
    } for sid in subjects]


def _prompt(camera: dict, camera_policy: str, performance: dict,
            invariants: list[str], allowed: list[str],
            end_state: str, clauses: str, geometry_locks: list[str],
            direction_contract: dict, canonical_subject_ids: list[str],
            supplemental_reference_plan: dict, lighting_contract: dict) -> str:
    timeline = " ".join(
        f"{int(item['from_progress']*100)}-{int(item['to_progress']*100)}%: {item['action']}"
        for item in performance["action_timeline"])
    camera_text = (f"CAMERA — {camera['movement']}; {camera['speed']}; "
                   f"{camera['framing']}; END: {camera['end']}")
    framing_guard = (
        "Do not cut to or drift into a different framing."
        if camera_policy == "locked" else
        "Do not cut or make an abrupt, unmotivated reframe; camera motion must stay continuous "
        "with the subject while world-space set geometry remains coherent."
    )
    manual_ids = [item.get("manual_id") for item in
                  supplemental_reference_plan.get("manuals") or [] if item.get("manual_id")]
    return "\n".join([
        (
            "REFERENCE BINDING — attach every approved canonical stage-02 sheet in this exact "
            f"subject order: {', '.join(canonical_subject_ids)}. "
            + (f"Then attach these approved clean interaction-manual boards: {', '.join(manual_ids)}. "
               if manual_ids else "No supplemental interaction-manual board is required. ")
            + "The first frame alone defines the actual starting composition and pose. Use sheets "
            "for identity/design/world truth and manuals only for mechanics; never reproduce their "
            "grid, panels, neutral backdrop, labels or reference poses in the video."
        ),
        camera_text,
        f"LIGHTING AND SHADOW CONTRACT — {_lighting_prompt(lighting_contract)}",
        f"ACTION TIMELINE — {timeline}",
        f"ONLY THESE CHANGES — {', '.join(allowed)}",
        f"MUST REMAIN UNCHANGED — {', '.join(invariants)}",
        f"GEOMETRY LOCKS — {'; '.join(geometry_locks)}",
        ("SCREEN DIRECTION — unresolved. Do not generate H3 until normalized start/end centers, "
         "direction vector and depth intent are approved."
         if direction_contract.get("generation_blocked_until_resolved") else
         "SCREEN DIRECTION — not required for this shot."),
        f"FINAL OBSERVABLE STATE — {end_state}",
        "Do not reverse the direction, rotate a translating subject sideways, invent a new action, "
        f"or change the set geometry. {framing_guard}",
        clauses,
    ]).strip()


def _plate_prompt(beat: dict, state_text: str, camera: dict, camera_policy: str, size: str,
                  composition: str, clauses: str, state_role: str,
                  geometry_locks: list[str], direction_contract: dict,
                  canonical_subject_ids: list[str], manual_ids: list[str],
                  frame_width: int, frame_height: int, lighting_contract: dict) -> str:
    chars = ", ".join(_list(beat.get("who"))) or "no character"
    objects = ", ".join(_list(beat.get("objects"))) or "no declared handheld object"
    viewpoint = (
        "Camera is at the exact shared shot viewpoint."
        if camera_policy == "locked" else
        "Camera is at the declared viewpoint for this state along one continuous camera path; "
        "preserve world-space architecture and lighting rather than pixel-registering the view."
    )
    orientation = (
        "Portrait" if frame_height > frame_width else
        "Landscape" if frame_width > frame_height else
        "Square"
    )
    return " ".join([
        "Attach every approved canonical stage-02 sheet in this exact subject order: "
        f"{', '.join(canonical_subject_ids)}. "
        + (f"Also attach these approved clean interaction-manual boards: {', '.join(manual_ids)}."
           if manual_ids else "No supplemental interaction-manual board is required."),
        f"{orientation} production plate ({frame_width}x{frame_height} native frame) "
        f"at {_where(beat)}.",
        f"Characters: {chars}. Objects: {objects}.",
        f"Lighting and shadow contract: {_lighting_prompt(lighting_contract)}.",
        f"The only depicted state is: {state_text}",
        ("This is strictly before the action. Do not show contact, displacement, rotation, "
         "opening, closing, tool use, gesture, or destination attainment already underway."
         if state_role == "start" else
         "Show the requested state change as completed, but do not add the next action."),
        f"Geometry locks: {'; '.join(geometry_locks)}.",
        ("TEMPLATE ONLY: do not generate an end or guide plate until screen-space start/end "
         "centers and depth intent are explicitly approved from the selected start plate."
         if state_role != "start" and direction_contract.get("generation_blocked_until_resolved") else ""),
        f"Frame: {size}, {composition}, {camera['angle']}. {viewpoint}",
        "This is one cinematic frame, not a board, grid, collage, split screen, or labeled diagram.",
        clauses,
    ]).strip()


def _candidate_policy(route: str, exact: bool, fast_track: bool = False) -> dict:
    return {
        "strategy": "one_take_then_review_append_retry",
        "candidate_count": 1,
        "initial_generation_count": 1,
        "max_attempts": MAX_GENERATION_ATTEMPTS,
        "stop_on_pass": True,
        "vary_every_retry": True,
        "variation_strategies": list(VARIATION_STRATEGIES),
        "candidate_semantics": "C01..C10 are retries/takes of one shot, never alternate angles",
        "seed_policy": "deterministic consecutive seeds recorded in the motion receipt",
        "preselect": ["contract/frame compliance", "first-frame identity", "background drift",
                      "motion direction", "change budget", "end-state attainment"],
        "human_required": not fast_track,
        "auto_promotion_allowed": fast_track,
        "selection_mode": "ai_fast_track" if fast_track else "human",
        "exhaustion_policy": (
            "use_attempt_10_and_continue_with_recorded_defects"
            if fast_track else "retain_attempt_10_for_human_review"
        ),
        "route": route,
    }


def _manual_kind(beat: dict) -> tuple[str | None, list[str]]:
    """Propose a supplemental manual only when a still cannot teach the action.

    The proposal is deliberately conservative.  A human still approves the
    decision, but tool contact and articulated mechanisms are never silently
    delegated to the image/video model.
    """
    declared = beat.get("supplemental_reference_requirement") or {}
    if isinstance(declared, dict) and declared.get("manual_type"):
        return str(declared["manual_type"]), [
            str(declared.get("reason") or
                "stage03 explicitly requires a cut-specific supplemental reference")
        ]

    text = " ".join([
        str(beat.get("primary_action") or ""),
        str(beat.get("what_happens") or ""),
        json.dumps(beat.get("interaction_contracts") or [], ensure_ascii=False),
    ])
    reasons = []
    interactions = [item for item in beat.get("interaction_contracts") or []
                    if isinstance(item, dict)]
    interaction_types = {item.get("interaction_type") for item in interactions
                         if item.get("interaction_type")}
    if interactions:
        reasons.append("stage03 declares one or more explicit interaction contracts")
        if interaction_types == {"articulated_mechanism"}:
            return "articulated_mechanism", reasons
        if interaction_types == {"assembly_sequence"}:
            return "assembly_sequence", reasons
        if len(interaction_types) > 1:
            return "mixed_interactions", reasons
    if _PROFESSIONAL_TOOL.search(text) and _MECHANICAL_ACTUATION.search(text):
        reasons.append("non-obvious tool/fastener/contact mechanics appear in the action")
    if reasons:
        return "mechanical_interaction", reasons
    if _ASSEMBLY_MANUAL.search(text):
        return "assembly_sequence", [
            "an ordered alignment/engagement/assembly sequence must preserve compatible interfaces"
        ]
    if _MECHANICAL_MANUAL.search(text) and _MECHANICAL_ACTUATION.search(text):
        return "mechanical_interaction", [
            "non-obvious fastener/contact mechanics appear in the action"
        ]
    if _ARTICULATED_MANUAL.search(text) and _ARTICULATED_ACTUATION.search(text):
        return "articulated_mechanism", [
            "an articulated mechanism changes state and its fixed/moving parts must be taught"
        ]
    return None, ["the action is readable from canonical sheets plus one approved start plate"]


def _manual_panels(kind: str) -> list[dict]:
    if kind == "vehicle_dynamics":
        specs = [
            ("P1", "exterior_identity", "low front three-quarter tracking view", "steady_speed",
             "complete vehicle silhouette, ride height, wheel rotation and track direction"),
            ("P2", "acceleration_attitude", "matched low side view", "hard_acceleration",
             "rear squat, front lift limit, tyre contact patches and stable body identity"),
            ("P3", "corner_entry", "long-lens exterior panning view", "turn_in",
             "front wheel steer angle, body yaw and track-edge relationship"),
            ("P4", "corner_mid", "matched long-lens exterior view", "steady_cornering",
             "observable but restrained body roll, loaded outside tyres and stable aero surfaces"),
            ("P5", "braking_attitude", "matched trackside telephoto view", "hard_braking",
             "brief nose pitch, aligned wheels, compressed front tyres and stable trajectory"),
            ("P6", "rear_exit", "low rear three-quarter tracking view", "corner_exit",
             "rear stance, diffuser clearance, acceleration direction and unchanged vehicle design"),
        ]
    elif kind == "cabin_occupancy":
        specs = [
            ("P1", "cabin_overview", "wide dashboard-mounted two-shot", "seated_ready",
             "left driver seat and right passenger seat, both adult occupants with fastened belts; "
             "the driver wears a track helmet and the bare-headed host wears no helmet"),
            ("P2", "driver_controls", "driver-side medium view", "steady_driving",
             "driver hands at nine and three, steering wheel, fixed paddles and forward gaze"),
            ("P3", "passenger_restraint", "passenger-side medium view", "steady_driving",
             "bare-headed host in right passenger seat with no helmet; her snug three-point belt "
             "runs safely from shoulder across the sternum and low over the hips, following the "
             "fitted top and making her natural bust-to-waist silhouette readable without unsafe "
             "routing or altered body proportions"),
            ("P4", "acceleration_reaction", "matched dashboard two-shot", "hard_acceleration",
             "visible rearward inertial load: both torsos and heads press into the seatbacks, "
             "the host moves more than the composed driver, and cheeks and loose hair lag toward "
             "the vehicle rear; show bodily displacement rather than expression alone"),
            ("P5", "cornering_reaction", "matched dashboard two-shot", "steady_cornering",
             "clear shared lateral inertial load toward the outside of one turn: both torsos, heads, "
             "cheeks and loose hair shift in the same physically correct direction, with the host "
             "moving more while belts and seat bolsters arrest the motion; the driver stays braced "
             "and looks to the exit"),
            ("P6", "braking_reaction", "matched dashboard two-shot", "hard_braking",
             "visible forward inertial load: both torsos and heads pitch into taut shoulder belts, "
             "with the host moving more than the composed driver and cheeks and loose hair lagging "
             "forward; hips remain supported and neither occupant flails or changes seats"),
        ]
    elif kind == "mechanical_interaction":
        specs = [
            ("P1", "structure_overview", "neutral three-quarter", "pre_action",
             "complete tool and target assembly, stable part count, and relative scale"),
            ("P2", "axis_view", "look directly along the target axis", "pre_contact",
             "target cross-section, axis, clearance, and fixed support"),
            ("P3", "action_plane", "orthographic side view of the true action plane", "pre_contact",
             "tool approach, capacity-to-target fit, and a physically possible grip angle"),
            ("P4", "engaged_contact", "close orthographic contact view", "contact",
             "the exact tool part touching the exact target part with no interpenetration"),
            ("P5", "actuation_mid", "same true action-plane view", "mid_action",
             "force or torque direction, moving parts, fixed parts, hands and handle sweep"),
            ("P6", "resolved_state", "matched comparison view", "post_action",
             "only the declared result changed; identity, assembly and fixed parts remain intact"),
        ]
    elif kind == "assembly_sequence":
        specs = [
            ("P1", "parts_and_interfaces", "neutral separated parts view", "pre_action",
             "all participating parts, mating interfaces, stable part count and relative scale"),
            ("P2", "interface_axis", "orthographic interface/axis view", "pre_alignment",
             "receiving part, moving part, alignment relation, clearance and orientation"),
            ("P3", "aligned_start", "matched functional view", "aligned",
             "correctly aligned parts immediately before engagement"),
            ("P4", "initial_engagement", "close orthographic contact view", "contact",
             "first engagement with no interpenetration, duplication or skipped part"),
            ("P5", "assembly_mid", "same functional view", "mid_action",
             "ordered wrap, insertion, mating or fastening state and hand/tool clearance"),
            ("P6", "resolved_assembly", "matched comparison view", "post_action",
             "declared completed assembly with fixed parts and all unrelated interfaces unchanged"),
        ]
    else:
        specs = [
            ("P1", "assembly_overview", "neutral three-quarter", "start",
             "complete mechanism, stable part count and surrounding fixed structure"),
            ("P2", "axis_or_track", "orthographic axis/track view", "start",
             "hinge, rail, pivot or deformation boundary and available clearance"),
            ("P3", "start_state", "matched functional view", "start",
             "the exact state before motion and all contact relationships"),
            ("P4", "early_state", "same matched functional view", "early_action",
             "first observable displacement without a new action"),
            ("P5", "mid_state", "same matched functional view", "mid_action",
             "halfway state, moving parts, fixed parts and occlusion behavior"),
            ("P6", "resolved_state", "same matched functional view", "post_action",
             "declared result state with every invariant preserved"),
        ]
    return [
        {"panel_id": panel_id, "role": role, "view": view, "state": state,
         "must_show": must_show}
        for panel_id, role, view, state, must_show in specs
    ]


def _manual_unresolved(kind: str, interaction: dict | None) -> list[str]:
    if kind in {"vehicle_dynamics", "cabin_occupancy"}:
        return []
    if not interaction:
        return ["stage03.interaction_contracts"]
    required = [
        "target_subject_id", "target_part_id", "fixed_part_ids", "moving_part_ids", "result_state"
    ]
    if kind == "mechanical_interaction":
        required.extend(["tool_subject_id", "tool_part_id"])
    unresolved = [field for field in required if not interaction.get(field)]
    if kind == "mechanical_interaction":
        axis = interaction.get("axis_contract") or {}
        for field in ("tool_action_plane_part_id", "target_axis_part_id", "relation",
                      "target_angle_deg", "max_error_deg"):
            if axis.get(field) in (None, "", []):
                unresolved.append(f"axis_contract.{field}")
        fit = interaction.get("fit_contract") or {}
        for field in ("tool_capacity_part_id", "target_extent_part_id", "tool_capacity_mm",
                      "target_extent_mm", "minimum_capacity_ratio"):
            if fit.get(field) in (None, "", []):
                unresolved.append(f"fit_contract.{field}")
        projection = interaction.get("projection_contract") or {}
        for field in ("mechanical_truth_over_tool_hero_view",
                      "hero_three_quarter_tool_view_forbidden"):
            if projection.get(field) is not True:
                unresolved.append(f"projection_contract.{field}=true")
    elif kind == "assembly_sequence":
        interface = interaction.get("interface_contract") or {}
        for field in ("moving_part_id", "receiving_part_id", "alignment_relation",
                      "engagement_motion", "start_state", "mid_state", "end_state"):
            if interface.get(field) in (None, "", []):
                unresolved.append(f"interface_contract.{field}")
    else:
        kinematic = interaction.get("kinematic_contract") or {}
        for field in ("motion_type", "axis_or_track_part_id", "start_state",
                      "mid_state", "end_state"):
            if kinematic.get(field) in (None, "", []):
                unresolved.append(f"kinematic_contract.{field}")
    return unresolved


def _manual_prompt(kind: str, source_text: str, canonical_subject_ids: list[str],
                   interaction: dict | None, panels: list[dict], clauses: str,
                   unresolved: list[str], lighting_contract: dict) -> str:
    status = (
        "READY FOR RENDERING."
        if not unresolved else
        "BLOCKED DRAFT. Resolve the listed contract fields before sending this prompt to an image model."
    )
    interaction = interaction or {}
    fixed_parts = interaction.get("fixed_part_ids") or []
    moving_parts = interaction.get("moving_part_ids") or []
    motion_isolation = (
        "EXHAUSTIVE PART MOTION LOCK — fixed parts "
        + json.dumps(fixed_parts, ensure_ascii=False)
        + " remain in the identical mechanical state, attachment, pose and position in every panel. "
        "The complete and exhaustive set of parts allowed to change is "
        + json.dumps(moving_parts, ensure_ascii=False)
        + "; every unlisted part is fixed. Do not infer a secondary action from ordinary mechanism "
        "behavior: unlocking does not open a drawer, releasing does not detach a part, and closing "
        "does not move a latch unless that secondary motion is explicitly declared."
    )
    kinematic = interaction.get("kinematic_contract") or {}
    articulated_state_lock = (
        "ARTICULATED STATE LOCK — P1, P2 and P3 are three views of the exact same declared "
        "start configuration: " + json.dumps(kinematic.get("start_state"), ensure_ascii=False)
        + ". Camera angle may change, but no part state may change between P1-P3. P4 shows only "
        "the first displacement, P5 shows exactly the declared mid configuration: "
        + json.dumps(kinematic.get("mid_state"), ensure_ascii=False)
        + ", and P6 shows exactly the declared end configuration: "
        + json.dumps(kinematic.get("end_state"), ensure_ascii=False)
        + ". The moving part must progress monotonically along the one declared axis or track; it "
        "must never reverse, oscillate, switch pivots or change orientation discontinuously."
        if kind == "articulated_mechanism" else None
    )
    return "\n\n".join(item for item in [
        status,
        "ASSET — one clean six-panel interaction reference board arranged as exactly two columns "
        "by three rows for H3 conditioning, "
        "using the contract-declared stage-02 reference-board raster and high quality.",
        "CANONICAL INPUT BINDING — the attached approved stage-02 sheets correspond in order to: "
        + ", ".join(canonical_subject_ids)
        + ". Preserve their identity, construction, proportions, materials, colors and part count. "
        "This supplemental board may explain an interaction but may not redesign any subject or setting.",
        "SHOT ACTION TO EXPLAIN — " + source_text,
        "INTERACTION FACTS — " + json.dumps(interaction, ensure_ascii=False, sort_keys=True),
        "UNRESOLVED CONTRACT FIELDS — " + json.dumps(unresolved, ensure_ascii=False),
        "PANEL CONTRACT — " + json.dumps(panels, ensure_ascii=False),
        motion_isolation,
        articulated_state_lock,
        "PANEL PLACEMENT — fixed row-major order only: top row P1 then P2; middle row P3 then P4; "
        "bottom row P5 then P6. Each panel must occupy exactly one grid cell. Do not use three "
        "columns by two rows and do not let one image cross a panel boundary.",
        "LIGHTING AND SHADOW CONTRACT — " + _lighting_prompt(lighting_contract),
        (
            "CONSISTENCY — show the same vehicle, wheels, aero surfaces and track direction in every "
            "panel. Preserve wheelbase, ride height, body geometry, paint and camera-side continuity. "
            "Only physically plausible acceleration squat, cornering roll, steering angle, tyre load "
            "and braking pitch may change between the declared states."
            if kind == "vehicle_dynamics" else
            "CONSISTENCY — show the same left-seat professional driver and right-seat female host in "
            "the same cockpit. Preserve faces, helmets, clothing, seat positions, belt routing, hands, "
            "controls and cabin geometry. Reactions must follow the declared vehicle load through "
            "coherent torso, shoulder, head, cheek and loose-hair displacement; an expressive face "
            "on an otherwise static body is not sufficient. The trained driver remains visibly more "
            "controlled than the passenger, but both bodies obey the same acceleration vector. Belts "
            "and seat bolsters visibly arrest motion without moving either occupant into the wrong "
            "seat or letting the passenger drive. The driver wears the same correctly fastened track "
            "helmet in every panel. The host remains bare-headed with her long hair visible and never "
            "wears a helmet. Her three-point belt remains safely routed over the shoulder and sternum "
            "and low across the hips; its snug fit and the established fitted top may emphasize her "
            "natural bust and waist silhouette, but must not deform anatomy or use unsafe belt routing."
            if kind == "cabin_occupancy" else
            "CONSISTENCY — show the same tool, target, assembly and relevant hands or limbs in every "
            "panel. Preserve dimensions and topology across all views and states. Mechanical truth, "
            "fit, axis and contact visibility take priority over a flattering hero angle. Do not enlarge "
            "the target to showcase it or rotate the tool into an impossible camera-facing pose."
            if kind == "mechanical_interaction" else
            "CONSISTENCY — show the same parts, mating interfaces and relevant hands or tools in "
            "every panel. Preserve dimensions, topology and part count. Show alignment, first contact, "
            "engagement motion and the resolved assembly as an ordered physical sequence; never skip "
            "a part, merge parts, or replace connection logic with a visual morph."
            if kind == "assembly_sequence" else
            "CONSISTENCY — show the same mechanism and surrounding fixed structure in every panel. "
            "Only declared moving parts change state; preserve topology, attachment, materials, lighting "
            "logic and clearance across all views."
        ),
        "H3-CLEAN OUTPUT — thin neutral panel separators only. No arrows, labels, numbers, dimension "
        "text, captions, logos, signatures, watermark, cinematic montage, duplicated parts, invented "
        "parts, detached parts or before/after morphing inside one panel.",
        clauses,
    ] if item is not None).strip()


def _interaction_reference_plan(shot_id: str, beat: dict, canonical_subject_ids: list[str],
                                plate_clauses: str, lighting_contract: dict,
                                fast_track: bool = False) -> dict:
    kind, reasons = _manual_kind(beat)
    required = kind is not None
    interactions = [item for item in beat.get("interaction_contracts") or []
                    if isinstance(item, dict)]
    if required and not interactions:
        interactions = [None]
    manuals = []
    for index, interaction in enumerate(interactions, start=1):
        interaction_type = (interaction or {}).get("interaction_type")
        manual_kind = (
            "articulated_mechanism"
            if interaction_type == "articulated_mechanism" else
            "assembly_sequence"
            if interaction_type == "assembly_sequence" else
            "mechanical_interaction"
            if interaction_type == "mechanical_tool_contact" else
            kind or "articulated_mechanism"
        )
        panels = _manual_panels(manual_kind)
        unresolved = _manual_unresolved(manual_kind, interaction)
        prompt = _manual_prompt(
            manual_kind,
            str(beat.get("what_happens") or beat.get("primary_action") or ""),
            canonical_subject_ids,
            interaction,
            panels,
            plate_clauses,
            unresolved,
            lighting_contract,
        )
        manual_id = f"{shot_id}-IM{index:02d}"
        manuals.append({
            "manual_id": manual_id,
            "manual_type": manual_kind,
            "source_interaction_id": (interaction or {}).get("interaction_id"),
            "required_stage02_sheet_subject_ids": canonical_subject_ids,
            "views": list(dict.fromkeys(panel["view"] for panel in panels)),
            "states": list(dict.fromkeys(panel["state"] for panel in panels)),
            "panels": panels,
            "interaction_facts": interaction or {},
            "unresolved_contract_fields": unresolved,
            "prompt_status": "ready" if not unresolved else "blocked_missing_interaction_facts",
            "image_generation_prompt": prompt if not unresolved else None,
            "draft_generation_prompt": prompt,
            "output_assets": {
                "clean_board": {
                    "owner_stage": "05-plate", "send_to_h3": True,
                    "text_or_arrows_allowed": False,
                },
                "annotated_qa_board": {
                    "owner_stage": "05-plate", "send_to_h3": False,
                    "render_method": "deterministic overlay on the approved clean board",
                    "annotations": [
                        "part ids", "target and tool axes", "contact points", "force/torque direction",
                        "fixed versus moving parts", "capacity and target dimensions", "forbidden geometry",
                    ],
                },
            },
            "approval": {
                "status": "pending_stage05_generation_and_ai_preflight",
                "review_mode": "ai_preflight",
                "human_approval_required": False,
                "auto_approve_allowed": True,
                "criteria": [
                    "all views preserve identity, topology, dimensions, materials and part count",
                    "all states form one physically continuous interaction without missing or invented parts",
                    "fit, axis, contact, clearance and fixed/moving part claims are visually verifiable",
                    "the clean board contains no labels, arrows, logos or diagram marks that can leak into H3",
                    "the annotated board agrees exactly with the clean board and the interaction contract",
                ],
            },
        })
    return {
        "policy_version": "interaction-manual.v1",
        "decision": "required" if required else "not_required",
        "required": required,
        "manual_type": kind,
        "decision_reasons": reasons,
        "human_decision_review_required": not fast_track,
        "decision_review_mode": "ai_fast_track" if fast_track else "human",
        "canonical_stage02_sheets_remain_required": True,
        "supplemental_manual_replaces_canonical_sheets": False,
        "manuals": manuals,
        "generation_blocked_until_approved_manuals": required,
    }


def _runtime_target(contract: Contract) -> float | None:
    runtime = contract.runtime_contract
    if runtime.get("mode") == "fixed":
        return float(runtime["target_seconds"])
    return None


def check_directorial_plan(plan: dict, scenario: dict, contract: Contract) -> dict:
    problems: list[str] = []
    warnings: list[str] = []
    source_scenes = {str(scene.get("id")): scene for scene in iter_scenes(scenario)}
    scene_ids = set(source_scenes)
    seen_shots: set[str] = set()
    timeline_total = 0.0
    all_shots = 0
    for scene in plan.get("scenes") or []:
        scene_id = str(scene.get("scene_id") or "")
        if scene_id not in scene_ids:
            problems.append(f"directorial scene이 scenario에 없다: {scene_id!r}")
        treatment = scene.get("treatment") or {}
        for field in ("intent", "pov", "blocking", "coverage_logic"):
            if not str(treatment.get(field) or "").strip():
                problems.append(f"{scene_id}: treatment.{field}가 없다")
        covered_events: set[str] = set()
        source_scene = source_scenes.get(scene_id) or {}
        source_events = {str(item.get("id")): item for item in source_scene.get("events") or []}
        requirement_ids = {str(item.get("id")) for item in
                           source_scene.get("production_requirements") or []}
        for setup in scene.get("setups") or []:
            setup_id = str(setup.get("setup_id") or "")
            if not setup_id:
                problems.append(f"{scene_id}: setup_id가 없다")
            for shot in setup.get("shots") or []:
                all_shots += 1
                shot_id = str(shot.get("shot_id") or "")
                if not shot_id or shot_id in seen_shots:
                    problems.append(f"shot id 누락 또는 중복: {shot_id!r}")
                seen_shots.add(shot_id)
                covered_events.update(str(item) for item in shot.get("event_ids") or [])
                declared_refs = {str(item) for item in
                                 shot.get("reference_requirement_ids") or []}
                if declared_refs - requirement_ids:
                    problems.append(
                        f"{shot_id}: scene에 없는 reference requirement {sorted(declared_refs - requirement_ids)}")
                expected_refs = {
                    str(source_events[event_id].get("target_subject_id"))
                    for event_id in shot.get("event_ids") or [] if event_id in source_events
                    and str(source_events[event_id].get("target_subject_id") or "").startswith("NEW-")
                }
                if expected_refs - declared_refs:
                    problems.append(
                        f"{shot_id}: 새 event target reference 결속 누락 {sorted(expected_refs - declared_refs)}")
                timing = shot.get("timing") or {}
                target = timing.get("edit_target_seconds")
                if (not isinstance(target, (int, float)) or isinstance(target, bool)
                        or target <= 0):
                    problems.append(f"{shot_id}: edit_target_seconds는 양수여야 한다")
                elif shot.get("included_in_timeline", True):
                    timeline_total += float(target)
                for field in ("tolerance_seconds", "head_handle_seconds", "tail_handle_seconds"):
                    value = timing.get(field)
                    if (not isinstance(value, (int, float)) or isinstance(value, bool)
                            or value < 0):
                        problems.append(f"{shot_id}: timing.{field}는 0 이상의 수여야 한다")
                if timing.get("temporal_mode") not in TEMPORAL_MODES:
                    problems.append(f"{shot_id}: temporal_mode 오류 {timing.get('temporal_mode')!r}")
                if timing.get("execution_method") not in TEMPORAL_EXECUTION_METHODS:
                    problems.append(f"{shot_id}: execution_method 오류 {timing.get('execution_method')!r}")
                if not str(timing.get("dramatic_reason") or "").strip():
                    problems.append(f"{shot_id}: timing.dramatic_reason이 없다")
                domains = timing.get("time_domains") or {}
                if any(not str(domains.get(key) or "").strip()
                       for key in ("subject", "world", "camera")):
                    problems.append(f"{shot_id}: subject/world/camera time domain이 필요하다")
                camera = shot.get("camera") or {}
                if any(not str(camera.get(key) or "").strip()
                       for key in ("movement", "speed", "framing", "end", "angle")):
                    problems.append(f"{shot_id}: camera movement/speed/framing/end/angle이 필요하다")
                if len([name for name in MOVEMENTS if name in str(camera.get("movement"))]) != 1:
                    problems.append(f"{shot_id}: camera primary movement는 정확히 하나여야 한다")
                visible_cast = list(shot.get("visible_cast_ids") or [])
                if len(visible_cast) == 2 and shot.get("composition") not in {
                    "투샷", "오버 더 숄더"
                }:
                    problems.append(
                        f"{shot_id}: 두 인물이 보이면 투샷 또는 오버 더 숄더여야 한다")
                if len(visible_cast) < 2 and shot.get("composition") in {
                    "투샷", "쓰리샷", "오버 더 숄더"
                }:
                    problems.append(f"{shot_id}: composition을 구성할 visible cast가 부족하다")
        expected_events = set(source_events)
        if expected_events - covered_events:
            problems.append(
                f"{scene_id}: shot coverage에 빠진 event {sorted(expected_events - covered_events)}")

    if plan.get("schema_version") != "directorial-plan.v2":
        problems.append("directorial-plan.v2 schema가 필요하다")
    if not all_shots:
        problems.append("directorial plan에 shot이 없다")
    target = _runtime_target(contract)
    if target is not None and abs(timeline_total - target) > 0.05:
        problems.append(
            f"timeline 포함 shot의 edit target 합 {timeline_total:g}초, Stage 1 runtime {target:g}초")
    return {"ok": not problems, "problems": problems, "warnings": warnings,
            "shots": all_shots, "timeline_edit_seconds": round(timeline_total, 3)}


def write_directorial_plan(attempt: Path, contract: Contract, source: dict,
                           model: str | None = None) -> dict:
    """Use an LLM for directorial/timing choices, then validate with the harness."""
    scenario = source["scenario"]
    base_prompt = "\n\n".join([
        DIRECTOR_RULES,
        "Stage 1 runtime contract:\n" + json.dumps(
            contract.runtime_contract, ensure_ascii=False, indent=2),
        "Stage 03 narrative design:\n" + json.dumps(scenario, ensure_ascii=False, indent=2),
        "Canonical element definitions:\n" + json.dumps(
            source.get("definitions") or {}, ensure_ascii=False, indent=2),
        "Production frame and runtime:\n" + json.dumps({
            "frame": contract.frame.as_dict(), "video_engine": PROFILE_ID,
            "valid_temporal_modes": sorted(TEMPORAL_MODES),
        }, ensure_ascii=False, indent=2),
    ])
    correction = ""
    records = []
    client = _client()
    for number in range(1, MAX_GENERATION_ATTEMPTS + 1):
        effective = retry_prompt(
            base_prompt, number, correction,
            failed_criteria=[line for line in correction.splitlines() if line.strip()],
            allowed_revisions=(
                "scene treatment, blocking and coverage owned by Stage 04",
                "setup and shot boundaries, camera, composition and performance",
                "edit contribution, handles, temporal mode, execution method and capability debt",
            ))
        try:
            response = client.responses.create(
                model=model or contract.text_model or DEFAULT_MODEL,
                input=effective,
                text={"format": {"type": "json_object"}},
            )
            candidate = json.loads(response.output_text)
            candidate["schema_version"] = "directorial-plan.v2"
            report = check_directorial_plan(candidate, scenario, contract)
            failed = list(report["problems"])
        except Exception as error:
            candidate = None
            failed = [f"generation error: {type(error).__name__}: {error}"]
        decision = "pass" if not failed else "fail"
        records.append(attempt_record(number, effective, decision, "\n".join(failed), failed))
        if decision == "pass" and candidate is not None:
            candidate["created_at"] = _now()
            candidate["created_by"] = model or contract.text_model or DEFAULT_MODEL
            candidate["runtime_contract"] = contract.runtime_contract
            candidate["source_scenario_sha256"] = _sha(scenario)
            candidate["generation_harness"] = {
                **harness_contract(
                    "stage04_directorial_plan", _sha(base_prompt),
                    ("all scenes have treatment and setups", "every shot has creative timing",
                     "timeline edit contribution satisfies the Stage 1 runtime contract"),
                    exhaustion_policy="report_attempt_10_with_unresolved_directorial_findings",
                    execution_mode=load_execution_mode(attempt)["mode"],
                ),
                "attempts": records,
            }
            return candidate
        correction = "\n".join(f"- {item}" for item in failed)
    raise ShotDesignError(
        f"Stage 04 directorial plan이 {MAX_GENERATION_ATTEMPTS}회 뒤에도 실패했다: "
        + "; ".join(records[-1]["failed_criteria"]))


def _legacy_directorial_plan(scenario: dict) -> dict:
    """Compatibility adapter only; new Stage-03 scene designs never use it."""
    scenes = []
    shots = []
    index = 0
    for parent in scenario.get("beats") or []:
        # Preserve already-authored legacy sub-beat boundaries during audit.
        # The three-second heuristic lives only in this migration adapter and
        # is never consulted by narrative-design.v3.
        for beat in _split_beat(parent):
            index += 1
            shots.append({
                "shot_id": f"S{index:02d}", "event_ids": [beat.get("id")],
                "included_in_timeline": True,
                "timing": {
                    "edit_target_seconds": float(beat.get("seconds") or 1),
                    "tolerance_seconds": 0.0, "head_handle_seconds": 0.0,
                    "tail_handle_seconds": 0.0, "temporal_mode": "real_time",
                    "dramatic_reason": str(beat.get("why_this_long") or "legacy authored duration"),
                    "execution_method": "model_native", "source_playback_rate": 1.0,
                    "time_domains": {"subject": "real_time", "world": "real_time",
                                     "camera": "real_time"},
                    "speed_curve": [{"at": 0, "rate": 1}, {"at": 1, "rate": 1}],
                    "camera_time": "continuous", "capability_debt": [],
                },
                "_legacy_beat": beat,
            })
    scenes.append({"scene_id": "LEGACY", "treatment": {
        "intent": "preserve legacy scenario", "pov": "legacy", "blocking": "legacy",
        "coverage_logic": "one compatibility shot per beat"},
        "setups": [{"setup_id": "LEGACY-SU", "shots": shots}]})
    return {"schema_version": "directorial-plan.v2", "legacy_adapter": True,
            "scenes": scenes}


def _planned_units(scenario: dict, plan: dict) -> list[dict]:
    scenes = {str(item.get("id")): item for item in iter_scenes(scenario)}
    units: list[dict] = []
    for planned_scene in plan.get("scenes") or []:
        scene_id = str(planned_scene.get("scene_id") or "")
        source_scene = scenes.get(scene_id, {})
        events = {str(item.get("id")): item for item in source_scene.get("events") or []}
        for setup in planned_scene.get("setups") or []:
            for planned_shot in setup.get("shots") or []:
                if planned_shot.get("_legacy_beat"):
                    beat = dict(planned_shot["_legacy_beat"])
                else:
                    selected = [events[event_id] for event_id in planned_shot.get("event_ids") or []
                                if event_id in events]
                    actions = [str(item.get("action") or "") for item in selected]
                    changes = [str(item.get("visible_change") or "") for item in selected]
                    beat = dict(source_scene)
                    beat.update({
                        "id": planned_shot.get("shot_id"),
                        "purpose": source_scene.get("act_id"),
                        "what_happens": " ".join(value for value in actions if value),
                        "primary_action": actions[0] if actions else planned_shot.get("purpose", ""),
                        "primary_visible_change": changes[-1] if changes else planned_shot.get("purpose", ""),
                        "sub_beats": selected,
                        "who": list(planned_shot.get("visible_cast_ids") or []),
                        "cast_presence": [
                            {"subject_id": value, "role": "actor"}
                            for value in planned_shot.get("visible_cast_ids") or []
                        ],
                        "objects": list(planned_shot.get("visible_object_ids") or []),
                        "object_roles": [
                            {"subject_id": value, "role": "required_visible"}
                            for value in planned_shot.get("visible_object_ids") or []
                        ],
                    })
                beat["seconds"] = float((planned_shot.get("timing") or {})
                                        .get("edit_target_seconds") or beat.get("seconds") or 1)
                beat["_stage04_plan"] = {
                    "sequence_id": source_scene.get("sequence_id"), "scene_id": scene_id,
                    "setup_id": setup.get("setup_id"), "scene_treatment": planned_scene.get("treatment"),
                    **planned_shot,
                }
                units.append(beat)
    return units


def _compile_temporal(timing: dict, fps: int) -> dict:
    edit = float(timing.get("edit_target_seconds") or 0)
    head = float(timing.get("head_handle_seconds") or 0)
    tail = float(timing.get("tail_handle_seconds") or 0)
    method = str(timing.get("execution_method") or "model_native")
    rate = float(timing.get("source_playback_rate") or 1.0)
    if rate <= 0:
        rate = 1.0
    source_body = edit * rate if method == "post_retime" else edit
    requested = max(0.1, source_body + head + tail)
    frames = snap_length(requested, fps)
    native = frames / fps
    mode = str(timing.get("temporal_mode") or "real_time")
    debt = list(timing.get("capability_debt") or [])
    if mode in {"time_freeze", "bullet_time_orbit", "simultaneous_split_time"} \
            and method == "model_native":
        debt.append(
            f"{mode} has no guaranteed deterministic H3-native control; use hybrid/post plan or block")
    return {
        "edit_target_seconds": edit,
        "tolerance_seconds": float(timing.get("tolerance_seconds") or 0),
        "head_handle_seconds": head, "tail_handle_seconds": tail,
        "temporal_mode": mode, "dramatic_reason": timing.get("dramatic_reason"),
        "execution_method": method, "source_playback_rate": rate,
        "time_domains": timing.get("time_domains") or {},
        "action_phases": timing.get("action_phases") or [],
        "speed_curve": timing.get("speed_curve") or [],
        "camera_time": timing.get("camera_time"),
        "requested_generation_seconds": round(requested, 3),
        "native_frames": frames, "native_seconds": round(native, 3),
        "source_trim_seconds": round(max(0.0, native - requested), 3),
        "edit_operation": (
            "trim_handles_then_retime" if method in {"post_retime", "hybrid"}
            else "trim_handles_only"),
        "capability_debt": list(dict.fromkeys(str(item) for item in debt if str(item).strip())),
        "generation_blocked": bool(debt),
    }


def _temporal_prompt(temporal: dict) -> str:
    return (
        "TEMPORAL CONTRACT — "
        f"mode={temporal.get('temporal_mode')}; "
        f"dramatic reason={temporal.get('dramatic_reason')}; "
        f"execution={temporal.get('execution_method')}; "
        f"time domains={json.dumps(temporal.get('time_domains') or {}, ensure_ascii=False)}; "
        f"speed curve={json.dumps(temporal.get('speed_curve') or [], ensure_ascii=False)}; "
        f"camera time={temporal.get('camera_time')}; "
        "perform only the normalized action phases and leave head/tail handles free of a new event."
    )


def _reference_fulfillment_plan(scenario: dict) -> dict:
    assets: dict[str, dict] = {}
    for scene in iter_scenes(scenario):
        for requirement in scene.get("production_requirements") or []:
            if not isinstance(requirement, dict) or not requirement.get("id"):
                continue
            rid = str(requirement["id"])
            record = dict(requirement)
            record["scene_id"] = scene.get("id")
            record["required_before"] = (
                "stage05_start_plate" if record.get("reference_policy") not in {"prompt_only", "none"}
                else "prompt_compilation"
            )
            record["generation_required"] = record.get("reference_policy") not in {"prompt_only", "none"}
            if record["generation_required"]:
                record["manual_id"] = rid
                record["manual_type"] = "stage03_reference_debt"
                record["required_stage02_sheet_subject_ids"] = list(
                    record.get("canonical_input_subject_ids") or [])
                record["image_generation_prompt"] = (
                    "STRUCTURED PRODUCTION REFERENCE — Create a clean reference board for the "
                    f"newly authored asset {record.get('name', rid)}. Asset class: "
                    f"{record.get('asset_class')}. Description and story function: "
                    f"{record.get('description', '')}. Show only the views and states needed to "
                    "lock identity, scale, materials, topology and the declared interaction or location "
                    "relationship. No unrelated tools, bags, labels, text, people or decoration."
                )
                record["draft_generation_prompt"] = record["image_generation_prompt"]
                record["approval"] = {"status": "pending", "criteria": [
                    "the reference matches the declared new asset description and story function",
                    "identity, topology, proportions, materials and part count are internally consistent",
                    "the board contains no invented unrelated prop, person, label or text",
                    "the board is sufficient for every bound Stage 04 shot before a start plate is generated",
                ]}
            assets.setdefault(rid, record)
    return {
        "schema_version": "reference-fulfillment-plan.v1",
        "phase_order": [
            "5A_generate_and_validate_reference_debt",
            "5A_global_reference_preflight",
            "5B_generate_and_validate_start_plates",
        ],
        "assets": list(assets.values()),
        "generation_required_count": sum(item["generation_required"] for item in assets.values()),
    }


def compile_scenario(attempt: Path, contract: Contract, gathered: dict | None = None) -> dict:
    execution_mode = load_execution_mode(attempt)
    fast_track = execution_mode.get("mode") == FAST_TRACK_MODE
    source = gathered or gather(attempt, contract)
    scenario = source["scenario"]
    states: dict[str, dict] = {}
    shots = []
    base_seed = int(hashlib.sha256(contract.data["contract_id"].encode()).hexdigest()[:6], 16)
    reference_fulfillment = _reference_fulfillment_plan(scenario)
    reference_assets = {str(item.get("id")): item
                        for item in reference_fulfillment.get("assets") or []}

    directorial_plan = source.get("directorial_plan") or _legacy_directorial_plan(scenario)
    if scenario.get("schema_version") == SCENARIO_SCHEMA and directorial_plan.get("legacy_adapter"):
        raise ShotDesignError("narrative-design.v3에는 LLM directorial-plan.v2가 필요하다")
    expanded = _planned_units(scenario, directorial_plan)

    for index, beat in enumerate(expanded, start=1):
        planned = beat.get("_stage04_plan") or {}
        shot_id = str(planned.get("shot_id") or f"S{index:02d}")
        actions = _action_units(beat)
        route, motion_class, units, exact = _route(beat)
        chars, objects = _characters(beat, contract), _objects(beat, contract)
        new_objects = [str(value) for value in planned.get("visible_object_ids") or []
                       if str(value).startswith("NEW-")]
        depicted_objects = list(dict.fromkeys(objects + new_objects))
        if planned.get("camera"):
            camera = dict(planned["camera"])
            movement = str(camera.get("movement") or "")
            camera_policy = "locked" if "스태틱 샷" in movement else "directed"
            frame_size = str(planned.get("frame_size") or "미디엄 샷")
            composition = str(planned.get("composition") or _composition_for_cast(chars))
        else:
            camera, camera_policy, frame_size, composition = _camera(beat, exact, chars)
        where = _where(beat)
        sublocation = _sublocation(beat, contract)
        interaction_subject_ids = [
            value for interaction in beat.get("interaction_contracts") or []
            if isinstance(interaction, dict)
            for value in (interaction.get("tool_subject_id"), interaction.get("target_subject_id"))
            if value in source["definitions"]
        ]
        canonical_subject_ids = list(dict.fromkeys(
            chars + objects + ([where] if where in source["definitions"] else [])
            + interaction_subject_ids
        ))
        allowed = [str(beat.get("primary_visible_change") or beat.get("what_happens") or "primary action")]
        invariants = _invariants(beat, chars, depicted_objects, camera_policy)
        reference_locks = _reference_locks(source["definitions"], canonical_subject_ids)
        geometry_locks = _geometry_locks(beat, depicted_objects)
        direction_contract = _screen_direction_contract(beat, exact, sublocation, fast_track)
        lighting_contract = _lighting_contract(source["definitions"], where, beat)
        plate_ids, plate_clauses = _all_clause_text(
            contract, contract.stage_for("plate", "05-plate"), beat, chars)
        motion_ids, motion_clauses = _all_clause_text(
            contract, contract.stage_for("motion", "06-motion"), beat, chars)
        interaction_reference_plan = _interaction_reference_plan(
            shot_id, beat, canonical_subject_ids, plate_clauses, lighting_contract,
            fast_track,
        )
        authored_reference_ids = list(planned.get("reference_requirement_ids") or [])
        authored_reference_manuals = [
            dict(reference_assets[asset_id]) for asset_id in authored_reference_ids
            if asset_id in reference_assets and reference_assets[asset_id].get("generation_required")
        ]
        if authored_reference_manuals:
            interaction_reference_plan["required"] = True
            interaction_reference_plan["decision"] = "required_by_stage03_reference_debt"
            interaction_reference_plan["manuals"] = list(
                interaction_reference_plan.get("manuals") or []) + authored_reference_manuals
            interaction_reference_plan["generation_blocked_until_approved_manuals"] = True
        manual_ids = [item.get("manual_id") for item in
                      interaction_reference_plan.get("manuals") or [] if item.get("manual_id")]

        start_id, end_id, mid_id = f"{shot_id}-START", f"{shot_id}-END", f"{shot_id}-MID"
        start_text = _state_text(beat, "start", actions)
        end_text = _state_text(beat, "end", actions)
        states[start_id] = {
            "state_id": start_id, "shot_id": shot_id, "role": "start", "mode": "create",
            "description": start_text,
            "prompt": _plate_prompt(beat, start_text, camera, camera_policy,
                                    frame_size, composition,
                                    plate_clauses, "start", geometry_locks, direction_contract,
                                    canonical_subject_ids, manual_ids,
                                    contract.frame.width, contract.frame.height, lighting_contract),
            "reference_locks": reference_locks,
            "geometry_locks": geometry_locks,
            "lighting_contract": lighting_contract,
            "screen_direction_contract": direction_contract,
            "required_reference_subject_ids": canonical_subject_ids,
            "required_interaction_manual_ids": manual_ids,
        }
        if exact:
            states[end_id] = {
                "state_id": end_id, "shot_id": shot_id, "role": "end", "mode": "edit",
                "from": start_id, "description": end_text,
                "edit_scope": (
                    "only the allowed_change masks; preserve camera viewpoint and all invariants"
                    if camera_policy == "locked" else
                    "only the allowed subject change and declared camera-path projection; preserve "
                    "world-space geometry and all other invariants"
                ),
                "prompt": _plate_prompt(beat, end_text, camera, camera_policy,
                                        frame_size, composition,
                                        plate_clauses, "end", geometry_locks, direction_contract,
                                        canonical_subject_ids, manual_ids,
                                        contract.frame.width, contract.frame.height, lighting_contract),
                "reference_locks": reference_locks,
                "geometry_locks": geometry_locks,
                "lighting_contract": lighting_contract,
                "screen_direction_contract": direction_contract,
                "required_reference_subject_ids": canonical_subject_ids,
                "required_interaction_manual_ids": manual_ids,
            }
        timing_source = dict(planned.get("timing") or {
            "edit_target_seconds": beat.get("seconds", 0), "tolerance_seconds": 0,
            "head_handle_seconds": 0, "tail_handle_seconds": 0,
            "temporal_mode": "real_time", "dramatic_reason": beat.get("why_this_long"),
            "execution_method": "model_native", "source_playback_rate": 1,
            "time_domains": {"subject": "real_time", "world": "real_time", "camera": "real_time"},
        })
        if planned.get("performance") and not timing_source.get("action_phases"):
            timing_source["action_phases"] = (planned.get("performance") or {}).get("action_phases", [])
        temporal = _compile_temporal(timing_source, contract.frame.fps)
        seconds = float(temporal["edit_target_seconds"])
        frames = int(temporal["native_frames"])
        performance = _performance(beat, actions, seconds)
        if (planned.get("performance") or {}).get("action_phases"):
            performance["normalized_action_phases"] = planned["performance"]["action_phases"]
        anchor_policy = "first_only"
        guide_plan = _guide_plan()
        for guide in guide_plan:
            guide["state_id"] = {"start": start_id, "mid": mid_id, "end": end_id}[guide["state_role"]]

        shot = {
            "shot_id": shot_id,
            "beat_id": beat.get("id"),
            "sequence_id": planned.get("sequence_id"),
            "scene_id": planned.get("scene_id"),
            "setup_id": planned.get("setup_id"),
            "event_ids": list(planned.get("event_ids") or []),
            "scene_treatment": planned.get("scene_treatment"),
            "included_in_timeline": planned.get("included_in_timeline", True),
            "take_policy": "C01 first take; append one varied retry only after review failure, maximum C10",
            "beat_segment": beat.get("beat_segment", {"index": 1, "count": 1,
                                                       "parent_seconds": beat.get("seconds")}),
            "act_id": beat.get("purpose"),
            "cut_purpose": _classify_purpose(beat),
            "edit_seconds": seconds,
            "timeline_edit_seconds": seconds if planned.get("included_in_timeline", True) else 0.0,
            "temporal_design": temporal,
            "h3_generation": {"runtime": PROFILE_ID, "route": route,
                              "anchor_policy": anchor_policy,
                              "last_frame_allowed": False,
                              "requested_seconds": temporal["requested_generation_seconds"],
                              "native_frames": frames,
                              "native_seconds": round(frames / contract.frame.fps, 3),
                              "trim_in_edit": temporal["source_trim_seconds"],
                              "retime_plan": {
                                  "operation": temporal["edit_operation"],
                                  "source_playback_rate": temporal["source_playback_rate"],
                                  "target_edit_seconds": seconds,
                              },
                              "generation_blocked": temporal["generation_blocked"],
                              "capability_debt": temporal["capability_debt"],
                              "seed_base": base_seed + index * 100},
            "where_subject_id": where,
            "sublocation_id": sublocation,
            "cast_presence": [{"subject_id": sid, "role": "actor"} for sid in chars],
            "object_roles": [{"subject_id": sid, "role": "interacted_with"}
                             for sid in depicted_objects],
            "visual_focus": list(dict.fromkeys(
                chars + depicted_objects + _list(beat.get("visual_focus")))),
            "condition_flags": {
                flag: bool(beat[flag]) if flag in beat else
                (bool(chars) if flag == "has_host" else False)
                for flag in contract.condition_flags
            },
            "interaction_contracts": list(beat.get("interaction_contracts") or []),
            "reference_requirements": {
                "canonical_stage02_sheet_subject_ids": canonical_subject_ids,
                "stage03_production_requirement_ids": authored_reference_ids,
                "canonical_stage02_sheets_required": True,
                "identity_subject_ids": canonical_subject_ids,
                "motion_affordance_subject_ids": list(dict.fromkeys(
                    value for interaction in beat.get("interaction_contracts") or []
                    if isinstance(interaction, dict)
                    for value in (interaction.get("tool_subject_id"),
                                  interaction.get("target_subject_id")) if value
                )),
                "whole_boards_allowed": True,
                "whole_boards_required": True,
                "supplemental_references_replace_canonical_boards": False,
                "h3_reference_image_limit": 9,
                "on_reference_limit_exceeded": (
                    "block and consolidate upstream; never silently omit a relevant canonical sheet"
                ),
            },
            "supplemental_reference_plan": interaction_reference_plan,
            "lighting_contract": lighting_contract,
            "camera": camera,
            "camera_policy": camera_policy,
            "frame_size": frame_size,
            "composition": composition,
            "performance": performance,
            "atomicity": {
                **beat.get("_stage04_atomization", {}),
                "compiled_action_units": units,
                "one_primary_action_per_shot": units == 1,
                "on_unresolved": (
                    "add explicit stage03 sub_beats or approve a manual split before stage05"
                ),
            },
            "state_pair": {"start_state_id": start_id,
                           "end_state_id": end_id if exact else None,
                           "end_state_usage": "qa_target_only" if exact else None,
                           "target_end_state_description": end_text,
                           "changing_variable": allowed[0],
                           "invariants": invariants,
                           "allowed_change": allowed,
                           "reference_locks": reference_locks,
                           "geometry_locks": geometry_locks},
            "motion_control": {
                "representation": "semantic tracks compiled to H3 text/image anchors and used again for QA",
                "direct_h3_trajectory_input": False,
                "anchor_policy": anchor_policy,
                "motion_class": motion_class,
                "action_units": units,
                "exact_motion_required": exact,
                "subject_tracks": _track(beat, chars, depicted_objects, motion_class, exact),
                "change_budget": {"minimum": "primary visible change is unmistakable",
                                  "maximum": "no change outside allowed_change masks",
                                  "wrong_direction_allowed": False},
                "screen_direction_contract": direction_contract,
                "guide_plan": guide_plan,
                "guide_rule": "each guide must be a genuinely different observable state; never repeat one still",
            },
            "candidate_policy": _candidate_policy(route, exact, fast_track),
            "plate_candidate_policy": {
                "strategy": "sequential_ai_review",
                "start_candidates": 1,
                "shared_harness_schema": HARNESS_SCHEMA,
                "max_attempts": MAX_GENERATION_ATTEMPTS,
                "stop_on_ai_pass": True,
                "vary_every_retry": True,
                "variation_strategies": list(VARIATION_STRATEGIES),
                "retry_prompt_policy": (
                    "preserve the complete structured base prompt and append only "
                    "criterion-scoped corrections from the preceding AI review"
                ),
                "exhaustion_policy": "use_attempt_10_for_human_review",
                "ai_preflight_required": True,
                "human_final_review_required": not fast_track,
                "select_start_before_end_generation": False,
                "end_edits_per_selected_start": 0,
                "last_frame_policy": "disabled_in_production",
                "pair_selection": "not applicable; production does not generate an end plate",
                "end_generation_preconditions": [],
                "auto_promotion_allowed": fast_track,
                "review_mode": "ai_fast_track" if fast_track else "human",
                "fast_track_attempt_10_policy": (
                    "record_non_safety_accepted_defects_and_continue"
                    if fast_track else None
                ),
            },
            "plate_acceptance": {
                "start": [
                    "the requested action has visibly not begun",
                    "there is clear screen-space and pose-space room to perform the action",
                    "all required subjects and interaction targets are visible",
                ],
                "end": [
                    "the one primary visible change is unmistakably complete",
                    "no next action or invented event has begun",
                ],
                "pair": [
                    ("identical camera viewpoint, crop, focal character and background geometry"
                     if camera_policy == "locked" else
                     "start/end viewpoints follow the declared continuous camera path; world-space "
                     "architecture, furniture and lighting identity remain coherent"),
                    "identity, wardrobe, body proportions, object geometry, count and lighting direction match",
                    "reference_locks and geometry_locks match the selected start plate",
                    "every changed pixel region is explainable by allowed_change, contact shadow or revealed background",
                ],
                "on_fail": "reject the start plate and regenerate stage05; never compensate with a longer H3 prompt",
            },
            "motion_prompt": (
                _prompt(camera, camera_policy, performance, invariants, allowed, end_text,
                        motion_clauses, geometry_locks, direction_contract,
                        canonical_subject_ids, interaction_reference_plan,
                        lighting_contract)
                + "\n" + _temporal_prompt(temporal)
            ),
            "audio_policy": {
                **(contract.get("audio") or {}),
                "h3_native_audio": "discard",
            },
            "clauses": {"plate": plate_ids, "motion": motion_ids},
            "source_beat": {"what_happens": beat.get("what_happens", ""),
                            "why_this_long": beat.get("why_this_long", "")},
        }
        shots.append(shot)

    return {
        "schema_version": SCHEMA_VERSION,
        "generation_harness": harness_contract(
            "stage04_shot_design",
            _sha(scenario),
            (
                "semantic check has no form problems",
                "timeline shot contributions satisfy the Stage 1 runtime contract",
                "capture duration and edit duration remain separate",
                "prompts preserve declared subjects, geometry, camera and state contracts",
                "stage05 handoff contains no unresolved production blocker owned by stage04",
            ),
            exhaustion_policy="report_attempt_10_with_unresolved_terminal_findings",
            execution_mode=execution_mode["mode"],
        ) | {"attempts": []},
        "design_id": f"{contract.data['contract_id']}-SHOT-DESIGN",
        "created_at": _now(),
        "created_by": "LLM directorial plan plus deterministic stage04 production compiler",
        "directorial_plan_schema": directorial_plan.get("schema_version"),
        "directorial_plan_sha256": _sha(directorial_plan),
        "directorial_plan_legacy_adapter": bool(directorial_plan.get("legacy_adapter")),
        "source_scenario": f'{contract.stage_for("scenario", "03-scenario")}/output/scenario.json',
        "source_scenario_sha256": _sha(scenario),
        "contract": contract.receipt_block(stage_name(contract)),
        "engine_policy": {
            "video_engine": PROFILE_ID,
            "other_video_engines_allowed": False,
            "routes": sorted(H3_ROUTES),
            "principle": "route selection changes H3 conditioning, never the video engine",
        },
        "reference_status": source["reference_status"],
        "reference_fulfillment_plan": reference_fulfillment,
        "upstream_status": {
            "premise_state": source["premise_state"],
            "direction_impact": source["direction_impact"],
            "production_allowed": bool(source["direction_impact"].get("downstream_allowed", True)),
        },
        "states": states,
        "shots": shots,
        "total_edit_seconds": sum(float(s["timeline_edit_seconds"]) for s in shots),
        "total_planned_capture_seconds": sum(
            float((s.get("temporal_design") or {}).get("native_seconds") or 0) for s in shots),
        "runtime_contract": contract.runtime_contract,
        "execution_mode": execution_mode,
        "human_gate": {
            "required": not fast_track,
            "auto_approve_allowed": fast_track,
            "resolution_mode": "ai_fast_track" if fast_track else "human",
            "transition_to_stage05_requires_human_confirmation": False,
            "review_after": (
                "stage05 start plates exist and stage06 candidate contact sheets exist"
            ),
            "dimensions": [
                "composition_pov", "performance", "continuity",
                "supplemental_reference_necessity", "interaction_manual_physical_validity",
            ],
        },
    }


def _problem(problems: list[dict], shot_id: str | None, code: str, message: str) -> None:
    problems.append({"shot_id": shot_id, "code": code, "message": message})


def check(payload: dict, contract: Contract, scenario: dict | None = None) -> dict:
    problems: list[dict] = []
    warnings: list[dict] = []
    shots, states = payload.get("shots") or [], payload.get("states") or {}
    scenario_beats = {beat.get("id"): beat for beat in (scenario or {}).get("beats", [])}
    for scene in iter_scenes(scenario or {}):
        scenario_beats.setdefault(scene.get("id"), scene)
        for event in scene.get("events") or []:
            scenario_beats.setdefault(event.get("id"), scene)
    reference_inventory = payload.get("reference_status") or {}
    if payload.get("schema_version") != SCHEMA_VERSION:
        _problem(problems, None, "schema-version", f"{SCHEMA_VERSION} 필요")
    engine = payload.get("engine_policy") or {}
    if engine.get("video_engine") != PROFILE_ID or engine.get("other_video_engines_allowed") is not False:
        _problem(problems, None, "engine-policy", "영상 엔진은 H3 프로파일 하나로 고정되어야 한다")

    ids = [s.get("shot_id") for s in shots]
    if len(ids) != len(set(ids)) or any(not sid for sid in ids):
        _problem(problems, None, "shot-ids", "shot_id 누락 또는 중복")
    total = 0.0
    beat_ids = []
    for shot in shots:
        sid = shot.get("shot_id", "?")
        beat_ids.append(shot.get("beat_id"))
        seconds = shot.get("edit_seconds")
        if not isinstance(seconds, (int, float)) or isinstance(seconds, bool) or seconds <= 0:
            _problem(problems, sid, "duration", "edit_seconds는 양수여야 한다")
        else:
            total += float(shot.get("timeline_edit_seconds", seconds))

        temporal = shot.get("temporal_design") or {}
        if temporal:
            if temporal.get("temporal_mode") not in TEMPORAL_MODES:
                _problem(problems, sid, "temporal-mode",
                         f"지원 temporal mode 아님: {temporal.get('temporal_mode')}")
            if temporal.get("execution_method") not in TEMPORAL_EXECUTION_METHODS:
                _problem(problems, sid, "temporal-execution",
                         f"지원 execution method 아님: {temporal.get('execution_method')}")
            if not str(temporal.get("dramatic_reason") or "").strip():
                _problem(problems, sid, "temporal-reason", "temporal dramatic_reason이 없다")
            if temporal.get("capability_debt"):
                warnings.append({"shot_id": sid, "code": "temporal-capability-debt",
                                 "message": "; ".join(temporal["capability_debt"])})

        camera = shot.get("camera") or {}
        for part in CAMERA_PARTS:
            if not camera.get(part):
                _problem(problems, sid, f"camera-{part}", f"camera.{part} 없음")
        named = [name for name in MOVEMENTS if name in str(camera.get("movement", ""))]
        if len(named) != 1:
            _problem(problems, sid, "camera-movement", f"카메라 무브먼트는 정확히 하나여야 한다: {named}")
        if camera.get("angle") not in ANGLES:
            _problem(problems, sid, "camera-angle", f"지원 angle 아님: {camera.get('angle')}")
        if shot.get("frame_size") not in SIZES:
            _problem(problems, sid, "frame-size", f"지원 frame_size 아님: {shot.get('frame_size')}")
        if shot.get("composition") not in COMPOSITIONS:
            _problem(problems, sid, "composition", f"지원 composition 아님: {shot.get('composition')}")
        cast_count = len([
            item for item in shot.get("cast_presence") or []
            if isinstance(item, dict) and item.get("subject_id")
        ])
        if cast_count == 2 and shot.get("composition") not in {"투샷", "오버 더 숄더"}:
            _problem(
                problems, sid, "cast-composition",
                "두 인물이 보이는 shot은 투샷 또는 명시적인 오버 더 숄더 구도여야 한다",
            )
        if cast_count == 3 and shot.get("composition") != "쓰리샷":
            _problem(problems, sid, "cast-composition",
                     "세 인물이 보이는 shot은 쓰리샷이어야 한다")
        if cast_count < 2 and shot.get("composition") in {"투샷", "쓰리샷", "오버 더 숄더"}:
            _problem(problems, sid, "cast-composition",
                     "투샷·쓰리샷·오버 더 숄더에는 그 구도를 구성할 cast가 필요하다")

        route = (shot.get("h3_generation") or {}).get("route")
        if route not in H3_ROUTES:
            _problem(problems, sid, "h3-route", f"H3 route 아님: {route}")
        anchor_policy = (shot.get("h3_generation") or {}).get("anchor_policy")
        if anchor_policy != "first_only":
            _problem(problems, sid, "anchor-policy",
                     "production H3 anchor_policy는 first_only여야 한다")
        policy = shot.get("camera_policy")
        if policy not in CAMERA_POLICIES:
            _problem(problems, sid, "camera-policy", f"camera policy 오류: {policy}")
        motion = shot.get("motion_control") or {}
        if motion.get("direct_h3_trajectory_input") is not False:
            _problem(problems, sid, "false-control-claim", "semantic track을 H3 직접 입력으로 표시할 수 없다")
        if motion.get("motion_class") not in MOTION_CLASSES:
            _problem(problems, sid, "motion-class", f"motion_class 오류: {motion.get('motion_class')}")
        if motion.get("exact_motion_required"):
            if route != "i2v":
                _problem(problems, sid, "exact-route",
                         "정확 동작도 production에서는 first-only i2v를 사용한다")
            transit = bool((motion.get("screen_direction_contract") or {}).get("required"))
            if not transit and policy != "locked":
                _problem(problems, sid, "exact-camera",
                         "비이동 정밀 동작은 비교 가능한 locked camera가 필요하다")
            if transit and policy not in {"natural", "soft_follow", "directed", "locked"}:
                _problem(problems, sid, "transit-camera",
                         "이동 shot은 natural/soft_follow/directed/locked 중 하나여야 한다")
            if not motion.get("subject_tracks"):
                _problem(problems, sid, "track-missing", "정확 동작의 semantic track이 없다")
        retry_policy = shot.get("candidate_policy") or {}
        if (int(retry_policy.get("candidate_count", 0)) != 1
                or int(retry_policy.get("max_attempts", 0)) != MAX_GENERATION_ATTEMPTS
                or retry_policy.get("strategy") != "one_take_then_review_append_retry"):
            _problem(problems, sid, "candidate-policy",
                     "모든 shot은 C01 한 take만 먼저 만들고 실패 시에만 C10까지 추가한다")
        atomicity = shot.get("atomicity") or {}
        if (motion.get("exact_motion_required") and
                (int(motion.get("action_units", 1)) > 1 or
                 atomicity.get("manual_segmentation_required"))):
            warnings.append({
                "shot_id": sid,
                "code": "manual-atomic-segmentation-required",
                "message": (
                    "한 문장 안의 복합 동작을 안전하게 분해할 stage03 sub_beats가 없다. "
                    "stage05 전에 sub_beats 추가 또는 사람의 원자 샷 분할 승인이 필요하다"
                ),
            })

        # A verbal contact instruction cannot rescue an impossible reference
        # image. New stage03 interaction contracts therefore carry measurable
        # fit and axis facts. Historical beats without a contract remain
        # warning-compatible; once a contract exists, stage05/H3 is blocked if
        # the geometry is absent or physically contradictory.
        for interaction in shot.get("interaction_contracts") or []:
            if not isinstance(interaction, dict):
                _problem(problems, sid, "interaction-contract-form",
                         "interaction contract은 JSON object여야 한다")
                continue
            missing_common = [field for field in (
                "target_subject_id", "target_part_id", "fixed_part_ids",
                "moving_part_ids", "result_state"
            ) if not interaction.get(field)]
            if missing_common:
                _problem(problems, sid, "interaction-common-contract",
                         f"대상·고정부·이동부·결과 명세가 없다: {missing_common}")
            interaction_type = interaction.get("interaction_type")
            if not interaction_type:
                interaction_type = "mechanical_tool_contact"
            if interaction_type == "articulated_mechanism":
                kinematic = interaction.get("kinematic_contract") or {}
                missing_kinematic = [field for field in (
                    "motion_type", "axis_or_track_part_id", "start_state", "mid_state", "end_state"
                ) if kinematic.get(field) in (None, "", [])]
                if missing_kinematic:
                    _problem(problems, sid, "interaction-kinematic-contract",
                             f"관절 기구의 축/트랙과 다상태가 없다: {missing_kinematic}")
                continue
            if interaction_type == "assembly_sequence":
                interface = interaction.get("interface_contract") or {}
                missing_interface = [field for field in (
                    "moving_part_id", "receiving_part_id", "alignment_relation",
                    "engagement_motion", "start_state", "mid_state", "end_state"
                ) if interface.get(field) in (None, "", [])]
                if missing_interface:
                    _problem(problems, sid, "interaction-interface-contract",
                             f"조립 인터페이스와 순서 상태가 없다: {missing_interface}")
                continue
            if interaction_type != "mechanical_tool_contact":
                _problem(problems, sid, "interaction-type",
                         f"지원하지 않는 interaction_type: {interaction_type}")
                continue
            if not interaction.get("tool_subject_id") or not interaction.get("tool_part_id"):
                _problem(problems, sid, "interaction-tool-contract",
                         "mechanical_tool_contact의 tool subject/part가 없다")
            fit = interaction.get("fit_contract") if isinstance(interaction, dict) else {}
            fit = fit or {}
            capacity = fit.get("tool_capacity_mm")
            extent = fit.get("target_extent_mm")
            minimum = fit.get("minimum_capacity_ratio")
            numeric_fit = all(isinstance(value, (int, float)) and not isinstance(value, bool)
                              for value in (capacity, extent, minimum))
            if (not fit.get("tool_capacity_part_id")
                    or not fit.get("target_extent_part_id")
                    or not numeric_fit or extent <= 0 or capacity / extent < minimum
                    or minimum < 1.15):
                _problem(
                    problems, sid, "interaction-fit-contract",
                    "도구 용량과 대상 치수를 같은 단위로 결속하고 실제 용량비가 1.15 이상이어야 한다",
                )
            axis = interaction.get("axis_contract") if isinstance(interaction, dict) else {}
            axis = axis or {}
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
                _problem(
                    problems, sid, "interaction-axis-contract",
                    "도구 작용면은 대상 축과 90도여야 하며 허용오차는 5도 이하여야 한다",
                )
            projection = (interaction.get("projection_contract")
                          if isinstance(interaction, dict) else {}) or {}
            if (projection.get("mechanical_truth_over_tool_hero_view") is not True
                    or projection.get("hero_three_quarter_tool_view_forbidden") is not True):
                _problem(
                    problems, sid, "interaction-projection-contract",
                    "도구가 잘 보이는 사선 구도보다 실제 접촉 기하를 우선해야 한다",
                )

        pair = shot.get("state_pair") or {}
        start_id, end_id = pair.get("start_state_id"), pair.get("end_state_id")
        if start_id not in states:
            _problem(problems, sid, "start-state", f"정의되지 않은 start state {start_id}")
        if motion.get("exact_motion_required") and end_id not in states:
            _problem(problems, sid, "end-state", f"정의되지 않은 end state {end_id}")
        if not pair.get("invariants") or not pair.get("allowed_change"):
            _problem(problems, sid, "change-contract", "invariants와 allowed_change가 모두 필요하다")
        if not pair.get("geometry_locks") or not pair.get("reference_locks"):
            _problem(problems, sid, "reference-locks", "구체적인 reference/geometry lock이 필요하다")
        legacy_locks = " ".join(str(item) for item in pair.get("geometry_locks") or [])
        if any(phrase in legacy_locks for phrase in (
                "tool bag silhouette", "zipper and pockets", "every visible tool")):
            _problem(
                problems, sid, "topic-specific-lock-leak",
                "주제 하드코딩 lock 대신 declared object/interaction 계약을 사용해야 한다",
            )

        orientation = (
            "Portrait" if contract.frame.height > contract.frame.width else
            "Landscape" if contract.frame.width > contract.frame.height else
            "Square"
        )
        frame_marker = (
            f"{orientation} production plate "
            f"({contract.frame.width}x{contract.frame.height} native frame)"
        )
        for state_id in (start_id, end_id):
            if not state_id or state_id not in states:
                continue
            state_prompt = str(states[state_id].get("prompt") or "")
            if frame_marker not in state_prompt:
                _problem(
                    problems, sid, "plate-frame-contract",
                    f"{state_id} prompt가 계약 frame 표기 '{frame_marker}'를 포함해야 한다",
                )

        source_beat = scenario_beats.get(shot.get("beat_id"))
        if source_beat:
            char_ids = [
                item.get("subject_id") for item in shot.get("cast_presence") or []
                if isinstance(item, dict) and item.get("subject_id")
            ]
            clause_beat = dict(source_beat)
            clause_beat.update(shot.get("condition_flags") or {})
            _, expected_plate_clauses = _all_clause_text(
                contract, contract.stage_for("plate", "05-plate"), clause_beat, char_ids)
            _, expected_motion_clauses = _all_clause_text(
                contract, contract.stage_for("motion", "06-motion"), clause_beat, char_ids)
            if expected_motion_clauses not in str(shot.get("motion_prompt") or ""):
                _problem(problems, sid, "conditional-clause-branch",
                         "motion prompt의 조건절이 scenario beat 플래그와 다르다")
            if start_id in states and expected_plate_clauses not in str(
                    states[start_id].get("prompt") or ""):
                _problem(problems, sid, "conditional-clause-branch",
                         "plate prompt의 조건절이 scenario beat 플래그와 다르다")
        requirements = shot.get("reference_requirements") or {}
        canonical_ids = requirements.get("canonical_stage02_sheet_subject_ids") or []
        if (requirements.get("canonical_stage02_sheets_required") is not True
                or requirements.get("whole_boards_required") is not True
                or requirements.get("supplemental_references_replace_canonical_boards") is not False):
            _problem(
                problems, sid, "canonical-stage02-reference-policy",
                "관련 stage02 시트 전체는 stage05와 H3에 필수이며 보조 시트가 대체할 수 없다",
            )
        available_boards = reference_inventory.get("canonical_boards") or {}
        missing_boards = [subject_id for subject_id in canonical_ids
                          if subject_id not in available_boards]
        if missing_boards:
            item = {
                "shot_id": sid,
                "code": "canonical-stage02-board-missing",
                "message": f"shot에 필요한 stage02 시트가 없다: {missing_boards}",
            }
            # Stage 04 is a design artifact, so it may be compiled before the
            # canonical pixels are adopted.  The same absence remains a hard
            # production gate through plate_generation_allowed=false and the
            # references-not-production-ready warning below.  Treating it as
            # a form error here contradicted reference_status's explicit
            # design_without_pixels_allowed contract and prevented a clearly
            # labelled draft from existing at all.
            if reference_inventory.get("design_without_pixels_allowed") is True:
                warnings.append(item)
            else:
                problems.append(item)

        manual_plan = shot.get("supplemental_reference_plan") or {}
        if manual_plan.get("policy_version") != "interaction-manual.v1":
            _problem(problems, sid, "supplemental-reference-review-missing",
                     "보조 상호작용 시트 필요성 판정이 없다")
        elif manual_plan.get("required"):
            manuals = manual_plan.get("manuals") or []
            if not manuals:
                _problem(problems, sid, "interaction-manual-spec-missing",
                         "필수로 판정한 상호작용 설명서 시트 명세가 없다")
            for manual in manuals:
                panels = manual.get("panels") or []
                is_reference_debt = manual.get("manual_type") == "stage03_reference_debt"
                if (not is_reference_debt and
                        (len(panels) < 6 or len(set(item.get("view") for item in panels)) < 3
                         or len(set(item.get("state") for item in panels)) < 3)):
                    _problem(problems, sid, "interaction-manual-coverage",
                             "설명서 시트는 6패널, 3개 이상 시점, 3개 이상 상태가 필요하다")
                if (not is_reference_debt and
                        manual.get("required_stage02_sheet_subject_ids") != canonical_ids):
                    _problem(problems, sid, "interaction-manual-canonical-inputs",
                             "설명서 시트도 해당 shot의 stage02 시트 전체를 입력으로 받아야 한다")
                if not str(manual.get("draft_generation_prompt") or "").strip():
                    _problem(problems, sid, "interaction-manual-prompt",
                             "stage05용 설명서 이미지 생성 프롬프트가 없다")
                if manual.get("unresolved_contract_fields"):
                    warnings.append({
                        "shot_id": sid,
                        "code": "interaction-manual-spec-unresolved",
                        "message": (
                            f"{manual.get('manual_id')}의 상호작용 명세가 미해결이다: "
                            f"{manual.get('unresolved_contract_fields')}. stage03 계약 보완 전에 생성 금지"
                        ),
                    })
            warnings.append({
                "shot_id": sid,
                "code": "interaction-manual-stage05-approval-required",
                "message": "clean/annotated 설명서 보드를 stage05에서 생성·검증·사람 승인하기 전에는 H3 생성 금지",
            })
        elif manual_plan.get("manuals"):
            _problem(problems, sid, "interaction-manual-decision-conflict",
                     "불필요 판정과 manual 명세가 동시에 존재한다")

        manual_count = len(manual_plan.get("manuals") or [])
        if len(canonical_ids) + manual_count > int(requirements.get("h3_reference_image_limit", 9)):
            _problem(problems, sid, "h3-reference-limit",
                     "stage02 시트와 보조 설명서가 H3 레퍼런스 9장 한도를 넘는다")
        required_motion_refs = ((shot.get("reference_requirements") or {})
                                .get("motion_affordance_subject_ids") or [])
        available_motion_refs = reference_inventory.get("approved_motion_affordance_crops") or {}
        missing_motion_refs = [subject_id for subject_id in required_motion_refs
                               if not available_motion_refs.get(subject_id)]
        if missing_motion_refs and not manual_plan.get("required"):
            warnings.append({
                "shot_id": sid,
                "code": "motion-affordance-reference-missing",
                "message": (
                    "상호작용 part에 결속된 motion-safe 선택 크롭이 없다: "
                    f"{missing_motion_refs}. stage02 시트와 시작 이미지로 충분한지 재검토하고 "
                    "부족하면 interaction manual을 필수로 변경한다"
                ),
            })
        direction = motion.get("screen_direction_contract") or {}
        if direction.get("required") and direction.get("generation_blocked_until_resolved"):
            warnings.append({
                "shot_id": sid,
                "code": "screen-direction-annotation-required",
                "message": (
                    "장면 속 목적지만으로 화면 이동 방향을 정할 수 없다. 선택된 start plate에서 "
                    "start/end 정규화 좌표와 depth intent를 승인하기 전에는 end plate/H3 생성 금지"
                ),
            })

        guides = motion.get("guide_plan") or []
        progress = [item.get("progress") for item in guides]
        if not progress or progress != sorted(progress) or progress[0] != 0.0:
            _problem(problems, sid, "guide-order", "guide progress는 0부터 오름차순이어야 한다")
        if progress != [0.0] or any(item.get("state_role") != "start" for item in guides):
            _problem(problems, sid, "first-only-guides",
                     "production guide_plan에는 progress 0.0의 first_frame만 있어야 한다")
        state_ids = [item.get("state_id") for item in guides]
        if len(state_ids) != len(set(state_ids)):
            _problem(problems, sid, "repeated-guide", "같은 still을 guide로 반복할 수 없다")
        if not (shot.get("performance") or {}).get("action_timeline"):
            _problem(problems, sid, "performance", "보이는 연기 timeline이 없다")
        if not str(shot.get("motion_prompt", "")).strip():
            _problem(problems, sid, "motion-prompt", "H3 prompt가 없다")
        elif shot.get("temporal_design") and "TEMPORAL CONTRACT —" not in str(
                shot.get("motion_prompt")):
            _problem(problems, sid, "temporal-prompt",
                     "Stage 4 temporal design이 H3 prompt로 컴파일되지 않았다")
        if (shot.get("audio_policy") or {}).get("h3_native_audio") != "discard":
            _problem(problems, sid, "h3-audio-policy", "H3 원본 오디오는 폐기해야 한다")
        plate_policy = shot.get("plate_candidate_policy") or {}
        if (plate_policy.get("strategy") != "sequential_ai_review" or
                int(plate_policy.get("start_candidates", 0)) != 1 or
                int(plate_policy.get("max_attempts", 0)) != MAX_GENERATION_ATTEMPTS or
                plate_policy.get("stop_on_ai_pass") is not True or
                plate_policy.get("vary_every_retry") is not True or
                plate_policy.get("variation_strategies") != list(VARIATION_STRATEGIES) or
                plate_policy.get("exhaustion_policy") != "use_attempt_10_for_human_review"):
            _problem(
                problems, sid, "plate-retry-harness",
                f"stage05 start plate는 1장씩 AI 검수하며 총 {MAX_GENERATION_ATTEMPTS}회까지 "
                "서로 다르게 변주하고, 연속 실패 시 10회차를 사람 검수로 넘겨야 한다")
        if int(plate_policy.get("end_edits_per_selected_start", -1)) != 0:
            _problem(problems, sid, "end-plate-disabled",
                     "production에서는 end plate 후보를 생성하지 않는다")
        if plate_policy.get("last_frame_policy") != "disabled_in_production":
            _problem(problems, sid, "last-frame-policy",
                     "production last_frame_policy는 disabled_in_production이어야 한다")
        acceptance = shot.get("plate_acceptance") or {}
        if not acceptance.get("start") or not acceptance.get("pair") or not acceptance.get("on_fail"):
            _problem(problems, sid, "plate-acceptance", "H3 이전 stage05 acceptance gate가 없다")

        if shot.get("sublocation_id") == "unresolved":
            warnings.append({"shot_id": sid, "code": "sublocation-unresolved",
                             "message": "03-scenario가 sublocation을 주지 않았고 setting에 node가 여러 개라 사람 확인 필요"})

    expected_total = _runtime_target(contract)
    if expected_total is not None and abs(total - expected_total) > 0.05:
        _problem(problems, None, "total-duration",
                 f"timeline shot 합 {total:g}초, Stage 1 runtime {expected_total:g}초")
    if scenario is not None and scenario.get("beats"):
        expected_beats = [b.get("id") for b in scenario.get("beats", [])]
        actual_order = list(dict.fromkeys(beat_ids))
        if actual_order != expected_beats:
            _problem(problems, None, "beat-coverage",
                     f"scenario beat 순서/커버리지 불일치: {actual_order}")
        allocated = {bid: sum(float(s.get("edit_seconds", 0)) for s in shots
                              if s.get("beat_id") == bid) for bid in expected_beats}
        expected_allocated = {b.get("id"): float(b.get("seconds", 0))
                              for b in scenario.get("beats", [])}
        if allocated != expected_allocated:
            _problem(problems, None, "beat-duration-conservation",
                     f"분할 뒤 beat 시간 불일치: {allocated} 대 {expected_allocated}")
    elif scenario is not None and scenario.get("sequences"):
        scenario_scene_ids = [str(item.get("id")) for item in iter_scenes(scenario)]
        covered_scene_ids = list(dict.fromkeys(
            str(shot.get("scene_id")) for shot in shots if shot.get("scene_id")))
        if covered_scene_ids != scenario_scene_ids:
            _problem(problems, None, "scene-coverage",
                     f"scenario scene 순서/coverage 불일치: {covered_scene_ids} 대 {scenario_scene_ids}")

    refs = payload.get("reference_status") or {}
    if not refs.get("plate_generation_allowed"):
        warnings.append({"shot_id": None, "code": "references-not-production-ready",
                         "message": (
                             "04 설계는 유효하지만 관련 stage02 전체 시트가 존재하고 "
                             "semantic review가 승인되기 전에는 stage05 생성 금지"
                         )})
    upstream = payload.get("upstream_status") or {}
    if upstream and not upstream.get("production_allowed", True):
        warnings.append({"shot_id": None, "code": "upstream-revalidation-required",
                         "message": "기존 direction 영향 재검토가 남아 있어 설계 초안만 허용"})
    mode = (payload.get("execution_mode") or {}).get("mode", "normal")
    gate = payload.get("human_gate") or {}
    if mode == FAST_TRACK_MODE:
        if (gate.get("required") is not False or
                gate.get("auto_approve_allowed") is not True or
                gate.get("resolution_mode") != "ai_fast_track"):
            _problem(problems, None, "human-gate", "fast_track은 AI 자율 판정 계약이어야 한다")
    elif (gate.get("required") is not True or
          gate.get("auto_approve_allowed") is not False or
          gate.get("resolution_mode", "human") != "human"):
        _problem(problems, None, "human-gate", "normal mode는 사람 승인 계약이어야 한다")
    return {
        "schema_version": "shot-design-check.v1",
        "shots": len(shots),
        "states": len(states),
        "total_edit_seconds": round(total, 3),
        "h3_route_counts": {route: sum(
            1 for shot in shots if (shot.get("h3_generation") or {}).get("route") == route)
            for route in sorted(H3_ROUTES)},
        "warnings": warnings,
        "problems": problems,
        "form_ok": not problems,
        "production_ready": not problems and not warnings,
    }


def run(attempt: Path, force: bool = False) -> dict:
    contract = load_contract(attempt)
    gathered = gather(attempt, contract)
    target = stage_dir(attempt, contract) / "output" / "shot-cards.json"
    plan_path = stage_dir(attempt, contract) / "output" / "directorial-plan.json"
    scenario_is_current = gathered["scenario"].get("schema_version") == SCENARIO_SCHEMA
    if scenario_is_current:
        if plan_path.exists() and not force:
            directorial_plan = json.loads(plan_path.read_text(encoding="utf-8"))
            plan_report = check_directorial_plan(directorial_plan, gathered["scenario"], contract)
            if (not plan_report["ok"] or
                    directorial_plan.get("source_scenario_sha256") != _sha(gathered["scenario"])):
                directorial_plan = write_directorial_plan(attempt, contract, gathered)
        else:
            directorial_plan = write_directorial_plan(attempt, contract, gathered)
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(json.dumps(directorial_plan, ensure_ascii=False, indent=2),
                             encoding="utf-8")
        gathered["directorial_plan"] = directorial_plan
    if target.exists() and not force:
        payload = json.loads(target.read_text(encoding="utf-8"))
        current_mode = load_execution_mode(attempt)
        if (payload.get("schema_version") != SCHEMA_VERSION or
                payload.get("source_scenario_sha256") != _sha(gathered["scenario"]) or
                (payload.get("execution_mode") or {}).get("mode") != current_mode.get("mode") or
                (payload.get("execution_mode") or {}).get("set_at") != current_mode.get("set_at")):
            payload = compile_scenario(attempt, contract, gathered)
            target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        payload = compile_scenario(attempt, contract, gathered)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    report = check(payload, contract, gathered["scenario"])
    harness = payload.get("generation_harness") or {}
    if harness.get("schema_version") != HARNESS_SCHEMA:
        harness = harness_contract(
            "stage04_shot_design", _sha(gathered["scenario"]),
            (
                "semantic check has no form problems",
                "timeline shot contributions satisfy Stage 1 runtime",
                "capture length remains separate from edit contribution",
                "prompts preserve declared subjects, geometry, camera and state contracts",
                "stage05 handoff contains no unresolved production blocker owned by stage04",
            ),
            exhaustion_policy="report_attempt_10_with_unresolved_terminal_findings",
            execution_mode=load_execution_mode(attempt)["mode"],
        ) | {"attempts": []}
    attempts = list(harness.get("attempts") or [])
    if len(attempts) < MAX_GENERATION_ATTEMPTS and (force or not attempts):
        number = len(attempts) + 1
        failed = [str(item.get("message") or item.get("code") or item)
                  if isinstance(item, dict) else str(item)
                  for item in report.get("problems") or []]
        effective_contract = json.dumps({
            "source_scenario_sha256": payload.get("source_scenario_sha256"),
            "variation_strategy": variation_strategy(number),
            "repair_findings": failed,
        }, ensure_ascii=False, sort_keys=True)
        attempts.append(attempt_record(
            number, effective_contract, "pass" if not failed else "fail",
            "\n".join(failed), failed))
        harness["attempts"] = attempts
        payload["generation_harness"] = harness
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    qa = stage_dir(attempt, contract) / "qa" / "semantic-check.json"
    qa.parent.mkdir(parents=True, exist_ok=True)
    qa.write_text(json.dumps({"checked_at": _now(), "contract": contract.receipt_block(stage_name(contract)),
                              "source": str(target.relative_to(attempt)), **report},
                             ensure_ascii=False, indent=2), encoding="utf-8")
    receipt = stage_dir(attempt, contract) / "receipt.json"
    stage05_handoff = {
        "stage": contract.stage_for("plate", "05-plate"),
        "policy": "start_immediately_after_stage04_form_ok",
        "human_confirmation_required": False,
        "first_action": "run stage05 input audit, fulfill 5A references, then prepare 5B plates",
    } if report.get("form_ok") else None
    receipt.write_text(json.dumps({
        "schema_version": "shot-design-receipt.v1",
        "receipt_id": f"{contract.data['contract_id']}-SHOT-DESIGN",
        "created_at": _now(),
        "contract": contract.receipt_block(stage_name(contract)),
        "source_scenario": payload.get("source_scenario"),
        "source_scenario_sha256": payload.get("source_scenario_sha256"),
        "shot_cards_sha256": _sha(payload),
        "engine_policy": payload.get("engine_policy"),
        "reference_status": payload.get("reference_status"),
        "upstream_status": payload.get("upstream_status"),
        "check": report,
        "stage05_handoff": stage05_handoff,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"path": str(target), "qa": str(qa), "receipt": str(receipt),
            "stage05_handoff": stage05_handoff, **report}


def audit_existing(attempt: Path) -> dict:
    contract = load_contract(attempt)
    target = stage_dir(attempt, contract) / "output" / "shot-cards.json"
    if not target.exists():
        raise ShotDesignError(f"기존 shot cards가 없다: {target}")
    payload = json.loads(target.read_text(encoding="utf-8"))
    scenario_path = attempt / contract.stage_for("scenario", "03-scenario") / "output" / "scenario.json"
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    return check(payload, contract, scenario)


def main() -> int:
    parser = argparse.ArgumentParser(description="03 scenario를 H3-only shot cards로 컴파일")
    parser.add_argument("attempt", type=Path)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--audit-only", action="store_true")
    args = parser.parse_args()
    try:
        result = audit_existing(args.attempt) if args.audit_only else run(args.attempt, args.force)
    except (ShotDesignError, ContractError) as error:
        print(json.dumps({"form_ok": False, "problem": str(error)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("form_ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
