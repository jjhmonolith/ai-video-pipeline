"""01-premise: turn one line of direction into the cast, the subject and the world.

This stage used to be two. A brief declared terms, and a research stage copied
facts out of a shared topic folder that had no origin of its own, so the stage
meant to establish what a film is about established nothing and the two halves
could disagree without anyone noticing.

Merged, the job is one job: take the direction, find out what would make it
plausible, decide what things are, and write down who decided and on what.

Three artefacts come out and they are different in kind.

`contract.json` is the promise. Frame, image roles, forbidden clauses. It says
nothing about cars because it holds only what survives a change of subject.

`subjects/*.json` are the definitions, and this stage owns their shape as well
as their values. Deciding that a vehicle has a redline is part of deciding what
the vehicle is; a stage cannot be handed a schema by someone who has not looked
yet. Each carries provenance and cites the evidence it leaned on.

`evidence/*.json` are the searches. For a film about something real this is
sourcing. For a film about something invented it is still worth doing, because
invention has to land inside the plausible, and `basis` has nothing to say
otherwise.

The stage runs without asking anyone. It reads the direction, searches, and
writes the definitions itself, because a pipeline that stops for a question at
every stage is not a pipeline. `approved_by` still starts empty and the report
still separates form from approval, so the record never claims an agreement
that has not happened; it simply does not wait for one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contract import Contract, load as load_contract
from .research import (DEFAULT_MODEL, Evidence, ResearchError, _client, ask,
                       load_all, look, record)
from .subjects import check as check_subjects, leaf_paths
from .subjects import approval_digest
from .lifecycle import (canonical_digest, read_direction_impact,
                        write_direction_impact)
from .generation_harness import (
    MAX_GENERATION_ATTEMPTS,
    attempt_record,
    harness_contract,
    retry_prompt,
    text_sha256,
)
from .execution_mode import load_execution_mode

STAGE_ROLE = "premise"
STAGE_FALLBACK = "01-premise"

PROPOSE_RULES = """You are defining one subject for a short vertical film.

Return a single JSON object and nothing else. You decide which fields the
subject needs; there is no schema to fill in. Rules:

- Every leaf must hold a real value. No nulls, no empty strings, no placeholders.
- Numbers are numbers, not strings. Units go in the field name, as in
  power_ps or length_mm or zero_to_100_kmh_s.
- Any figure you state must sit inside the ranges the evidence reports, or you
  must not state it. Stay inside what was found.
- If you declare a derived value such as power to weight, it must agree with the
  numbers it is derived from.
- Group related fields into nested objects.
- If the element can be operated, contacted or moved on screen, give its visible
  moving, fixed and contact parts stable `part_id` values. Add `affordances` that
  state the compatible target class, canonical contact/approach, intended force
  result and forbidden results. A tool describes a target class; it must not
  name or own another exact film element.
- A professional tool affordance must be dimensionally usable, not merely
  recognizable. Give the working contact part a numeric `capacity_contract`
  (for example jaw opening in mm) and stable action-plane/axis part ids. A
  compatible target definition must give the numeric extent that the tool acts
  on (for example outside diameter in mm) and its axis part id. Preserve enough
  clearance for the tool to seat visibly; do not choose dimensions just because
  they make the target look substantial on screen.
- If the element is a setting with an on-screen work point, give that point an
  `interaction_site_id`, target class and separate moving/fixed part ids. For a
  mechanical work point, also define its operated extent, axis and clearance in
  the same numeric unit used by the compatible tool class.
- Do not include a provenance block, a subject_id or an evidence list. Those are
  added around what you return.
- Add `_decisions`, keyed by important dotted field path. Each value has `class`
  (`user_mandated`, `evidence_supported`, `creative_choice`, `inferred`, or
  `unresolved`), `evidence_ids` containing only directly relevant evidence, and
  a short `basis`. Exact fictional numbers must be `creative_choice`; do not
  disguise them as external facts.
- Write field names in English. Write descriptive prose values in Korean.

Other elements of the same film may be shown to you. Read them and let them
inform your choices. Then leave them out.

- Describe only your own element. A character definition holds a face, a body,
  clothes and what the person carries. It does not hold the car, the location,
  the weather, or how those look next to each other.
- Do not create fields that reference another element, such as one naming how a
  garment sits against a particular vehicle's paint. That reasoning belongs in
  the decision, not in the record.
