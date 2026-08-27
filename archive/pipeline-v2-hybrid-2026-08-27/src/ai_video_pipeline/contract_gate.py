"""Check that what was generated was generated under the contract.

Three ways a contract quietly stops binding, all of them seen in v3.

A clause is dropped. The tool grew a `people_clause` after the prompt pack was
already written, so the pack on disk said nothing about people and the tool
said plenty. Whichever one you read, you learn something untrue about the other.

The contract moves after the fact. Receipts carry the digest of the contract
they were built under. A mismatch is a failure unless a narrow, human-approved
compatibility record binds the old receipt and current contract without
rewriting either one.

The frame is not the frame. The brief said 1080x1920, the runner said 576x1024,
the compositor said 1080x1920 again, and the receipts recorded no resolution at
all, so a 1.875x upscale sat in the middle of the pipeline unrecorded and
undiscussed.

Everything here compares files that already exist. Nothing is regenerated and
nothing is fixed. A failure means the record and the artefact disagree, and
which of the two is wrong is not something a checker can decide.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from .contract import Contract, ContractError, load

# 프롬프트 팩 안에서 프롬프트 문자열을 담고 있는 키
PROMPT_KEYS = ("prompt", "repair_prompt", "end_frame_prompt", "text")
# 팩 파일이 어느 단계에 속하는지는 그 팩이 놓인 폴더가 정한다
PACK_GLOB = "*/prompts/*.json"


def _iter_prompts(node, path=""):
    """Yield (label, prompt_text, entry) for every prompt-ish object in a pack."""
    if isinstance(node, dict):
        for key in PROMPT_KEYS:
            value = node.get(key)
            if isinstance(value, str) and value.strip():
                label = next((str(node[k]) for k in ("shot", "id", "name", "element")
                              if node.get(k)), path)
                yield label, value, node
                break
        for key, value in node.items():
            yield from _iter_prompts(value, f"{path}.{key}" if path else key)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            yield from _iter_prompts(item, f"{path}[{index}]")


def _conditions(contract: Contract, entry: dict) -> dict:
    """Read the contract's own condition flags off the pack entry.

    A conditional clause names the flag it turns on. The pack records that flag
    per entry, so the gate can resolve the same branch the tool resolved and
    compare like with like. When an entry does not carry the flag the clause is
    skipped rather than guessed at, because a wrong guess reports a violation
    that is not there.
    """
    return {flag: bool(entry[flag]) for flag in contract.condition_flags if flag in entry}


def check_prompt_packs(attempt: Path, contract: Contract) -> dict:
    """Every prompt must carry every clause its stage binds it to."""
    findings = []
    checked = 0
    for pack_path in sorted(attempt.glob(PACK_GLOB)):
        stage = pack_path.relative_to(attempt).parts[0]
        if not any(stage in c["applies_to"] for c in contract.data["clauses"]):
            continue
        try:
            data = json.loads(pack_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            findings.append({"pack": pack_path.name, "problem": f"JSON 아님: {error}"})
            continue

        for label, prompt, entry in _iter_prompts(data):
            checked += 1
            kind = entry.get("kind")
            element = entry.get("element")
            missing = [c["id"] for c in contract.clauses_for(
                stage, _conditions(contract, entry), kind, element)
                       if c["text"] not in prompt]
            if missing:
                findings.append({
                    "pack": f"{stage}/prompts/{pack_path.name}",
                    "entry": label, "missing_clauses": missing,
                })
            leaked = [clause["id"]
                      for clause in contract.excluded_clauses_for(
                          stage, subject_kind=kind, element=element)
                      if any(text in prompt
                             for text in contract.clause_text_variants(clause))]
            if leaked:
                findings.append({
                    "pack": f"{stage}/prompts/{pack_path.name}",
                    "entry": label, "inapplicable_clauses": leaked,
                })
    return {"prompts_checked": checked, "findings": findings, "ok": not findings}


def check_receipts(attempt: Path, contract: Contract) -> dict:
    """Every stage receipt must name the contract or an accepted compatibility.

    Receipt integrity is independent of prompt clauses. A stage with no bound
    clause can still have been produced under an obsolete frame, subject list,
    scenario structure or stage mapping, so filtering receipts by
    `clauses.applies_to` hides real contract drift.
    """
    findings = []
    warnings = []
    seen = 0
    candidates = sorted(list(attempt.glob("*/receipt.json")) + list(attempt.glob("*/qa/*receipt*.json")))
    for path in candidates:
        seen += 1
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            findings.append({"receipt": path.name, "problem": f"JSON 아님: {error}"})
            continue
        block = data.get("contract") if isinstance(data, dict) else None
        if not block:
            findings.append({"receipt": str(path.relative_to(attempt)),
                             "problem": "contract 블록 없음. 어느 계약으로 만들었는지 기록이 없다"})
            continue
        if block.get("sha256") != contract.digest:
            relative = str(path.relative_to(attempt))
            stage = path.relative_to(attempt).parts[0]
            embedded = data.get("superseded_compatibility") or {}
            if (
                embedded.get("status") == "accepted"
                and embedded.get("recorded_contract_sha256") == block.get("sha256")
                and embedded.get("current_contract_sha256") == contract.digest
                and embedded.get("does_not_rewrite_original_receipt") is True
                and embedded.get("basis")
            ):
                warnings.append({"receipt": relative,
                                 "warning": "revalidation receipt의 후속 계약 호환 판정",
                                 "recorded": block.get("sha256"),
                                 "current": contract.digest,
                                 "basis": embedded.get("basis")})
                continue
            compatibility_path = attempt / stage / "qa" / "contract-compatibility.json"
            compatibility = None
            lifecycle_record = None
            if compatibility_path.exists():
                try:
                    candidate = json.loads(compatibility_path.read_text(encoding="utf-8"))
                    if (
                        candidate.get("scope") == stage
                        and candidate.get("receipt") == relative
                        and candidate.get("recorded_contract_sha256") == block.get("sha256")
                        and candidate.get("current_contract_sha256") == contract.digest
                        and candidate.get("does_not_rewrite_original_receipt") is True
                    ):
                        lifecycle_record = candidate
                    if (
                        candidate.get("status") == "accepted"
                        and candidate.get("scope") == stage
                        and candidate.get("receipt") == relative
                        and candidate.get("recorded_contract_sha256") == block.get("sha256")
                        and candidate.get("current_contract_sha256") == contract.digest
                        and str(candidate.get("accepted_by", "")).strip()
                        and bool(candidate.get("basis"))
                        and candidate.get("does_not_rewrite_original_receipt") is True
                    ):
                        compatibility = candidate
                except json.JSONDecodeError:
                    compatibility = None

            if compatibility:
                warnings.append({
                    "receipt": relative,
                    "warning": "전체 계약 digest 변경을 단계 범위 호환 판정으로 수용",
                    "recorded": block.get("sha256"),
                    "current": contract.digest,
                    "compatibility": str(compatibility_path.relative_to(attempt)),
                    "accepted_by": compatibility["accepted_by"],
                })
            else:
                finding = {"receipt": relative,
                           "problem": "계약 해시 불일치",
                           "recorded": block.get("sha256"), "current": contract.digest}
                if lifecycle_record:
                    finding["compatibility_status"] = lifecycle_record.get("status")
                    finding["compatibility"] = str(compatibility_path.relative_to(attempt))
                    finding["note"] = "차이는 기록됐지만 accepted가 아니므로 통과시키지 않는다"
                findings.append(finding)
    return {"receipts_checked": seen, "findings": findings,
            "warnings": warnings, "ok": not findings}


def _probe(path: Path) -> tuple[int, int] | None:
    try:
        raw = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v",
             "-show_entries", "stream=width,height", "-of", "json", str(path)],
            check=True, capture_output=True, text=True).stdout
        stream = json.loads(raw)["streams"][0]
        return int(stream["width"]), int(stream["height"])
    except Exception:
        return None


def check_frames(attempt: Path, contract: Contract, media_globs: list[str]) -> dict:
    """Pixels on disk must match that stage's production or delivery raster."""
    findings = []
    checked = 0
    skipped = []
    targets = {}
    for pattern in media_globs:
        for path in sorted(attempt.glob(pattern)):
            stage = path.relative_to(attempt).parts[0]
            stage_frame = contract.frame_for_stage(stage)
            if stage_frame is None:
                skipped.append(str(path.relative_to(attempt)))
                continue
            want = (stage_frame.width, stage_frame.height)
            targets[stage] = list(want)
            size = _probe(path)
            if size is None:
                continue
            checked += 1
            if size != want:
                findings.append({
                    "file": str(path.relative_to(attempt)),
                    "actual": list(size), "contract": list(want),
                    "scale": round((want[0] * want[1]) / (size[0] * size[1]), 3),
                })
    return {"media_checked": checked,
            "production_frame": [contract.frame.width, contract.frame.height],
            "delivery_frame": [contract.delivery_frame.width, contract.delivery_frame.height],
            "stage_targets": targets,
            "frame_binds": contract.data["frame"].get("applies_to"),
            "delivery_frame_binds": contract.data["delivery_frame"].get("applies_to"),
            "skipped_not_bound": len(skipped),
            "findings": findings,
            "ok": not findings}


