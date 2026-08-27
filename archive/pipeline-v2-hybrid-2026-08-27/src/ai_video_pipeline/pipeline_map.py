"""Derive the pipeline graph from the code, not from what the docs claim.

Every attempt has its own tools directory and its own idea of what feeds what.
The prose in NOTES.md is written after the fact and has already been wrong: one
run declared a subject sheet in its shot card, generated the sheet, and then no
script ever opened the directory it was written to. Nothing caught that,
because nothing was reading the code.

So this reads the code. It walks each tool's AST, resolves `RUN_DIR / "06-look"
/ "output"` style path expressions to stage-relative strings, and decides read
or write from the call the path ends up in. What comes out is what the scripts
actually touch.

An artifact that is written and never read is reported as orphaned. That is the
shape of the failure above and it is worth seeing on a graph.
"""

from __future__ import annotations

import argparse
import ast
import html
import json
from pathlib import Path

READ_CALLS = {"read_text", "read_bytes", "open", "glob", "rglob", "iterdir", "load", "exists"}
WRITE_CALLS = {"write_text", "write_bytes", "save", "mkdir", "replace", "copy2", "move"}
STAGE_PREFIXES = tuple(f"{n:02d}-" for n in range(1, 13))


def _string_parts(node: ast.AST) -> list[str] | None:
    """Flatten `NAME / "a" / "b"` into ['NAME', 'a', 'b']."""
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left = _string_parts(node.left)
        right = _string_parts(node.right)
        if left is None or right is None:
            return None
        return left + right
    if isinstance(node, ast.Call):
        return None
    if isinstance(node, ast.Attribute):
        return None
    return None


class PathCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.aliases: dict[str, list[str]] = {}
        self.hits: list[tuple[str, str]] = []   # (path, verb)

    def visit_Assign(self, node: ast.Assign) -> None:
        parts = _string_parts(node.value)
        if parts:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.aliases[target.id] = parts
        self.generic_visit(node)

    def _resolve(self, parts: list[str]) -> list[str]:
        out: list[str] = []
        for part in parts:
            if part in self.aliases and self.aliases[part] != parts:
                out.extend(self._resolve(self.aliases[part]))
            else:
                out.append(part)
        return out

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute):
            verb = node.func.attr
            if verb in READ_CALLS or verb in WRITE_CALLS:
                parts = _string_parts(node.func.value)
                if parts:
                    resolved = self._resolve(parts)
                    stage = next((p for p in resolved if p.startswith(STAGE_PREFIXES)), None)
                    if stage:
                        tail = resolved[resolved.index(stage):]
                        self.hits.append(("/".join(tail), verb))
        self.generic_visit(node)