- Where another element genuinely changed a choice, put one line in a top-level
  key named `_considered`, a list of short strings. It is lifted out of the body
  and filed with the provenance, so the reason survives without becoming part of
  what the thing is.

The elements meet later, when a shot is composed from several of them at once.
Deciding here what they look like together forecloses that.
"""


def stage_name(contract: Contract | None = None, attempt: Path | None = None) -> str:
    """The stage this module writes into, named by the contract when there is one."""
    if contract is None and attempt is not None:
        try:
            contract = load_contract(attempt)
        except Exception:  # noqa: BLE001 - 계약이 아직 없을 때도 경로는 필요하다
            contract = None
    return contract.stage_for(STAGE_ROLE, STAGE_FALLBACK) if contract else STAGE_FALLBACK


def stage_output(attempt: Path, contract: Contract | None = None) -> Path:
    return attempt / stage_name(contract, attempt) / "output"


def subjects_dir(attempt: Path, contract: Contract) -> Path:
    where = contract.get("subjects", {}).get(
        "directory", f"{stage_name(contract)}/output/subjects")
    return attempt / where


# ------------------------------------------------------------------ direction


def write_direction(attempt: Path, text: str, given_by: str, add: bool = False) -> Path:
    """The one line the run started from, kept verbatim.

    Everything after this is derived, and a derivation whose starting point is
    only in someone's memory cannot be argued with later.

    Direction arrives late as often as not. Someone says what the film is, the
    stage runs, and only when there is something to look at does anyone think to
    say what actually happens in it. `add` files those as supplements with their
    own timestamps rather than editing the original line, so a later reader can
    see which parts of the work predate which instruction.
    """
    target = stage_output(attempt) / "direction.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    if add and target.exists():
        record = json.loads(target.read_text(encoding="utf-8"))
        record.setdefault("supplements", []).append(
            {"direction": text, "given_by": given_by, "received_at": now,
             "note": "처음 지시 이후에 온 보충이다. 이 시각 이전에 만들어진 것은 이것을 모른다"})
    else:
        record = {
            "direction": text,
            "given_by": given_by,
            "received_at": now,
            "supplements": [],
            "note": "사람이 준 지시사항 원문이다. 이 아래 모든 것은 여기서 파생됐다",
        }
    target.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    if add:
        try:
            write_direction_impact(attempt, load_contract(attempt), record)
        except Exception:
            # A direction may legitimately arrive before its contract. The report
            # command will create the impact record once the contract exists.
            pass
    return target


def full_direction(attempt: Path) -> str:
    """The original line plus everything added since, in the order it arrived."""
    record = read_direction(attempt) or {}
    parts = [record.get("direction", "")]
    parts += [s["direction"] for s in record.get("supplements", [])]
    return "\n".join(p for p in parts if p)


def read_direction(attempt: Path) -> dict | None:
    path = stage_output(attempt) / "direction.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


# ------------------------------------------------------------------- questions

PLANNER_RULES = """
지시사항과 정의할 요소 목록을 받는다. 무엇을 조사해야 할지 정하라.

조사의 목적은 하나다. **지어낸 것이 실제와 어긋나지 않게 하는 것.**

**질문은 최대 {max_questions} 개, 그중 사진 질문은 최대 {max_image_questions} 개다.**
상한을 넘기지 마라. 넘치면 덜 중요한 것을 버려라.

이 상한이 있는 이유는 조사가 목적이 아니기 때문이다. Stage 1 runtime 계약은
{runtime_contract} 이다. 화면에 보이지 않을 것은 묻지 마라. 배관공이 밸브를
어떤 순서로 잠그는지는 그 절차가 화면에 나올 때만 물을 값어치가 있다.

무엇을 묻나. 요소마다 하나씩, 화면에 실제로 보일 것을 묻는다.

- 그것이 어떻게 생겼는가. 형태, 비례, 재질, 색, 크기.
- 그 일을 하는 사람이 실제로 무엇을 걸치고 무엇을 드는가.
- 화면에서 전문 도구를 실제로 사용한다면 생김새만 조사하지 마라. 올바른 대상,
  접촉 위치, 접근 방향, 움직이는 부품, 힘을 받을 때 고정되는 반작용 부품과 정상
  결과를 함께 조사하라. 도구의 실제 작업 용량 범위, 대상의 작업부 외경·두께,
  도구 작용면과 대상 축이 이루어야 하는 각도도 같은 단위의 수치로 확인하라.
  어느 하나라도 근거가 없으면 `unresolved`로 남길 질문을 우선한다.

