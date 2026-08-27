"""The facts a film is about, established by an attempt and owned by it.

The supercar run kept its vehicle spec and its presenter description in a
topic-level folder shared by every attempt. Two things went wrong with that,
both of them structural rather than accidental.

Attempts stopped being independent. One file described the presenter, every
attempt pointed at it, and overwriting it for a later version silently changed
what the earlier ones claimed to have been built from. A version plan that says
each film is a different film cannot share the subject of the films.

And the facts had no origin. The spec announced itself as "fixed fact for this
project" while carrying no record of who fixed it, when, on what basis, or
whether anyone approved it. A consistency check inside the file compared two of
its own numbers and passed, which reads like verification and is not: it
catches a typo and can say nothing about whether the numbers were ever agreed.

So subjects are established in `01-premise`, one set per attempt, each carrying
its provenance. `approved_by` starts empty and stays empty until a person fills
it, the same way a human gate does.

`01-premise` owns the shape as well as the values. It decides that a vehicle
has a redline and what that redline is, because a stage that establishes what a
film is about cannot be handed a schema by someone who has not looked yet. An
earlier draft of this module took the required fields from the tools' AST, and
that put the first stage in the position of waiting for the eighth: the
compositor is written long afterwards, so nothing could be filled until
everything downstream existed.

The AST walk is still here and still worth having, pointed the other way. It
does not say what a subject needs. It catches the case where a tool reaches for
a field the premise never defined, which is a render that dies with a KeyError
and is much cheaper to find before a GPU is spent than after.

Nothing here knows what a vehicle is. It knows that facts need an origin, that
declared fields must be filled, that derived values must agree with their
inputs, and that nothing downstream may read a field nobody defined.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .contract import Contract, ContractError, load as load_contract

DEFAULT_SUBJECTS_DIR = "01-premise/output/subjects"   # 계약이 말이 없을 때만
DEFAULT_PROVENANCE = ["decided_by", "decided_at", "basis", "approved_by"]


class SubjectError(ValueError):
    """A subject is missing, malformed, or contradicts what the brief asked for."""


SKIP_KEYS = {"provenance", "subject_id", "kind", "note", "evidence", "decisions",
             "evidence_context_legacy"}
DECISION_CLASSES = {
    "user_mandated", "evidence_supported", "creative_choice", "inferred", "unresolved",
}


def approval_digest(spec: dict) -> str:
    """Digest the approved definition without letting approval fields hash themselves."""
    copy = json.loads(json.dumps(spec))
    provenance = copy.get("provenance") or {}
    for key in ("approved_by", "approved_at", "approved_subject_sha256"):
        provenance.pop(key, None)
    return hashlib.sha256(
        json.dumps(copy, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]


def decision_problems(spec: dict) -> list[dict]:
    """Validate field-level origin without pretending every field is researched fact."""
    out = []
    evidence = set(spec.get("evidence") or [])
    for dotted, decision in (spec.get("decisions") or {}).items():
        if dig(spec, dotted) is None:
            out.append({"id": "decision-field", "field": dotted,
                        "problem": "결정 기록이 없는 필드를 가리킨다"})
            continue
        klass = decision.get("class") if isinstance(decision, dict) else None
        if klass not in DECISION_CLASSES:
            out.append({"id": "decision-class", "field": dotted,
                        "problem": f"지원하지 않는 class {klass!r}"})
            continue
        cited = set(decision.get("evidence_ids") or [])
        if klass == "evidence_supported" and not cited:
            out.append({"id": "decision-evidence", "field": dotted,
                        "problem": "evidence_supported 결정에 evidence_ids가 없다"})
        if cited - evidence:
            out.append({"id": "decision-evidence", "field": dotted,
                        "problem": f"subject evidence에 없는 id {sorted(cited - evidence)}"})
    return out


def _empty(value: Any) -> bool:
    return value is None or (isinstance(value, (str, list, dict)) and len(value) == 0)


def leaf_paths(spec: dict, prefix: str = "") -> list[str]:
    """Every field this subject declares, as dotted paths.

    The schema is whatever `01-premise` wrote. Bookkeeping keys are skipped:
    provenance is about the fact rather than part of it, and counting it as a
    field would let a subject pass by describing only where it came from.
    """
    out: list[str] = []
    for key, value in spec.items():
        if not prefix and key in SKIP_KEYS:
            continue
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict) and value:
            out.extend(leaf_paths(value, path))
        else:
            out.append(path)
    return sorted(out)


def dig(data: Any, dotted: str) -> Any:
    """Fetch `a.b.c` out of nested dicts, or None if any hop is missing."""
    node = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


@dataclass(frozen=True)
class SubjectReport:
    subject_id: str
    path: str
    exists: bool
    missing_fields: list[str]
    failed_checks: list[dict]
    missing_provenance: list[str]
    approved: bool
    consumers: dict = field(default_factory=dict)
    declared: list = field(default_factory=list)
    read_but_undefined: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return (self.exists and not self.missing_fields and not self.failed_checks
                and not self.missing_provenance and not self.read_but_undefined)

    def as_dict(self) -> dict:
        return {
            "subject": self.subject_id, "path": self.path, "exists": self.exists,
            "missing_fields": self.missing_fields,
            "failed_checks": self.failed_checks,
            "missing_provenance": self.missing_provenance,
            "approved": self.approved,
            "declared_fields": self.declared,
            "read_but_undefined": self.read_but_undefined,
            "read_by": self.consumers,
            "ok": self.ok,
        }


def _run_check(spec: dict, check: dict) -> dict | None:
    """A declared derived value must agree with the numbers it is derived from.

    Only ratios, deliberately. A general expression language here would let the
    contract compute anything, and a check nobody can read is not a check. What
    this catches is the case where one number is edited and the value derived
    from it is not, so the screen would show two figures that contradict.
    """
    left = dig(spec, check["ratio"][0])
    right = dig(spec, check["ratio"][1])
    declared = dig(spec, check["equals"])
    if left is None or right is None or declared is None:
        return {"id": check.get("id", "?"), "problem": "검사에 쓸 값이 없다",
                "ratio": check["ratio"], "equals": check["equals"]}
    try:
        computed = (float(left) / float(right)) * float(check.get("scale", 1))
    except (TypeError, ValueError, ZeroDivisionError) as error:
        return {"id": check.get("id", "?"), "problem": f"계산 불가: {error}"}

    tolerance = float(check.get("tolerance", 0.5))
    if abs(computed - float(declared)) > tolerance:
        return {"id": check.get("id", "?"), "computed": round(computed, 4),
                "declared": declared, "tolerance": tolerance,
                "ratio": check["ratio"], "equals": check["equals"]}
    return None


def _taint(tree, subject_id: str) -> set[str]:
    """Names that ultimately hold the subject's data.

    The load is rarely one hop. A tool holds the path in one name and the
    parsed JSON in another:

        SNAPSHOT = RUN_DIR / "01-premise" / "output" / "subjects" / "vehicle.json"
        SPEC = json.loads(SNAPSHOT.read_text(encoding="utf-8"))

    Following only the first assignment finds a Path and no fields at all, which
    is what the first version of this did. So a name is tainted if its value
    mentions the subject file or mentions an already tainted name, and that runs
    to a fixed point.
    """
    import ast

    assigns = [n for n in ast.walk(tree) if isinstance(n, ast.Assign)]
    tainted: set[str] = set()
    for _ in range(6):
        grew = False
        for node in assigns:
            dumped = ast.dump(node.value)
            mentions_file = any(
                isinstance(c, ast.Constant) and isinstance(c.value, str)
                and subject_id in c.value and c.value.endswith(".json")
                for c in ast.walk(node.value))
            mentions_tainted = any(
                isinstance(c, ast.Name) and c.id in tainted for c in ast.walk(node.value))
            if not (mentions_file or mentions_tainted):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id not in tainted:
                    tainted.add(target.id)
                    grew = True
            del dumped
        if not grew:
            break
    return tainted


def consumed_paths(attempt: Path, subject_id: str) -> dict[str, list[str]]:
    """Which fields the tools actually read out of a subject file.

    A hand-written list of required fields is a wish, and it belongs to whoever
    typed it. What the film genuinely needs is what its tools reach for: a
    figure that reaches the screen is read by the compositor, and a field
    nothing reads is required by nothing.

    So the requirement is derived the way `pipeline_map` derives the graph, by
    walking the tools' AST. Every subscript chain on a name holding the subject
    is a field the run depends on. If one goes missing the render dies with a
    KeyError, and this reports it before a GPU is spent.
    """
    import ast

    def chain(node) -> tuple[str, ...] | None:
        """`SPEC["a"]["b"]` -> ('SPEC', 'a', 'b')"""
        if isinstance(node, ast.Name):
            return (node.id,)
        if (isinstance(node, ast.Subscript)
                and isinstance(node.slice, ast.Constant)
                and isinstance(node.slice.value, str)):
            head = chain(node.value)
            return head + (node.slice.value,) if head else None
        return None

    found: dict[str, list[str]] = {}
    tools = attempt / "tools"
    if not tools.exists():
        return found

    for path in sorted(tools.glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue

        roots = _taint(tree, subject_id)
        if not roots:
            continue

        # 별칭은 스코프 안에서만 유효하다. compose.py 는 spec_rows 안에서
        # c 를 chassis 별칭으로 쓰고 main 안에서 같은 c 를 카드 반복 변수로
        # 쓴다. 모듈 전체로 뭉뚱그리면 card["seconds"] 가 chassis.seconds 로
        # 잘못 읽힌다.
        scopes = [tree] + [n for n in ast.walk(tree)
                           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        hits: set[str] = set()
        for scope in scopes:
            body = list(ast.walk(scope))
            aliases: dict[str, tuple[str, ...]] = {}
            for node in body:
                if not isinstance(node, ast.Assign):
                    continue
                values = node.value.elts if isinstance(node.value, ast.Tuple) else [node.value]
                targets = (node.targets[0].elts if isinstance(node.targets[0], ast.Tuple)
                           else node.targets)
                for target, value in zip(targets, values):
                    parts = chain(value)
                    if (isinstance(target, ast.Name) and parts
                            and parts[0] in roots and len(parts) > 1):
                        aliases[target.id] = parts[1:]
            # 같은 스코프에서 다시 묶이는 이름은 더는 그 별칭이 아니다
            for node in body:
                if isinstance(node, ast.For) and isinstance(node.target, ast.Name):
                    aliases.pop(node.target.id, None)
                elif isinstance(node, ast.comprehension) and isinstance(node.target, ast.Name):
                    aliases.pop(node.target.id, None)

            for node in body:
                if not isinstance(node, ast.Subscript):
                    continue
                parts = chain(node)
                if not parts or len(parts) < 2:
                    continue
                if parts[0] in roots:
                    hits.add(".".join(parts[1:]))
                elif parts[0] in aliases:
                    hits.add(".".join(aliases[parts[0]] + parts[1:]))

        # 잎만 남긴다. chassis 는 chassis.rear_tyre 가 있으면 따로 셀 필요가 없다
        hits = {h for h in hits if not any(o != h and o.startswith(h + ".") for o in hits)}
        if hits:
            found[path.name] = sorted(hits)
    return found


def check_subject(attempt: Path, contract: Contract, subject_id: str, rules: dict) -> SubjectReport:
    where = contract.get("subjects", {}).get(
        "directory", f'{contract.stage_for("premise", "01-premise")}/output/subjects')
    path = attempt / where / f"{subject_id}.json"
    rel = str(Path(where) / f"{subject_id}.json")

    if not path.exists():
        consumers = consumed_paths(attempt, subject_id)
        read = sorted({f for fields in consumers.values() for f in fields})
        return SubjectReport(subject_id, rel, False, [], [],
                             list(contract.get("subjects", {}).get(
                                 "provenance_required", DEFAULT_PROVENANCE)), False,
                             consumers=consumers, read_but_undefined=read)

    spec = json.loads(path.read_text(encoding="utf-8"))

    # 이 단계가 스스로 정한 필드가 곧 이 피사체의 스키마다. 선언해놓고 비워두면 지적한다.
    declared = leaf_paths(spec)
    missing = [f for f in declared if _empty(dig(spec, f))]

    # 반대 방향 검사. 아무도 정의하지 않은 필드를 뒤의 도구가 읽으면 렌더가 죽는다.
    consumers = consumed_paths(attempt, subject_id)
    read = sorted({f for fields in consumers.values() for f in fields})
    undefined = [f for f in read if dig(spec, f) is None]
    failed = [f for f in (_run_check(spec, c) for c in rules.get("checks", [])) if f]
    failed.extend(decision_problems(spec))

    wanted = contract.get("subjects", {}).get("provenance_required", DEFAULT_PROVENANCE)
    provenance = spec.get("provenance") or {}
    absent = [key for key in wanted if key != "approved_by" and not provenance.get(key)]
    approved = bool(provenance.get("approved_by")) and (
        provenance.get("approved_subject_sha256") == approval_digest(spec))

    return SubjectReport(subject_id, rel, True, missing, failed, absent, approved,
                         consumers=consumers, declared=declared,
                         read_but_undefined=undefined)


def check(attempt: Path, contract: Contract | None = None) -> dict:
    contract = contract or load_contract(attempt)
    declared = contract.get("subjects", {}).get("declared", {})
    if not declared:
        return {"attempt": attempt.name, "declared": 0,
                "note": "계약이 피사체를 선언하지 않았다. 검사할 것이 없다",
                "subjects": [], "ok": True, "all_approved": True}

    reports = [check_subject(attempt, contract, sid, rules)
               for sid, rules in declared.items()]

    # 계약에서 요소를 빼도 파일은 남는다. 남은 파일은 아무도 안 읽는 채로
    # 다음 사람에게 여전히 사실처럼 보인다.
    where = contract.get("subjects", {}).get("directory", DEFAULT_SUBJECTS_DIR)
    folder = attempt / where
    on_disk = sorted(p.stem for p in folder.glob("*.json")) if folder.exists() else []
    undeclared = [name for name in on_disk if name not in declared]

    return {
        "undeclared_files": undeclared,
        "attempt": attempt.name,
        "directory": contract.get("subjects", {}).get("directory", DEFAULT_SUBJECTS_DIR),
        "declared": len(reports),
        "subjects": [r.as_dict() for r in reports],
        "ok": all(r.ok for r in reports) and not undeclared,
        "all_approved": all(r.approved for r in reports),
        "note": "ok 는 형식이 갖춰졌다는 뜻이다. all_approved 가 사람이 확인했다는 뜻이다",
    }


def template(subject_id: str, rules: dict) -> dict:
    """A skeleton with every required field present and empty, so nothing is silently absent."""
    out: dict[str, Any] = {
        "subject_id": subject_id,
        "kind": rules.get("kind", "subject"),
        "note": rules.get("why", ""),
        "provenance": {
            "decided_by": "",
            "decided_at": "",
            "basis": "",
            "approved_by": "",
            "how_to_fill": "decided_by 는 사람 이름이나 모델 이름. basis 는 무엇을 보고 정했는지. "
                           "approved_by 는 사람이 확인하기 전까지 비워 둔다",
        },
    }
    for dotted in rules.get("suggest_fields", []):
        node = out
        parts = dotted.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = None
    out["evidence"] = []
    return out


def scaffold(attempt: Path, contract: Contract | None = None, force: bool = False) -> list[Path]:
    contract = contract or load_contract(attempt)
    where = contract.get("subjects", {}).get("directory", DEFAULT_SUBJECTS_DIR)
    written = []
    for subject_id, rules in contract.get("subjects", {}).get("declared", {}).items():
        target = attempt / where / f"{subject_id}.json"
        if target.exists() and not force:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(template(subject_id, rules), ensure_ascii=False, indent=2),
                          encoding="utf-8")
        written.append(target)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="브리프가 선언한 피사체가 실제로 채워졌는지 검사한다")
    sub = parser.add_subparsers(dest="command", required=True)

    verify = sub.add_parser("check")
    verify.add_argument("attempt", type=Path)
    verify.add_argument("--out", type=Path)

    init = sub.add_parser("scaffold", help="선언된 피사체의 빈 뼈대를 쓴다")
    init.add_argument("attempt", type=Path)
    init.add_argument("--force", action="store_true")

    args = parser.parse_args()

    try:
        if args.command == "scaffold":
            written = scaffold(args.attempt, force=args.force)
            print(json.dumps({"written": [str(p) for p in written]}, ensure_ascii=False, indent=2))
            return 0
        report = check(args.attempt)
    except ContractError as error:
        print(json.dumps({"ok": False, "problem": str(error)}, ensure_ascii=False, indent=2))
        return 1

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
