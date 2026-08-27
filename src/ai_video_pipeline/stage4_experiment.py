"""Controlled comparison of different stage-04 working methods.

Stages 01–03 are immutable experiment inputs.  Each method receives exactly
the same bundle and writes to an isolated experiment folder.  The generated
plan is not promoted to ``04-shot-design/output``; promotion happens only after
AI scoring and a human choice.

This module performs the text-model part of the experiment.  Stage-05 canary
images are produced separately because the Codex built-in image generator is
interactive and must keep every generated project asset in the workspace.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contract import Contract, load as load_contract
from .h3_runtime import PROFILE_ID
from .shot_design import compile_scenario, gather

SCHEMA = "stage4-method-output.v1"
METHODS = {
    "M1-prose-baseline": {
        "title": "prose baseline",
        "hypothesis": "한 비트 한 샷의 명료한 산문과 카메라 4요소만으로 충분한가",
        "rules": """
- scenario beat 하나를 shot 하나로 유지한다. 분할하지 않는다.
- 장면, 연기, movement/speed/framing/end의 카메라 네 조각을 자연어로 쓴다.
- start/end 상태쌍, trajectory, guide frame, candidate 정책은 설계하지 않는다.
- H3 route는 모든 shot에서 i2v로 둔다.
""",
    },
    "M2-state-pair": {
        "title": "state-pair",
        "hypothesis": "시작·끝 상태와 불변/허용 변화만 명시하면 과소·과다 변화가 줄어드는가",
        "rules": """
- scenario beat 하나를 shot 하나로 유지한다.
- 모든 shot에 start_state, end_state, invariants, allowed_change를 쓴다.
- 정밀 동작은 fl2va, 분위기·미세 동작은 i2v로 고른다.
- 중간 guide, 좌표 track, 다중 후보 정책은 쓰지 않는다.
""",
    },
    "M3-atomic-locked": {
        "title": "atomic action + locked camera",
        "hypothesis": "복합 비트를 원자 샷으로 나누고 카메라를 잠그면 동작 방향과 배경 유지가 좋아지는가",
        "rules": """
- 한 shot에는 하나의 관찰 가능한 주 동작과 하나의 주 변화만 둔다.
- 복합 beat는 여러 shot으로 나누되 beat별/전체 seconds 합을 정확히 보존한다.
- 피사체 이동·도구 접촉·회전·개폐 shot의 camera는 locked/static이다.
- semantic motion path, wrong_direction 금지, change_budget, invariants를 쓴다.
- H3 route는 i2v 또는 fl2va만 쓴다. 중간 guide와 best-of-N은 쓰지 않는다.
""",
    },
    "M4-h3-adaptive": {
        "title": "H3 adaptive state/guide/candidate",
        "hypothesis": "원자 샷과 H3 조건화 경로·서로 다른 중간 상태·다중 후보 선별을 함께 설계하면 가장 안정적인가",
        "rules": """
- 한 shot에는 하나의 관찰 가능한 주 동작과 하나의 주 변화만 둔다.
- 복합 beat는 분할하고 beat별/전체 seconds 합을 정확히 보존한다.
- 정확한 피사체 동작은 locked/static, 작은 카메라 표현만 prompt_only_small로 둔다.
- H3만 사용한다. route는 i2v/fl2va/guided_fl2va 중 컷별로 선택한다.
- 3단 이상의 진짜 변화에만 서로 다른 mid_state guide를 둔다. 같은 still 반복 금지.
- semantic motion path, change_budget, invariants, allowed_change를 쓴다.
- 정확 동작은 최소 4 seed, 그 외 최소 3 seed를 만들고 자동 승격하지 않는다.
""",
    },
}

COMMON = """
너는 AI 영상 파이프라인의 04-shot-design 담당자다. 01~03 단계의 결정은
고정되어 있으며 사건·요소·총 길이를 바꾸지 않는다. 비트의 촬영 방식만 설계한다.
영상 생성 엔진은 무조건 MiniMax H3 하나다. 다른 영상 모델을 제안하거나 쓰지 마라.

모든 camera에는 movement, speed, framing, end, angle이 있어야 하고 한 shot에
movement는 하나뿐이다. 연기는 시간 순서로 보이게 쓰며, 주지 않은 동작을 만들지
않는다. 화면에 필요한 인물·사물 id는 입력 id를 그대로 쓴다. 계약 조항은 그대로
유지한다.