두 번째를 빠뜨리면 그럴듯하지만 아무도 그렇게 안 하는 물건이 나온다. 자동차
유튜브 진행자에게 방송용 핸드헬드 마이크를 쥐여주는 식이다. 실제로는 옷에 다는
핀마이크를 쓴다.

지어낸 세계라도 참고할 실물이 있다. 공중 마을이면 실제 고가 구조물과 수상가옥의
동선을 본다. 다만 그것도 화면에 나올 만큼만 본다.

각 질문마다 **글로 답할 것인지 사진으로 답할 것인지** 정하라.

- `text`: 수치, 범위, 규정, 절차, 용어처럼 문장으로 답이 되는 것.
- `image`: 생김새, 배치, 착용 방식, 장비가 몸이나 공간에 실제로 어떻게 놓이는지.
  말로 옮기면 그럴듯하지만 틀리기 쉬운 것은 전부 여기다.

의심스러우면 `image` 로 보내라. 사진 한 장이 문단 하나보다 자주 정확하다.
방송용 핸드헬드 마이크를 쥔 유튜버가 나온 것은 그 질문을 글로만 물었기 때문이다.

`text` 질문은 출처를 요구하는 문장으로 끝내라.
`image` 질문은 무엇이 찍힌 사진을 원하는지 명시하라.

