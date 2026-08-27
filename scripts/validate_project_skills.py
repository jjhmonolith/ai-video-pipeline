#!/usr/bin/env python3
"""Validate the project-local v3 skill entries without external packages."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / ".agents" / "skills"
EXPECTED = {
    "video-pipeline-orchestrator",
    "video-pipeline-recovery",
    "video-stage01-premise",
    "video-stage02-sheets",
    "video-stage03-scenario",
    "video-stage04-shot-design",
    "video-stage05-plates",
    "video-stage05b-motion-prompt",
    "video-stage06-motion",
    "video-stage07-edit",
    "video-stage08-review",
}
FRONTMATTER = re.compile(r"\A---\n(?P<body>.*?)\n---(?:\n|\Z)", re.DOTALL)
FIELD = re.compile(r"^(?P<key>[a-zA-Z0-9_-]+):\s*(?P<value>.+?)\s*$")


def validate() -> list[str]:
    problems: list[str] = []
    actual = {path.name for path in SKILL_ROOT.iterdir() if (path / "SKILL.md").is_file()}
    missing = sorted(EXPECTED - actual)
    unexpected = sorted(actual - EXPECTED)
    if missing:
        problems.append(f"missing skills: {', '.join(missing)}")
    if unexpected:
        problems.append(f"unexpected active skills: {', '.join(unexpected)}")
    for name in sorted(EXPECTED & actual):
        path = SKILL_ROOT / name / "SKILL.md"
        text = path.read_text(encoding="utf-8")
        match = FRONTMATTER.match(text)
        if not match:
            problems.append(f"{name}: invalid YAML frontmatter boundary")
            continue
        fields: dict[str, str] = {}
        for line in match.group("body").splitlines():
            parsed = FIELD.match(line)
            if parsed:
                fields[parsed.group("key")] = parsed.group("value").strip('"\'')
        if fields.get("name") != name:
            problems.append(f"{name}: frontmatter name does not match directory")
        description = fields.get("description", "")
        if not description or len(description) > 1024:
            problems.append(f"{name}: description must contain 1-1024 characters")
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) or len(name) > 64:
            problems.append(f"{name}: invalid skill name")
        agent_yaml = SKILL_ROOT / name / "agents" / "openai.yaml"
        if not agent_yaml.is_file():
            problems.append(f"{name}: agents/openai.yaml is missing")
    return problems


def main() -> int:
    problems = validate()
    if problems:
        for problem in problems:
            print(f"FAIL {problem}")
        return 1
    print(f"PASS {len(EXPECTED)} project skills")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
