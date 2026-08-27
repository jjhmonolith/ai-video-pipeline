"""Shot cards must carry a camera in four parts, one movement, and authored timing.

Vocabulary and rules come from two practitioner videos, recorded in
`docs/design/shot-grammar.md` with their timestamps. The terms below are the
ones those videos use; they are not translated or renamed, so a card reads the
same way a person would say it out loud.

Three findings drive the checks.

`end` is the part people drop, and without it the model does not know where to
stop, so the last second drifts. We saw the same thing: a 13.7s take came back
with its middle replaced by a close-up nobody asked for, from a prompt that
named no speed and no end.

One movement per cut. Rotating while zooming while rising gives the model no
single instruction and it just shakes.

Duration is a Stage-04 creative decision, not a table lookup.  The validator
requires an explicit reason and temporal design but does not impose fixed
seconds by purpose: slow motion, frozen-world camera moves, ellipsis and time
compression deliberately break real-time action arithmetic.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

MOVEMENTS = {
    "스태틱 샷", "달리 인", "슬로우 줌 인", "돌리 줌", "아크 샷", "사이드 트래킹",
    "팔로우 샷", "리버스 트래킹", "휩 팬", "크레인 업", "드론 풀백", "푸시 스루",
    "핸드헬드", "스노리캠", "1인칭 시점", "랙 포커스",
}
ANGLES = {"리어 샷", "로우 앵글", "하이 앵글", "오버헤드", "더치 앵글", "아이 레벨"}
SIZES = {
    "익스트림 롱샷", "롱샷", "풀샷", "미디엄 풀샷", "미디엄 샷",
    "미디엄 클로즈업", "클로즈업", "빅 클로즈업", "익스트림 클로즈업",
}
COMPOSITIONS = {"싱글", "투샷", "쓰리샷", "오버 더 숄더", "인서트", "컷어웨이", "리액션"}
CAMERA_PARTS = ("movement", "speed", "framing", "end")

CUT_PURPOSES = {"insert", "action", "emotion", "establishing", "long_take"}
SUBJECT_SHEET_KINDS = {"character", "subject", "none"}


def check_card(card: dict) -> list[str]:
    shot = card.get("shot_id") or card.get("take_id") or "?"
    problems: list[str] = []

    camera = card.get("camera")
    if not isinstance(camera, dict):
        return [f"{shot}: camera 를 네 조각으로 선언해야 한다 {CAMERA_PARTS}"]

    for part in CAMERA_PARTS:
        if not camera.get(part):
            hint = " 끝을 정하지 않으면 마지막 1초가 흐른다" if part == "end" else ""
            problems.append(f"{shot}: camera.{part} 없음.{hint}")

    movement = camera.get("movement")
    if movement:
        named = [m for m in MOVEMENTS if m in movement]
        if not named:
            problems.append(f"{shot}: movement 가 어휘 목록에 없다. {sorted(MOVEMENTS)}")
        elif len(named) > 1:
            problems.append(
                f"{shot}: 한 컷에 무브먼트가 둘 이상이다 ({', '.join(named)}). "
                f"카메라가 어디로 갈지 몰라 떨기만 한다")

    angle = camera.get("angle")
    if angle and not any(a in angle for a in ANGLES):
        problems.append(f"{shot}: angle 이 어휘 목록에 없다. {sorted(ANGLES)}")

    size = card.get("frame_size")
    if not size:
        problems.append(f"{shot}: frame_size 없음. 인물을 어디서 자르는지가 프레이밍의 알맹이다")
    elif size not in SIZES:
        problems.append(f"{shot}: frame_size 가 어휘 목록에 없다. {sorted(SIZES)}")

    composition = card.get("composition")
    if composition and composition not in COMPOSITIONS:
        problems.append(f"{shot}: composition 이 어휘 목록에 없다. {sorted(COMPOSITIONS)}")

    purpose = card.get("cut_purpose")
    seconds = card.get("seconds")
    if not purpose:
        problems.append(f"{shot}: cut_purpose 없음. {sorted(CUT_PURPOSES)}")
    elif purpose not in CUT_PURPOSES:
        problems.append(f"{shot}: cut_purpose 는 {sorted(CUT_PURPOSES)} 중 하나여야 한다")
    elif seconds is not None:
        if not isinstance(seconds, (int, float)) or isinstance(seconds, bool) or seconds <= 0:
            problems.append(f"{shot}: seconds는 Stage 04가 정한 양수여야 한다")
        temporal = card.get("temporal_design") or {}
        if not (temporal.get("dramatic_reason") or card.get("duration_rationale")):
            problems.append(f"{shot}: timing의 극적 이유가 없다")
        if purpose == "long_take" and movement and movement.strip() != "스태틱 샷":
            named = [m for m in MOVEMENTS if m in movement]
            if len(named) > 1:
                problems.append(f"{shot}: 롱테이크는 무브먼트를 반드시 하나로 간다")

    return problems


def check_sheet(payload: dict) -> list[str]:
    sheet = payload.get("subject_sheet")
    if not isinstance(sheet, dict):
        return ["subject_sheet 선언 없음. character / subject / none 중 하나를 밝혀야 한다"]

    kind = sheet.get("kind")
    problems: list[str] = []
    if kind not in SUBJECT_SHEET_KINDS:
        problems.append(f"subject_sheet.kind 는 {sorted(SUBJECT_SHEET_KINDS)} 중 하나여야 한다")
    if kind == "none" and not sheet.get("reason"):
        problems.append("subject_sheet.kind 가 none 이면 사유가 있어야 한다. "
                        "매 컷 다른 장소이고 반복되는 대상이 없을 때만 생략한다")
    if kind in {"character", "subject"}:
        panels = sheet.get("panels") or []
        if len(panels) < 3:
            problems.append(f"{kind} 시트는 최소 3패널이다. 정면, 후면 또는 반대편, 세부 클로즈업")
    return problems


def check(cards_path: Path) -> dict:
    payload = json.loads(cards_path.read_text(encoding="utf-8"))
    cards = payload.get("takes") or payload.get("cards") or []
    problems = check_sheet(payload)
    for card in cards:
        problems.extend(check_card(card))
    return {"file": cards_path.name, "cards": len(cards),
            "problems": problems, "ok": not problems}


def main() -> int:
    parser = argparse.ArgumentParser(description="촬영 문법 게이트")
    parser.add_argument("cards", type=Path)
    args = parser.parse_args()
    report = check(args.cards)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