def check_image_roles(attempt: Path, contract: Contract) -> dict:
    """Each image role delivers at the size its role asks for.

    A plate is a frame of the film, so it is measured against the frame. A
    sheet is conditioning input and is measured against the largest size the
    API offers. Both numbers come out of the contract, so moving the frame
    moves the plate without a tool being edited.
    """
    roles = (contract.image.get("roles") or {})
    where = contract.image.get("output_globs") or {}
    findings, checked = [], 0
    for role in roles:
        plan = contract.image_plan(role)
        want = tuple(plan.target)
        patterns = where.get(role) or []
        if not patterns:
            findings.append({"role": role,
                             "problem": "image.output_globs 에 이 역할의 산출물 위치가 없다. 검사할 수 없다"})
            continue
        for pattern in patterns:
            for path in sorted(attempt.glob(pattern)):
                size = _probe(path)
                if size is None:
                    continue
                checked += 1
                if size != want:
                    findings.append({"role": role, "file": str(path.relative_to(attempt)),
                                     "actual": list(size), "role_target": list(want),
                                     "api_size": plan.api_size, "fit": plan.fit})
    return {"images_checked": checked,
            "plans": {r: contract.image_plan(r).as_dict() for r in roles},
            "findings": findings, "ok": not findings}


DEFAULT_MEDIA = [
    "*/output/**/*.png",
    "*/output/**/*.mp4",
    "*/output/*.mp4",
]