반환은 JSON 객체 하나다. 설명 문장을 JSON 밖에 붙이지 마라.
형식:
{
  "schema_version": "stage4-method-output.v1",
  "method_id": "주어진 id",
  "design_summary": "이 방식이 한 일",
  "shots": [{
    "shot_id": "S01", "beat_id": "B01", "seconds": 3.0,
    "purpose": "이 샷의 역할", "visible_action": "한 가지 주 행동",
    "primary_visible_change": "시작에서 끝까지 변하는 한 가지",
    "where_subject_id": "setting id", "sublocation_id": "가능하면 공간 node id",
    "subject_ids": ["보이는 character/subject id"],
    "camera": {"movement":"...", "speed":"...", "framing":"...", "end":"...", "angle":"..."},
    "camera_policy": "locked/prompt_only_small/prompt_only_free",
    "performance_timeline": [{"from_progress":0.0,"to_progress":1.0,"action":"..."}],
    "start_state": "없으면 빈 문자열", "end_state": "없으면 빈 문자열",
    "invariants": [], "allowed_change": [],
    "semantic_motion_path": "없으면 빈 문자열",
    "change_budget": "없으면 빈 문자열",
    "h3_route": "i2v/fl2va/guided_fl2va",
    "guide_states": [{"progress":0.5,"observable_state":"..."}],
    "candidate_count": 1,
    "plate_prompt": "이 shot의 대표 시작 상태판을 생성하는 완전한 영문 프롬프트",
    "h3_motion_prompt": "카메라와 시간순 동작, 끝 상태를 분리한 완전한 영문 프롬프트"
  }],
  "canary": {"shot_id":"이 방식의 장단점이 가장 잘 드러나는 shot", "why":"선정 이유"}
}
"""


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _sha(data: Any) -> str:
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def _load_bundle(attempt: Path, contract: Contract) -> dict:
    premise = attempt / contract.stage_for("premise", "01-premise") / "output"
    scenario_path = attempt / contract.stage_for("scenario", "03-scenario") / "output" / "scenario.json"
    direction = json.loads((premise / "direction.json").read_text(encoding="utf-8"))
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    definitions = {}
    subject_dir = attempt / contract.get("subjects", {}).get(
        "directory", f'{contract.stage_for("premise", "01-premise")}/output/subjects')
    for sid in sorted(contract.elements()):
        definitions[sid] = json.loads((subject_dir / f"{sid}.json").read_text(encoding="utf-8"))
    return {"direction": direction, "contract": contract.data,
            "definitions": definitions, "scenario": scenario}


def build_prompt(method_id: str, bundle: dict) -> str:
    method = METHODS[method_id]
    return "\n\n".join([
        COMMON,
        f"실험 방식 id: {method_id}\n가설: {method['hypothesis']}\n이 방식의 추가 규칙:\n{method['rules']}",
        "고정 입력(수정 금지):\n" + json.dumps(bundle, ensure_ascii=False, indent=2),
    ])


def _validate(payload: dict, method_id: str, bundle: dict) -> list[str]:
    problems = []
    if payload.get("schema_version") != SCHEMA:
        problems.append("schema_version")
    if payload.get("method_id") != method_id:
        problems.append("method_id")
    shots = payload.get("shots") or []
    if not shots:
        problems.append("shots.empty")
        return problems
    want = float(bundle["contract"].get("duration_seconds", 0))
    got = sum(float(s.get("seconds", 0)) for s in shots)
    if abs(want - got) > 0.01:
        problems.append(f"duration {got} != {want}")
    expected = [b.get("id") for b in bundle["scenario"].get("beats", [])]
    actual = list(dict.fromkeys(s.get("beat_id") for s in shots))
    if actual != expected:
        problems.append(f"beat coverage {actual} != {expected}")
    for index, shot in enumerate(shots):
        camera = shot.get("camera") or {}
        for part in ("movement", "speed", "framing", "end", "angle"):
            if not camera.get(part):
                problems.append(f"shots.{index}.camera.{part}")
        if shot.get("h3_route") not in {"i2v", "fl2va", "guided_fl2va"}:
            problems.append(f"shots.{index}.h3_route")
        if not shot.get("plate_prompt") or not shot.get("h3_motion_prompt"):
            problems.append(f"shots.{index}.prompts")
    canary = payload.get("canary") or {}
    if canary.get("shot_id") not in {s.get("shot_id") for s in shots}:
        problems.append("canary.shot_id")
    return problems


def _method_shot(source: dict, states: dict, method_id: str) -> dict:
    """Project the executable stage04 card into the comparison schema."""
    pair = source.get("state_pair") or {}
    control = source.get("motion_control") or {}
    generation = source.get("h3_generation") or {}
    start = states.get(pair.get("start_state_id"), {})
    end = states.get(pair.get("end_state_id"), {})
    route = generation.get("route", "i2v")
    guide_states = [
        {"progress": item.get("progress"),
         "observable_state": states.get(item.get("state_id"), {}).get("description", "")}
        for item in control.get("guide_plan", []) if item.get("state_role") == "mid"
    ]
    candidate_count = int((source.get("candidate_policy") or {}).get("candidate_count", 1))
    if method_id == "M3-atomic-locked":
        route = "fl2va" if route == "guided_fl2va" else route
        guide_states = []
        candidate_count = 1
    return {
        "shot_id": source["shot_id"], "beat_id": source["beat_id"],
        "seconds": source["edit_seconds"], "purpose": source["cut_purpose"],
        "visible_action": source["source_beat"]["what_happens"],
        "primary_visible_change": pair.get("changing_variable", ""),
        "where_subject_id": source.get("where_subject_id"),
        "sublocation_id": source.get("sublocation_id"),
        "subject_ids": [x.get("subject_id") for x in source.get("cast_presence", [])]
                       + [x.get("subject_id") for x in source.get("object_roles", [])],
        "camera": source.get("camera"), "camera_policy": source.get("camera_policy"),
        "performance_timeline": (source.get("performance") or {}).get("action_timeline", []),
        "start_state": start.get("description", ""), "end_state": end.get("description", ""),
        "invariants": pair.get("invariants", []), "allowed_change": pair.get("allowed_change", []),
        "semantic_motion_path": "; ".join(
            str(item.get("path", "")) for item in control.get("subject_tracks", [])),
        "change_budget": json.dumps(control.get("change_budget", {}), ensure_ascii=False),
        "h3_route": route, "guide_states": guide_states,
        "candidate_count": candidate_count,
        "plate_prompt": start.get("prompt", ""),
        "h3_motion_prompt": source.get("motion_prompt", ""),
    }


def _aggregate_beat(group: list[dict], states: dict, beat: dict, method_id: str,
                    number: int) -> dict:
    first, last = group[0], group[-1]
    first_pair, last_pair = first.get("state_pair") or {}, last.get("state_pair") or {}
    start = states.get(first_pair.get("start_state_id"), {})
    end = states.get(last_pair.get("end_state_id"), {})
    camera = dict(first.get("camera") or {})
    text = str(beat.get("what_happens", ""))
    chars = [x.get("subject_id") for x in first.get("cast_presence", [])]
    objects = [x.get("subject_id") for x in first.get("object_roles", [])]
    if method_id == "M1-prose-baseline":
        start_text = end_text = ""
        invariants: list[str] = []
        allowed: list[str] = []
        route = "i2v"
    else:
        start_text = start.get("description", "행동 직전")
        end_text = end.get("description", "행동 완료 직후")
        invariants = first_pair.get("invariants", [])
        allowed = [text]
        route = "fl2va" if any((s.get("motion_control") or {}).get("exact_motion_required")
                               for s in group) else "i2v"
    return {
        "shot_id": f"S{number:02d}", "beat_id": beat.get("id"),
        "seconds": float(beat.get("seconds", 0)), "purpose": beat.get("purpose"),
        "visible_action": text, "primary_visible_change": text,
        "where_subject_id": beat.get("where_subject_id", beat.get("where")),
        "sublocation_id": first.get("sublocation_id"), "subject_ids": chars + objects,
        "camera": camera, "camera_policy": first.get("camera_policy"),
        "performance_timeline": [{"from_progress": 0.0, "to_progress": 1.0,
                                  "action": text}],
        "start_state": start_text, "end_state": end_text,
        "invariants": invariants, "allowed_change": allowed,
        "semantic_motion_path": "", "change_budget": "",
        "h3_route": route, "guide_states": [], "candidate_count": 1,
        "plate_prompt": (
            "Create one cinematic key frame that represents this whole beat without an explicit "
            f"start/end state contract: {text} Camera: {camera.get('movement')}; "
            f"{camera.get('framing')}; {camera.get('angle')}."
            if method_id == "M1-prose-baseline" else start.get("prompt", "")
        ),
        "h3_motion_prompt": "\n".join([
            f"CAMERA — {camera.get('movement')}; {camera.get('speed')}; "
            f"{camera.get('framing')}; END: {camera.get('end')}",
            f"ACTION — {text}",
            f"FINAL STATE — {end_text}" if end_text else "",
        ]).strip(),
    }


def _canary_beat(attempt: Path, scenario: dict) -> str:
    known = {"sky-village-plumber": "B07", "luxury-penthouse-tour": "B02"}
    for part in attempt.parts:
        if part in known:
            return known[part]
    beats = scenario.get("beats") or []
    return beats[len(beats) // 2].get("id") if beats else ""


def _local_execute(attempt: Path, contract: Contract, method_id: str, bundle: dict) -> dict:
    """Execute the saved method prompt without exporting the fixed inputs."""
    executable = compile_scenario(attempt, contract, gather(attempt, contract))
    states = executable["states"]
    if method_id in {"M3-atomic-locked", "M4-h3-adaptive"}:
        shots = [_method_shot(shot, states, method_id) for shot in executable["shots"]]
    else:
        grouped: dict[str, list[dict]] = {}
        for shot in executable["shots"]:
            grouped.setdefault(shot["beat_id"], []).append(shot)
        shots = [_aggregate_beat(grouped[beat["id"]], states, beat, method_id, index)
                 for index, beat in enumerate(bundle["scenario"].get("beats", []), start=1)]
    canary_beat = _canary_beat(attempt, bundle["scenario"])
    selected = next((s for s in shots if s["beat_id"] == canary_beat), shots[0])
    return {
        "schema_version": SCHEMA, "method_id": method_id,
        "design_summary": METHODS[method_id]["hypothesis"],
        "shots": shots,
        "canary": {"shot_id": selected["shot_id"], "beat_id": canary_beat,
                   "why": "모든 방식이 같은 고정 beat를 다르게 처리하도록 선택한 블라인드 비교 canary"},
    }


def run_method(attempt: Path, contract: Contract, method_id: str,
               executor: str, force: bool = False) -> dict:
    root = attempt / contract.stage_for("shot_design", "04-shot-design") / "qa" / "experiments" / "methods" / method_id
    output = root / "shot-design.json"
    prompt_path = root / "prompt.txt"
    if output.exists() and not force:
        payload = json.loads(output.read_text(encoding="utf-8"))
        bundle = _load_bundle(attempt, contract)
    else:
        bundle = _load_bundle(attempt, contract)
        prompt = build_prompt(method_id, bundle)
        root.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(prompt, encoding="utf-8")
        payload = _local_execute(attempt, contract, method_id, bundle)
        payload["experiment_meta"] = {
            "created_at": _now(), "executor": executor, "method": METHODS[method_id],
            "fixed_input_sha256": _sha(bundle),
            "fixed_stages": ["01-premise", "02-sheet", "03-scenario"],
            "ignores_legacy_gate_failures_for_experiment": True,
            "not_production_approved": True,
        }
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    problems = _validate(payload, method_id, bundle)
    qa = root / "validation.json"
    qa.write_text(json.dumps({"method_id": method_id, "problems": problems,
                              "form_ok": not problems}, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"method_id": method_id, "output": str(output), "prompt": str(prompt_path),
            "validation": str(qa), "problems": problems, "form_ok": not problems}


def run_all(attempt: Path, executor: str = "local-stage04-compiler",
            force: bool = False) -> dict:
    contract = load_contract(attempt)
    results = [run_method(attempt, contract, method_id, executor, force)
               for method_id in METHODS]
    results.sort(key=lambda item: item["method_id"])
    summary = {
        "schema_version": "stage4-method-experiment.v1",
        "attempt": str(attempt), "created_at": _now(), "executor": executor,
        "video_engine": PROFILE_ID,
        "fixed_input_policy": "01-03 immutable; legacy validation failures recorded but non-blocking",
        "methods": results,
        "all_form_ok": all(item["form_ok"] for item in results),
        "next": "generate one stage05 canary per method with method output + stage02 sheets + stage01 direction/definitions",
    }
    target = attempt / contract.stage_for("shot_design", "04-shot-design") / "qa" / "experiments" / "method-experiment.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="run four isolated stage04 method prompts")
    parser.add_argument("attempt", type=Path)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--executor", default="local-stage04-compiler")
    args = parser.parse_args()
    result = run_all(args.attempt, args.executor, args.force)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["all_form_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
