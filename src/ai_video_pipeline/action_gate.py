"""Refuse shot cards that ask people to perform things nobody does.

v2 failed here. All eight cards' `performance` fields read some variant of
"places a bundle", "sets down a bundle", "lifts the bundle out of frame". Not
one was a real counting-hall job. They were choreography for a bar chart, cast
with humans and shot photorealistically, and the finished frames carried an
"AI 생성 재현 영상" disclosure over a scene that has never happened.

The cause was upstream of props and upstream of the metaphor. Once the brief
declared that the screen must *be* the arithmetic, every action got derived
from the equation instead of from the room, and nothing in the pipeline asked
whether the resulting action exists.

So every card must now declare, per action:

    real_world_action   이 동작을 무엇이라 부르는가
    who_performs_it     실제로 누가 하는가
    evidence_class      documented | plausible | invented

`invented` is not forbidden. It is forbidden to shoot it photorealistically
and label it a reenactment. An invented action must be rendered as graphic
(`render_mode: graphic`), where a bar meaning a vote margin is honest because
a bar is visibly a bar.

A second reason to care, observed once and worth testing again: unreal action
seems to make generation drift worse. T2's middle abandoned the locked-off
wide for a hand close-up nobody asked for, plausibly because "a worker sets
down one bundle and a huge stack appears" is not in the model's priors, so it
fell back on something it knows.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

EVIDENCE_CLASSES = {"documented", "plausible", "invented"}
RENDER_MODES = {"photoreal", "graphic", "hybrid"}

# Phrasings that describe moving a quantity into position rather than doing a job.
CHART_CHOREOGRAPHY = [
    "묶음을 놓", "묶음을 얹", "묶음을 들어", "기둥을 세", "기둥을 쌓",
    "높이를 맞", "막대를 올", "수치를 배치",
]


def check_card(card: dict) -> list[str]:
    problems: list[str] = []
    shot = card.get("shot_id") or card.get("take_id") or "?"

    performance = card.get("performance")
    if not performance:
        return [f"{shot}: performance 없음"]

    reality = card.get("action_reality")
    if not isinstance(reality, dict):
        return [f"{shot}: action_reality 선언 없음. 이 동작을 실제로 하는 사람이 있는지 밝혀야 한다"]

    for field in ("real_world_action", "who_performs_it", "evidence_class"):
        if not reality.get(field):
            problems.append(f"{shot}: action_reality.{field} 없음")

    evidence = reality.get("evidence_class")
    if evidence and evidence not in EVIDENCE_CLASSES:
        problems.append(f"{shot}: evidence_class 는 {sorted(EVIDENCE_CLASSES)} 중 하나여야 한다")

    mode = card.get("render_mode")
    if mode and mode not in RENDER_MODES:
        problems.append(f"{shot}: render_mode 는 {sorted(RENDER_MODES)} 중 하나여야 한다")

    if evidence == "invented":
        if mode == "photoreal":
            problems.append(
                f"{shot}: 실재하지 않는 동작을 photoreal 로 찍을 수 없다. "
                f"graphic 으로 바꾸거나 실재하는 동작으로 다시 설계한다")
        if card.get("disclosure_as_reenactment"):
            problems.append(f"{shot}: 일어난 적 없는 장면에 재현 고지를 붙일 수 없다")

    if evidence == "documented" and not reality.get("source"):
        problems.append(f"{shot}: documented 로 선언했으면 source 가 있어야 한다")

    hits = [phrase for phrase in CHART_CHOREOGRAPHY if phrase in performance]
    if hits and evidence != "invented":
        problems.append(
            f"{shot}: performance 가 차트 안무로 읽힌다 ({', '.join(hits)}). "
            f"실제 직무라면 그 직무의 이름으로 다시 쓰고, 아니라면 evidence_class 를 invented 로 바꾼다")

    return problems


def check(cards_path: Path) -> dict:
    payload = json.loads(cards_path.read_text(encoding="utf-8"))
    cards = payload.get("takes") or payload.get("cards") or []
    problems: list[str] = []
    for card in cards:
        problems.extend(check_card(card))
    return {
        "file": cards_path.name,
        "cards": len(cards),
        "problems": problems,
        "ok": not problems,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="shot card 동작 실재성 게이트")
    parser.add_argument("cards", type=Path)
    args = parser.parse_args()
    report = check(args.cards)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