def analyse_tool(path: Path) -> dict:
    """Resolved read/write plus every stage constant the tool mentions at all.

    Resolving only module-level `A / "b"` chains misses a great deal: a path
    held in a loop variable, or built inside a helper, never resolves. That
    matters here, because the question being asked is whether a stage is wired
    in at all, and a tool that opens `SHEETS / name` in a loop is wired in.

    So constants that point at a stage are tracked by name, and any mention of
    one counts as the tool touching that stage.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    collector = PathCollector()
    collector.visit(tree)

    reads, writes = set(), set()
    for target, verb in collector.hits:
        (writes if verb in WRITE_CALLS else reads).add(target)

    stage_constants = {
        name: "/".join(collector._resolve(parts)[
            next((i for i, p in enumerate(collector._resolve(parts))
                  if p.startswith(STAGE_PREFIXES)), 0):])
        for name, parts in collector.aliases.items()
        if any(p.startswith(STAGE_PREFIXES) for p in collector._resolve(parts))
    }
    mentioned = {
        stage_constants[node.id]
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id in stage_constants
    }

    return {
        "tool": path.name,
        "reads": sorted(reads - writes),
        "writes": sorted(writes),
        "both": sorted(reads & writes),
        "mentions": sorted(mentioned - reads - writes),
    }


def analyse_attempt(attempt: Path) -> dict:
    tools_dir = attempt / "tools"
    tools = [analyse_tool(p) for p in sorted(tools_dir.glob("*.py"))] if tools_dir.exists() else []

    produced: dict[str, str] = {}
    consumed: dict[str, list[str]] = {}
    for tool in tools:
        for target in tool["writes"] + tool["both"]:
            produced.setdefault(target, tool["tool"])
        for target in tool["reads"] + tool["both"] + tool["mentions"]:
            consumed.setdefault(target, []).append(tool["tool"])

    def touched(prefix: str) -> bool:
        return any(t.startswith(prefix) for t in list(produced) + list(consumed))

    orphans = sorted(t for t in produced if t not in consumed and "output" in t)
    dangling = sorted(t for t in consumed if t not in produced)

    stages_on_disk = sorted(p.name for p in attempt.iterdir()
                            if p.is_dir() and p.name.startswith(STAGE_PREFIXES))
    return {
        "attempt": attempt.name,
        "tools": tools,
        "stages_on_disk": stages_on_disk,
        "stages_touched_by_code": sorted({t.split("/")[0] for t in list(produced) + list(consumed)}),
        "produced_by": produced,
        "orphan_outputs": orphans,
        "external_inputs": dangling,
    }


def render_html(topic: Path, reports: list[dict], out: Path) -> Path:
    body = [
        f"<title>{html.escape(topic.name)} 파이프라인 실제 구성</title>",
        "<style>",
        "body{background:#0f1012;color:#e9e5dd;font:14px/1.6 -apple-system,'Apple SD Gothic Neo',sans-serif;",
        "margin:0;padding:36px 24px;max-width:1180px;margin:0 auto}",
        "h1{font-size:24px;margin:0 0 4px}h2{font-size:16px;margin:32px 0 4px;color:#c3b79f}",
        "p.sub{color:#8d8579;margin:0 0 24px;font-size:13px}",
        ".attempt{border:1px solid #24262a;border-radius:8px;padding:16px 18px;margin:0 0 20px}",
        ".chain{display:flex;flex-wrap:wrap;align-items:stretch;gap:6px;margin:10px 0 4px}",
        ".stage{background:#17191d;border:1px solid #2b2e33;border-radius:6px;padding:8px 10px;min-width:112px}",
        ".stage .id{color:#d6b260;font-size:11px;letter-spacing:.05em}",
        ".stage .t{color:#c9c3b8;font-size:12px;display:block;margin-top:3px}",
        ".stage.cold{opacity:.32}",
        ".arrow{align-self:center;color:#4a4d53}",
        "table{border-collapse:collapse;width:100%;margin-top:10px;font-size:12.5px}",
        "th,td{padding:6px 8px;border-bottom:1px solid #212327;text-align:left;vertical-align:top}",
        "th{color:#857e72;font-weight:500;font-size:11px}",
        "code{color:#a8c0a0;font-size:11.5px}",
        ".bad{color:#e0806f}.warn{color:#d6b260}.ok{color:#7fa87a}",
        "</style>",
        f"<h1>{html.escape(topic.name)}</h1>",
        "<p class='sub'>코드의 AST에서 추출한 실제 읽기·쓰기다. 문서가 주장하는 흐름이 아니다.</p>",
    ]

    for report in reports:
        body.append("<div class='attempt'>")
        body.append(f"<h2>{html.escape(report['attempt'])}</h2>")

        touched = set(report["stages_touched_by_code"])
        cells = []
        for stage in report["stages_on_disk"]:
            cold = "" if stage in touched else " cold"
            label = "코드가 만짐" if stage in touched else "코드가 안 만짐"
            cells.append(f"<div class='stage{cold}'><span class='id'>{html.escape(stage)}</span>"
                         f"<span class='t'>{label}</span></div>")
        body.append("<div class='chain'>" + "<span class='arrow'>›</span>".join(cells) + "</div>")

        body.append("<table><tr><th>도구</th><th>읽는 것</th><th>쓰는 것</th></tr>")
        for tool in report["tools"]:
            reads = "<br>".join(f"<code>{html.escape(r)}</code>" for r in tool["reads"]) or "<span class='warn'>없음</span>"
            writes = "<br>".join(f"<code>{html.escape(w)}</code>" for w in tool["writes"] + tool["both"]) or "-"
            extra = "<br>".join(f"<code>{html.escape(m)}</code>" for m in tool["mentions"])
            if extra:
                reads = (reads if reads != "<span class='warn'>없음</span>" else "") + \
                        ("<br>" if reads != "<span class='warn'>없음</span>" else "") + extra
            body.append(f"<tr><td>{html.escape(tool['tool'])}</td><td>{reads}</td><td>{writes}</td></tr>")
        body.append("</table>")

        if report["orphan_outputs"]:
            items = ", ".join(f"<code>{html.escape(o)}</code>" for o in report["orphan_outputs"])
            body.append(f"<p class='bad'>어느 도구도 읽지 않는 산출물: {items}</p>")
        else:
            body.append("<p class='ok'>고아 산출물 없음</p>")
        body.append("</div>")

    out.write_text("\n".join(body), encoding="utf-8")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="코드에서 파이프라인 실제 구성을 뽑는다")
    parser.add_argument("topic", type=Path)
    parser.add_argument("--html", type=Path)
    args = parser.parse_args()

    attempts = sorted(p for p in (args.topic / "attempts").iterdir() if p.is_dir())
    reports = [analyse_attempt(a) for a in attempts]

    if args.html:
        args.html.parent.mkdir(parents=True, exist_ok=True)
        render_html(args.topic, reports, args.html)
        print(f"작성: {args.html}")

    print(json.dumps([{k: r[k] for k in
                       ("attempt", "stages_on_disk", "stages_touched_by_code",
                        "orphan_outputs", "external_inputs")}
                      for r in reports], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
