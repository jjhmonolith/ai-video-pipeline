"""Canonical on-disk layout for production runs, and a checker for it.

The layout is topic -> attempt -> stage, with two additions that the first two
runs proved were needed.

First, a topic-level shared area. Verified vote counts do not belong to an
attempt; v2 reuses v1's claim ledger unchanged, and copying facts per attempt
invites them to drift apart.

Second, every stage keeps its own rejected work. Stages are not visited once:
v2 went back from motion to look five times, and without a home for superseded
versions the names leak into the filesystem as `superseded-scattered/`,
`candidates-not-selected/` and `plate-receipt-p3retry.json`.

    runs/<topic>/
      TOPIC.md                  what the topic is, which attempts exist, verdicts
      topic/claims/             facts that outlive any attempt
      attempts/<attempt>/
        ATTEMPT.md              hypothesis, what changed from the last attempt, verdict
        tools/                  scripts belonging to this attempt only
        01-premise/ .. 08-review/
          NOTES.md              what happened here, in prose, including retries
          prompts/              exact prompt text that was sent
          output/               what this stage produced and the next stage consumes
          rejected/             candidates and superseded versions, with reasons
          qa/                   contact sheets, measurements, verification output
          receipt.json          calls, parameters, hashes, timings
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

STAGES = [
    ("01-premise", "지시사항 접수, 웹 조사, 인물·피사체·배경 정의"),
    ("02-sheet", "정의된 요소를 여러 각도의 레퍼런스 시트로 굳힌다"),
    ("03-scenario", "무슨 일이 벌어지는가. 비트와 길이 배분"),
    ("04-shot-design", "shot card, 상태쌍, 카메라, 연기"),
    ("05-plate", "컷별 이미지 생성. 시트를 물린다"),
    ("06-motion", "영상 클립 생성"),
    ("07-edit", "정보 레이어 합성, 리타이밍, 조립"),
    ("08-review", "감사, 게이트, 측정 결과"),
]
STAGE_IDS = [name for name, _ in STAGES]
STAGE_ROLES = {
    "premise": "01-premise",
    "sheet": "02-sheet",
    "scenario": "03-scenario",
    "shot_design": "04-shot-design",
    "plate": "05-plate",
    "motion": "06-motion",
    "edit": "07-edit",
    "review": "08-review",
}

# Two shapes of the same idea, both learned the hard way.
#
# The look stage used to make the sheets and the per-cut plates together, which
# put the sheet -> plate hand-off inside one stage where a stage graph cannot
# show it. A run shipped with sheets generated and never attached. Sheets now
# live beside definitions in `02-sheet`, while per-cut plates live in
# `05-plate`; a missing hand-off is therefore a visible missing edge.
#
# The brief and the research stage used to be separate, and the split had it
# backwards. The brief declared terms; research copied facts out of a shared
# topic folder that had no origin, so the stage that was supposed to establish
# what the film is about established nothing. Worse, the shared folder coupled
# the attempts: overwriting one subject file changed what every earlier attempt
# claimed to have been built from.
#
#   01-premise  takes the human's direction, searches, and establishes the cast,
#               the subject and the setting, each with its provenance. Owns its
#               facts; borrows nothing from a topic-level folder.
#   02-sheet    turns each of those definitions into reference sheets, several
#               views per element.
#   03-scenario takes them and decides what happens: the beats and how long
#               each runs. Direction and script were two stages once, and the
#               split did not survive contact. What happens and how it is timed
#               are one decision; concept had already lost stage and light to
#               the setting definitions and had only the flow left to hold.
#   04-shot-design then decides how each beat is photographed, which is a
#               different question again.
#
# The sheet sits next to the definition rather than next to production because
# it is the same act: a written description of a face and a picture of that face
# are two halves of deciding what the face is, and separating them lets the two
# drift. Concept then gets to be written while looking at what the things
# actually look like, instead of imagining them twice.
#
# What a thing *is* and what it *does* are different questions, and the second
# one cannot be answered before the first.
#
# Attempts made before these splits keep their own names. The checker accepts
# them; ensure() does not create them.
# Ids from earlier layouts, kept so old attempts still read and still pass the
# checker. They are never created.
_HISTORICAL = {
    "01-brief": "관객·약속·금지선·품질헌장",
    "02-research": "출처 조사와 주장 원장",
    "02-concept": "방향 후보와 선택",
    "03-concept": "방향 후보와 선택",
    "03-script": "대본과 비트",
    "04-script": "대본과 비트",
    "04-shot-design": "shot card, 상태쌍, 카메라, 연기",
    "05-shot-design": "shot card, 상태쌍, 카메라, 연기",
    "05-sheet": "레퍼런스 시트",
    "06-look": "이미지 생성. 스타일 프레임과 상태 판",
    "06-sheet": "레퍼런스 시트",
    "06-plate": "컷별 이미지 생성",
    "07-plate": "컷별 이미지 생성",
    "07-motion": "영상 클립 생성",
    "08-motion": "영상 클립 생성",
    "08-edit": "정보 레이어 합성, 리타이밍, 조립",
    "09-edit": "정보 레이어 합성, 리타이밍, 조립",
    "09-review": "감사, 게이트, 측정 결과",
    "10-review": "감사, 게이트, 측정 결과",
}
# An id that came back into the current layout is not legacy any more. Keeping
# it in both lists would make the mixed-scheme check blind, since every attempt
# would look like both at once.
LEGACY_STAGES = {k: v for k, v in _HISTORICAL.items() if k not in dict(STAGES)}
STAGE_TITLES = {**dict(STAGES), **LEGACY_STAGES}
# Ids that exist only in the current layout. An attempt holding one of these
# alongside a legacy-only id is half-migrated, which is worse than either.
SPLIT_STAGES = frozenset(STAGE_IDS) - frozenset(LEGACY_STAGES)

SUBDIRS = ["prompts", "output", "rejected", "qa"]
ATTEMPT_FILES = {"ATTEMPT.md", "tools", "VERSION.json", "DASHBOARD.html"}
STAGE_DIR_RE = re.compile(r"^\d\d-[a-z0-9-]+$")


@dataclass(frozen=True)
class Stage:
    root: Path

    @property
    def prompts(self) -> Path:
        return self.root / "prompts"

    @property
    def output(self) -> Path:
        return self.root / "output"

    @property
    def rejected(self) -> Path:
        return self.root / "rejected"

    @property
    def qa(self) -> Path:
        return self.root / "qa"

    @property
    def receipt(self) -> Path:
        return self.root / "receipt.json"

    @property
    def notes(self) -> Path:
        return self.root / "NOTES.md"

    def ensure(self) -> "Stage":
        for sub in SUBDIRS:
            (self.root / sub).mkdir(parents=True, exist_ok=True)
        return self


@dataclass(frozen=True)
class Attempt:
    root: Path

    def stage(self, stage_id: str) -> Stage:
        if stage_id not in STAGE_IDS and stage_id not in LEGACY_STAGES:
            raise ValueError(f"unknown stage {stage_id!r}; expected one of {STAGE_IDS}")
        return Stage(self.root / stage_id)

    def stages_on_disk(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(p.name for p in self.root.iterdir()
                      if p.is_dir() and STAGE_DIR_RE.match(p.name))

    @property
    def tools(self) -> Path:
        return self.root / "tools"

    def ensure(self) -> "Attempt":
        self.tools.mkdir(parents=True, exist_ok=True)
        for stage_id in STAGE_IDS:
            self.stage(stage_id).ensure()
        return self


@dataclass(frozen=True)
class Topic:
    root: Path

    def attempt(self, name: str) -> Attempt:
        return Attempt(self.root / "attempts" / name)

    @property
    def claims(self) -> Path:
        return self.root / "topic" / "claims"

    def ensure(self) -> "Topic":
        self.claims.mkdir(parents=True, exist_ok=True)
        (self.root / "attempts").mkdir(parents=True, exist_ok=True)
        return self

    def attempts(self) -> list[str]:
        holder = self.root / "attempts"
        return sorted(p.name for p in holder.iterdir() if p.is_dir()) if holder.exists() else []


def check(topic_root: Path) -> dict:
    """Report anything sitting outside the layout, so it cannot quietly decay."""
    topic = Topic(topic_root)
    problems: list[str] = []

    if not (topic_root / "TOPIC.md").exists():
        problems.append("TOPIC.md 없음")

    for name in topic.attempts():
        attempt = topic.attempt(name)
        if not (attempt.root / "ATTEMPT.md").exists():
            problems.append(f"{name}: ATTEMPT.md 없음")

        for entry in attempt.root.iterdir():
            # VERSION.json is the version-control snapshot, DASHBOARD.html the
            # generated index; both describe the attempt as a whole.
            if entry.name in ATTEMPT_FILES or entry.name in STAGE_IDS:
                continue
            if entry.name in LEGACY_STAGES or entry.name.startswith("."):
                continue
            problems.append(f"{name}: 단계 밖에 {entry.name}")

        found = attempt.stages_on_disk()
        # Half-renamed is worse than either scheme, because a tool written
        # against one set of names silently reads nothing from the other.
        old = [s for s in found if s in LEGACY_STAGES]
        new = [s for s in found if s in SPLIT_STAGES]
        if old and new:
            problems.append(f"{name}: 옛 단계 {old} 와 새 단계 {new} 가 섞였다")

        for stage_id in found:
            stage = attempt.stage(stage_id)
            for entry in stage.root.iterdir():
                if entry.name in SUBDIRS or entry.name in {"receipt.json", "NOTES.md"}:
                    continue
                if entry.name.startswith("."):
                    continue
                problems.append(f"{name}/{stage_id}: 규약 밖 파일 {entry.name}")

    return {
        "topic": topic_root.name,
        "attempts": topic.attempts(),
        "problems": problems,
        "ok": not problems,
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="run layout checker")
    parser.add_argument("topic", type=Path)
    args = parser.parse_args()
    report = check(args.topic)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