JSON 객체 하나만 반환하라. 형식은 이렇다.
{{"questions": [{{"ask": "...", "mode": "text", "why": "무엇을 확인하려는가"}}]}}
"""


def plan_questions(attempt: Path, contract: Contract, model: str = DEFAULT_MODEL) -> list[dict]:
    """What to look up, decided from the direction rather than by hand.

    The first run of this stage had its three questions typed in by a person.
    They covered what the car is, what a trackday lets you wear, and how twilight
    behaves, and they missed how anyone actually records audio on a shoot like
    this. The definition that came out gave a YouTube presenter a broadcast
    handheld microphone, which is plausible-looking and not what anyone does.

    Nobody had asked, because asking was not part of the pipeline.
    """
    direction = read_direction(attempt) or {}
    elements = {name: rules for name, rules in contract.elements().items()}
    plan = contract.get("research") or {}
    question = "\n\n".join([
        PLANNER_RULES.format(
            max_questions=plan.get("max_questions", 6),
            max_image_questions=plan.get("max_image_questions", 3),
            runtime_contract=json.dumps(contract.runtime_contract, ensure_ascii=False)),
        f"지시사항: {full_direction(attempt)}",
        "정의할 요소:\n" + json.dumps(elements, ensure_ascii=False, indent=2),
    ])
    client = _client()
    response = client.responses.create(
        model=model, input=question, text={"format": {"type": "json_object"}})
    raw = json.loads(response.output_text).get("questions", [])

    planned = []
    for item in raw:
        if isinstance(item, str):
            planned.append({"ask": item, "mode": "text", "why": ""})
        elif item.get("ask"):
            mode = item.get("mode", "text")
            planned.append({"ask": item["ask"],
                            "mode": mode if mode in {"text", "image"} else "text",
                            "why": item.get("why", "")})

    # 지시로 준 상한을 모델이 넘기면 여기서 자른다. 열여섯 개를 내놓고 백 번
    # 검색해서 십 분을 쓴 적이 있다. 사진 질문이 특히 비싸므로 따로 센다.
    limit = plan.get("max_questions", 6)
    image_limit = plan.get("max_image_questions", 3)
    kept, images = [], 0
    for item in planned:
        if len(kept) >= limit:
            break
        if item["mode"] == "image":
            if images >= image_limit:
                item = {**item, "mode": "text", "why": item["why"] + " (사진 상한 초과로 글 조사)"}
            else:
                images += 1
        kept.append(item)
    created = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    for index, item in enumerate(kept, 1):
        item["question_id"] = f"RQ{index:02d}"
    plan_doc = {
        "schema_version": "research-plan.v1",
        "plan_id": f"{contract.data['contract_id']}-RESEARCH-{canonical_digest(kept)}",
        "created_at": created,
        "direction_sha256": canonical_digest(read_direction(attempt) or {}),
        "limits": {"max_questions": limit, "max_image_questions": image_limit},
        "planned_question_count": len(kept),
        "questions": kept,
        "note": "question count is measured here; searches/results are separate counts",
    }
    path = stage_output(attempt, contract) / "research-plan.json"
    path.write_text(json.dumps(plan_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return kept


# ------------------------------------------------------------------- research


def investigate(attempt: Path, questions: list, model: str | None = None,
                images: int = 4, workers: int = 4) -> list[Evidence]:
    """Ask each question the way it asked to be asked, and file every answer.

    A planned question carries the mode the planner chose. Routing on it is the
    whole point: the run that put a broadcast handheld microphone on a YouTube
    presenter asked that question in words, and words were never going to settle
    it.
    """
    out = stage_output(attempt)

    def one(item):
        if isinstance(item, str):
            item = {"ask": item, "mode": "text"}
        try:
            if item.get("mode") == "image":
                return item, look(item["ask"], out, images, model or DEFAULT_MODEL)
            return item, (ask(item["ask"], model) if model else ask(item["ask"]))
        except ResearchError as error:
            print(f"조사 실패 [{item.get('mode', 'text')}]: {error}", flush=True)
            return None

    # 질문끼리는 서로를 안 본다. 순차로 돌 이유가 없다.
    gathered = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for result in pool.map(one, questions):
            if result is None:
                continue
            item, evidence = result
            path = record(evidence, out)
            stored = json.loads(path.read_text(encoding="utf-8"))
            stored["research_question_id"] = item.get("question_id")
            stored["query"] = {"mode": item.get("mode", "text"),
                               "text": item.get("ask", "")}
            stored["result_unit"] = "one synthesized evidence record"
            path.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")
            gathered.append(evidence)
    return gathered


# ------------------------------------------------------------------- subjects


def put_subject(attempt: Path, contract: Contract, subject_id: str, spec: dict,
                decided_by: str, basis: str, evidence_ids: list[str] | None = None,
                approved_by: str = "", considered: list | None = None,
                decisions: dict | None = None) -> Path:
    """Write a definition with its origin attached, never without.

    `approved_by` defaults to empty on purpose. A proposal that arrives already
    approved by whoever wrote it is the failure this whole stage exists to stop.
    """
    target = subjects_dir(attempt, contract) / f"{subject_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)

    # 계약이 정한 것은 본문이 덮을 수 없다. 앞에 두면 뒤에 오는 본문이 이긴다.
    # 모델이 kind 를 되받아 적는 바람에 character 로 선언된 요소가 파일에서
    # subject 가 됐고, 시트 도구가 다른 명세를 찾다가 멈췄다.
    reserved = {"provenance", "subject_id", "evidence", "kind", "decisions"}
    body = {k: v for k, v in spec.items() if k not in reserved}
    payload = {
        "subject_id": subject_id,
        "kind": contract.elements().get(subject_id, {}).get("kind", "subject"),
        **body,
        "evidence": list(evidence_ids or []),
        "decisions": dict(decisions or {}),
        "provenance": {
            "decided_by": decided_by,
            "decided_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "basis": basis,
            # 다른 요소가 이 결정을 바꿨다면 그 이유는 여기 남는다. 본문에는 안 남는다.
            "considered": list(considered or []),
            "approved_by": approved_by,
        },
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


# -------------------------------------------------------------------- propose


def _evidence_digest(evidence: dict[str, dict], limit: int = 4000) -> str:
    """The answers, trimmed, so a proposal can be held to what was actually found."""
    parts = []
    for eid, item in evidence.items():
        sources = ", ".join(c["url"] for c in item.get("citations", [])[:4]) or "출처 없음"
        parts.append(f"[{eid}]\n질문: {item['question']}\n"
                     f"답변: {item['answer'][:limit]}\n근거: {sources}")
    return "\n\n".join(parts)


def _context(attempt: Path, contract: Contract, exclude: str) -> str:
    """The elements already decided, so a choice can be made in view of them.

    Reading them and describing them are different acts. A presenter's jacket
    may be chosen dark because the car is gloss red, and that is good reasoning;
    a field on the presenter called `car_paint_compatibility` is that reasoning
    left lying in the wrong file. It travels with every later stage that loads
    the character, and it fights the shot when the shot wants a different car.
    """
    where = contract.get("subjects", {}).get(
        "directory", f"{stage_name(contract)}/output/subjects")
    parts = []
    for name in sorted(contract.elements()):
        if name == exclude:
            continue
        path = attempt / where / f"{name}.json"
        if not path.exists():
            continue
        spec = json.loads(path.read_text(encoding="utf-8"))
        body = {k: v for k, v in spec.items()
                if k not in {"provenance", "evidence", "subject_id", "decisions",
                             "evidence_context_legacy"}}
        parts.append(f"[{name}]\n" + json.dumps(body, ensure_ascii=False)[:2500])
    return "\n\n".join(parts)


def _proposal_problems(value: Any, path: str = "subject") -> list[str]:
    problems = []
    if value is None or value == "":
        return [f"{path}: empty value"]
    if isinstance(value, dict):
        if not value:
            return [f"{path}: empty object"]
        for key, item in value.items():
            problems.extend(_proposal_problems(item, f"{path}.{key}"))
    elif isinstance(value, list):
        if not value:
            return [f"{path}: empty list"]
        for index, item in enumerate(value):
            problems.extend(_proposal_problems(item, f"{path}[{index}]"))
    return problems


def propose(attempt: Path, contract: Contract, subject_id: str, rules: dict,
            model: str = DEFAULT_MODEL) -> dict:
    """Write one subject definition from the direction and what the search found.

    The model chooses the fields. That is the point of merging the brief and the
    research stage: deciding a vehicle has a redline is part of deciding what
    the vehicle is, and it cannot be settled by anyone who has not looked yet.

    Every evidence id goes into the record whether or not the text leaned on it,
    because which answers were in front of the model when it decided is part of
    how it decided.
    """
    direction = read_direction(attempt) or {}
    evidence = load_all(stage_output(attempt))

    question = "\n\n".join([
        PROPOSE_RULES,
        f"지시사항: {full_direction(attempt)}",
        f"정의할 대상: {subject_id}  종류: {rules.get('kind', 'subject')}",
        f"이 대상이 필요한 이유: {rules.get('why', '')}",
        "조사에서 나온 것:\n" + (_evidence_digest(evidence) or "조사 결과 없음"),
        "이미 정해진 다른 요소. 참고만 하고 기술하지 마라:\n"
        + (_context(attempt, contract, subject_id) or "아직 없음"),
    ])

    client = _client()
    correction = ""
    harness_attempts = []
    body = None
    for number in range(1, MAX_GENERATION_ATTEMPTS + 1):
        effective = retry_prompt(
            question, number, correction,
            failed_criteria=[line for line in correction.splitlines() if line.strip()])
        try:
            response = client.responses.create(
                model=model, input=effective, text={"format": {"type": "json_object"}})
            candidate = json.loads(response.output_text)
            problems = _proposal_problems(candidate)
        except Exception as error:  # malformed/transient model output is recoverable
            candidate = None
            problems = [f"generation error: {type(error).__name__}: {error}"]
        decision = "pass" if not problems else "fail"
        feedback = "\n".join(problems)
        harness_attempts.append(attempt_record(
            number, effective, decision, feedback, problems))
        if decision == "pass":
            body = candidate
            break
        correction = (
            "Repair these definition-validator findings without changing direction or evidence facts:\n" +
            "\n".join(f"- {item}" for item in problems))
    if body is None:
        raise ResearchError(
            f"{subject_id}: 정의가 {MAX_GENERATION_ATTEMPTS}회 변주·검증 뒤에도 통과하지 못했다")
    considered = body.pop("_considered", None)
    decisions = body.pop("_decisions", {})
    cited = sorted({eid for decision in decisions.values()
                    if isinstance(decision, dict)
                    for eid in decision.get("evidence_ids", []) if eid in evidence})

    basis = (f"{len(evidence)}건의 웹 조사 결과 범위 안에서 정함"
             if evidence else "조사 결과 없이 지시사항만으로 정함")
    path = put_subject(attempt, contract, subject_id, body,
                       decided_by=model, basis=basis,
                       evidence_ids=cited, considered=considered, decisions=decisions)
    written = json.loads(path.read_text(encoding="utf-8"))
    definition_field_count = len(leaf_paths(written))
    written.setdefault("provenance", {})["generation_harness"] = {
        **harness_contract(
            "stage01_subject_definition", text_sha256(question),
            ("valid JSON object", "no empty or placeholder leaves", "facts remain within evidence"),
            exhaustion_policy="report_attempt_10_with_unresolved_findings",
            execution_mode=load_execution_mode(attempt)["mode"]),
        "attempts": harness_attempts,
    }
    path.write_text(json.dumps(written, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"subject": subject_id, "path": str(path),
            "fields": definition_field_count, "evidence": len(evidence)}


def propose_all(attempt: Path, contract: Contract | None = None,
                model: str = DEFAULT_MODEL, force: bool = False) -> list[dict]:
    contract = contract or load_contract(attempt)
    out = []
    for subject_id, rules in contract.get("subjects", {}).get("declared", {}).items():
        target = subjects_dir(attempt, contract) / f"{subject_id}.json"
        if target.exists() and not force:
            out.append({"subject": subject_id, "status": "existing"})
            continue
        out.append(propose(attempt, contract, subject_id, rules, model))
    return out


# --------------------------------------------------------------------- report


def report(attempt: Path, contract: Contract | None = None) -> dict:
    contract = contract or load_contract(attempt)
    out = stage_output(attempt)
    direction = read_direction(attempt)
    evidence = load_all(out)
    subjects = check_subjects(attempt, contract)
    impact_path = write_direction_impact(attempt, contract, direction or {})
    impact = json.loads(impact_path.read_text(encoding="utf-8"))
    plan_path = out / "research-plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8")) if plan_path.exists() else None

    # 근거를 인용해놓고 그 근거가 없으면 확인한 척이 된다
    dangling: list[dict] = []
    for entry in subjects["subjects"]:
        path = attempt / entry["path"]
        if not path.exists():
            continue
        spec = json.loads(path.read_text(encoding="utf-8"))
        for eid in spec.get("evidence", []) or []:
            if eid not in evidence:
                dangling.append({"subject": entry["subject"], "evidence_id": eid})

    sourceless = [eid for eid, ev in evidence.items() if not ev.get("citations")]

    form_ok = bool(direction) and subjects["ok"] and not dangling and not sourceless
    human_approved = subjects["all_approved"]
    release_eligible = form_ok and human_approved and impact.get("unresolved_count", 0) == 0
    return {
        "stage": stage_name(contract),
        "attempt": attempt.name,
        "direction_recorded": bool(direction),
        "direction": (direction or {}).get("direction"),
        "contract": {"id": contract.data["contract_id"], "sha256": contract.digest,
                     "frame": contract.frame.as_dict(),
                     "delivery_frame": contract.delivery_frame.as_dict()},
        "evidence_count": len(evidence),
        "research_plan": {
            "status": "recorded" if plan else "historical_unrecorded",
            "planned_question_count": (plan or {}).get("planned_question_count"),
            "evidence_result_count": len(evidence),
            "searches_run": sum(int(e.get("searches_run", 0)) for e in evidence.values()),
        },
        "evidence_without_source": sourceless,
        "evidence_cited_but_missing": dangling,
        "subjects": subjects["subjects"],
        "direction_impact": {"path": str(impact_path.relative_to(attempt)),
                             "unresolved_count": impact.get("unresolved_count", 0)},
        "form_ok": form_ok,
        "human_approved": human_approved,
        "release_eligible": release_eligible,
        "production_state": "release_eligible" if release_eligible else "draft_unapproved",
        "all_approved": human_approved,
        "note": "form, human approval, and release eligibility are independent gates",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="지시사항을 받아 조사하고 정의를 세운다")
    sub = parser.add_subparsers(dest="command", required=True)

    direction = sub.add_parser("direction", help="지시사항 원문을 남긴다")
    direction.add_argument("attempt", type=Path)
    direction.add_argument("text")
    direction.add_argument("--by", default="user")
    direction.add_argument("--add", action="store_true",
                           help="원문을 고치지 않고 보충으로 덧붙인다")

    research = sub.add_parser("research", help="개연성 조사를 하고 근거로 남긴다")
    research.add_argument("attempt", type=Path)
    research.add_argument("questions", nargs="*", help="비우면 질문도 자동으로 세운다")
    research.add_argument("--model")
    research.add_argument("--images", type=int, default=3,
                          help="사진 질문 하나에 받아올 장수")
    research.add_argument("--workers", type=int, default=4, help="동시 실행 수")

    define = sub.add_parser("define", help="정의를 JSON 으로 받아 출처와 함께 쓴다")
    define.add_argument("attempt", type=Path)
    define.add_argument("subject_id")
    define.add_argument("spec", type=Path, help="본문 JSON 파일")
    define.add_argument("--by", required=True)
    define.add_argument("--basis", required=True)
    define.add_argument("--evidence", nargs="*", default=[])

    auto = sub.add_parser("propose", help="지시사항과 조사 결과로 정의를 짓는다")
    auto.add_argument("attempt", type=Path)
    auto.add_argument("--only", nargs="*")
    auto.add_argument("--model", default=DEFAULT_MODEL)
    auto.add_argument("--force", action="store_true")

    approve = sub.add_parser("approve", help="사람이 읽고 승인한다")
    approve.add_argument("attempt", type=Path)
    approve.add_argument("subject_id")
    approve.add_argument("--by", required=True)

    show = sub.add_parser("report")
    show.add_argument("attempt", type=Path)
    show.add_argument("--out", type=Path)

    args = parser.parse_args()
    attempt = args.attempt

    if args.command == "direction":
        print(f"작성: {write_direction(attempt, args.text, args.by, args.add)}")
        return 0

    if args.command == "research":
        questions = args.questions
        if not questions:
            questions = plan_questions(attempt, load_contract(attempt),
                                       args.model or DEFAULT_MODEL)
            modes = {}
            for q in questions:
                modes[q["mode"]] = modes.get(q["mode"], 0) + 1
            print(f"질문 {len(questions)}개를 세웠다. {modes}", flush=True)
            for q in questions:
                print(f"  [{q['mode']:5}] {q['ask'][:88]}", flush=True)
        for evidence in investigate(attempt, questions, args.model, args.images, args.workers):
            print(f"{evidence.evidence_id}: 검색 {evidence.searches}회 "
                  f"인용 {len(evidence.citations)}건", flush=True)
        return 0

    contract = load_contract(attempt)

    if args.command == "define":
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
        path = put_subject(attempt, contract, args.subject_id, spec,
                           args.by, args.basis, args.evidence)
        written = json.loads(path.read_text(encoding="utf-8"))
        print(json.dumps({"path": str(path), "declared_fields": len(leaf_paths(written)),
                          "evidence": written["evidence"],
                          "approved_by": ""}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "propose":
        declared = contract.get("subjects", {}).get("declared", {})
        if args.only:
            declared = {k: v for k, v in declared.items() if k in set(args.only)}
        results = []
        for subject_id, rules in declared.items():
            target = subjects_dir(attempt, contract) / f"{subject_id}.json"
            if target.exists() and not args.force:
                results.append({"subject": subject_id, "status": "existing"})
            else:
                results.append(propose(attempt, contract, subject_id, rules, args.model))
            print(json.dumps(results[-1], ensure_ascii=False), flush=True)
        return 0

    if args.command == "approve":
        path = subjects_dir(attempt, contract) / f"{args.subject_id}.json"
        spec = json.loads(path.read_text(encoding="utf-8"))
        spec["provenance"]["approved_by"] = args.by
        spec["provenance"]["approved_at"] = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        spec["provenance"]["approved_subject_sha256"] = approval_digest(spec)
        path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{args.subject_id}: {args.by} 승인")
        return 0

    result = report(attempt, contract)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    qa_report = attempt / stage_name(contract) / "qa" / "report.json"
    qa_report.parent.mkdir(parents=True, exist_ok=True)
    qa_report.write_text(text, encoding="utf-8")
    receipt = attempt / stage_name(contract) / "receipt.json"
    if receipt.exists():
        try:
            old_digest = (json.loads(receipt.read_text(encoding="utf-8"))
                          .get("contract", {}).get("sha256"))
        except (OSError, json.JSONDecodeError):
            old_digest = None
        if old_digest and old_digest != contract.digest:
            receipt = attempt / stage_name(contract) / "qa" / \
                f"premise-revalidation-receipt-{contract.digest}.json"
    receipt.write_text(json.dumps({
        "schema_version": "premise-receipt.v1",
        "receipt_id": f"{contract.data['contract_id']}-PREMISE",
        "contract": contract.receipt_block(stage_name(contract)),
        "direction_sha256": canonical_digest(read_direction(attempt) or {}),
        "subject_sha256": {p.stem: hashlib.sha256(p.read_bytes()).hexdigest()[:16]
                           for p in sorted(subjects_dir(attempt, contract).glob("*.json"))},
        "state": {k: result[k] for k in
                  ("form_ok", "human_approved", "release_eligible", "production_state")},
        "qa_report": str(qa_report.relative_to(attempt)),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0 if result["form_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