def check(attempt: Path, media_globs: list[str] | None = None) -> dict:
    contract = load(attempt)
    packs = check_prompt_packs(attempt, contract)
    receipts = check_receipts(attempt, contract)
    frames = check_frames(attempt, contract, media_globs or DEFAULT_MEDIA)
    images = check_image_roles(attempt, contract) if contract.image.get("roles") else None
    return {
        "attempt": attempt.name,
        "contract_id": contract.data["contract_id"],
        "contract_sha256": contract.digest,
        "frame": contract.frame.as_dict(),
        "delivery_frame": contract.delivery_frame.as_dict(),
        "delivery_transform": contract.delivery_transform,
        "prompt_packs": packs,
        "receipts": receipts,
        "frames": frames,
        "image_roles": images,
        "ok": packs["ok"] and receipts["ok"] and frames["ok"]
              and (images is None or images["ok"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="계약이 실제로 지켜졌는지 검사한다")
    parser.add_argument("attempt", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--media", nargs="*", help="검사할 미디어 glob. 기본값은 output 아래 전부")
    args = parser.parse_args()

    try:
        report = check(args.attempt, args.media)
    except ContractError as error:
        print(json.dumps({"attempt": args.attempt.name, "ok": False,
                          "problem": str(error)}, ensure_ascii=False, indent=2))
        return 1

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
