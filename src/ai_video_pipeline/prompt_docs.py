"""Turn prompt packs into something a person can actually read.

Prompt packs are stored as JSON because the runners consume them, but nobody
reviews a wall of escaped strings. This renders each stage's packs into
PROMPTS.md, and each attempt into a single self-contained DASHBOARD.html for
browsing.

The renderer does not know about any particular pack schema. It walks the JSON
looking for lists of objects that carry a `prompt`-ish field, treats those as
the prompt entries, and shows whatever other keys they have as their labels.
So a new pack shape needs no code change.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any, Iterable

PROMPT_KEYS = ("prompt", "repair_prompt", "end_frame_prompt", "text")
ID_KEYS = ("id", "shot", "shot_id", "plate", "name", "used_by")
SKIP_META = {"plates", "shots", "images", "cards", "items", "entries"}


def _looks_like_prompt_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and value
        and all(isinstance(v, dict) for v in value)
        and any(any(k in v for k in PROMPT_KEYS) for v in value)
    )


def _find_prompt_lists(node: Any, path: str = "") -> Iterable[tuple[str, list]]:
    if _looks_like_prompt_list(node):
        yield path or "prompts", node
        return
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _find_prompt_lists(value, f"{path}.{key}" if path else key)


def _label(entry: dict, index: int) -> str:
    for key in ID_KEYS:
        if entry.get(key):
            return str(entry[key])
    return f"#{index + 1}"


def _detail_rows(entry: dict) -> list[tuple[str, str]]:
    rows = []
    for key, value in entry.items():
        if key in PROMPT_KEYS or key in ID_KEYS:
            continue
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        rows.append((key, str(value)))
    return rows


def render_pack_markdown(pack_path: Path) -> str:
    data = json.loads(pack_path.read_text(encoding="utf-8"))
    lines = [f"# {pack_path.stem}", ""]

    meta = [(k, v) for k, v in data.items()
            if not isinstance(v, (dict, list)) and k not in SKIP_META] if isinstance(data, dict) else []
    if meta:
        lines += ["| 항목 | 값 |", "|---|---|"]
        lines += [f"| {k} | {str(v)} |" for k, v in meta]
        lines.append("")

    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, list) and value and all(isinstance(v, str) for v in value):
                lines += [f"## {key}", ""] + [f"- {v}" for v in value] + [""]
            elif isinstance(value, str) and len(value) > 160:
                lines += [f"## {key}", "", value, ""]

    for group, entries in _find_prompt_lists(data):
        lines += [f"## {group}  ·  {len(entries)}개", ""]
        for index, entry in enumerate(entries):
            lines.append(f"### {_label(entry, index)}")
            details = _detail_rows(entry)
            if details:
                lines += ["", "| 항목 | 값 |", "|---|---|"]
                lines += [f"| {k} | {v[:300]} |" for k, v in details]
            for key in PROMPT_KEYS:
                if entry.get(key):
                    heading = "프롬프트" if key == "prompt" else key
                    lines += ["", f"**{heading}**", "", "```text", str(entry[key]), "```"]
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_stage(stage_dir: Path) -> dict | None:
    prompts_dir = stage_dir / "prompts"
    packs = sorted(p for p in prompts_dir.glob("*.json")) if prompts_dir.exists() else []
    if not packs:
        return None

    body = [f"# {stage_dir.name} 프롬프트", "",
            "이 문서는 `prompts/` 의 JSON에서 자동 생성된다. 원본을 고치고 다시 생성한다.", ""]
    total = 0
    for pack in packs:
        rendered = render_pack_markdown(pack)
        total += sum(len(entries) for _, entries in _find_prompt_lists(
            json.loads(pack.read_text(encoding="utf-8"))))
        body += [rendered, "", "---", ""]

    target = prompts_dir / "PROMPTS.md"
    target.write_text("\n".join(body).rstrip() + "\n", encoding="utf-8")
    return {"stage": stage_dir.name, "packs": [p.name for p in packs],
            "prompt_count": total, "markdown": str(target.name)}


def _count(path: Path) -> int:
    return sum(1 for p in path.rglob("*") if p.is_file()) if path.exists() else 0


def render_dashboard(attempt_dir: Path, stage_reports: list[dict]) -> Path:
    reports = {r["stage"]: r for r in stage_reports}
    stages = sorted(p for p in attempt_dir.iterdir() if p.is_dir() and p.name[0].isdigit())

    rows = []
    for stage in stages:
        report = reports.get(stage.name)
        notes = stage / "NOTES.md"
        summary = ""
        if notes.exists():
            for line in notes.read_text(encoding="utf-8").splitlines():
                if line.strip() and not line.startswith("#"):
                    summary = line.strip()
                    break
        rows.append({
            "stage": stage.name,
            "prompts": report["prompt_count"] if report else 0,
            "output": _count(stage / "output"),
            "rejected": _count(stage / "rejected"),
            "qa": _count(stage / "qa"),
            "notes": summary,
            "has_md": bool(report),
        })

    attempt_doc = attempt_dir / "ATTEMPT.md"
    intro = ""
    if attempt_doc.exists():
        lines = [l for l in attempt_doc.read_text(encoding="utf-8").splitlines() if l.strip()]
        intro = " ".join(lines[1:4])[:400]

    body = [
        "<title>" + html.escape(attempt_dir.name) + "</title>",
        "<style>",
        "body{background:#111214;color:#e8e4dc;font:15px/1.65 -apple-system,'Apple SD Gothic Neo',sans-serif;",
        "margin:0;padding:40px 28px;max-width:1000px;margin:0 auto}",
        "h1{font-size:26px;margin:0 0 6px}h2{font-size:17px;margin:34px 0 10px;color:#b9ae99}",
        "p.intro{color:#9a9285;margin:0 0 26px}",
        "table{border-collapse:collapse;width:100%;font-size:14px}",
        "th,td{padding:9px 10px;border-bottom:1px solid #26282c;text-align:left;vertical-align:top}",
        "th{color:#8e867a;font-weight:500;font-size:12px;letter-spacing:.04em}",
        "td.n{text-align:right;font-variant-numeric:tabular-nums;color:#cfc7b8}",
        "td.z{color:#4d4f54}",
        ".stage{color:#e8e4dc;font-weight:600}",
        ".note{color:#8e867a;font-size:13px}",
        "a{color:#c0a678;text-decoration:none;border-bottom:1px solid #4a4033}",
        "</style>",
        f"<h1>{html.escape(attempt_dir.name)}</h1>",
        f"<p class='intro'>{html.escape(intro)}</p>",
        "<h2>단계별 산출물</h2>",
        "<table><tr><th>단계</th><th>프롬프트</th><th>output</th><th>rejected</th><th>qa</th><th>메모</th></tr>",
    ]
    for row in rows:
        stage_cell = f"<span class='stage'>{html.escape(row['stage'])}</span>"
        if row["has_md"]:
            stage_cell += f" <a href='{html.escape(row['stage'])}/prompts/PROMPTS.md'>프롬프트</a>"
        cells = "".join(
            f"<td class='n{' z' if row[k] == 0 else ''}'>{row[k]}</td>"
            for k in ("prompts", "output", "rejected", "qa")
        )
        body.append(f"<tr><td>{stage_cell}</td>{cells}"
                    f"<td class='note'>{html.escape(row['notes'])}</td></tr>")
    body.append("</table>")
    body.append("<h2>읽는 법</h2><p class='note'>output은 다음 단계가 받아 쓰는 것, "
                "rejected는 버린 후보와 폐기 판본, qa는 콘택트시트와 측정 결과다. "
                "각 단계 NOTES.md에 되돌린 기록이 시간순으로 있다.</p>")

    target = attempt_dir / "DASHBOARD.html"
    target.write_text("\n".join(body), encoding="utf-8")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="프롬프트 팩을 읽기 좋은 문서로 렌더")
    parser.add_argument("topic", type=Path)
    args = parser.parse_args()

    attempts = sorted(p for p in (args.topic / "attempts").iterdir() if p.is_dir())
    for attempt in attempts:
        reports = []
        for stage in sorted(p for p in attempt.iterdir() if p.is_dir() and p.name[0].isdigit()):
            report = render_stage(stage)
            if report:
                reports.append(report)
                print(f"{attempt.name}/{stage.name}: 프롬프트 {report['prompt_count']}개 -> PROMPTS.md")
        dashboard = render_dashboard(attempt, reports)
        print(f"{attempt.name}: {dashboard.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
