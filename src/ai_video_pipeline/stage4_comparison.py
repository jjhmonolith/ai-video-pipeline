"""Build blind human/AI comparison artifacts for the M1–M4 canaries."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat

from .contract import load as load_contract
from .stage4_experiment import METHODS

BLIND = {
    "A": "M3-atomic-locked",
    "B": "M1-prose-baseline",
    "C": "M4-h3-adaptive",
    "D": "M2-state-pair",
}


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _font(size: int) -> ImageFont.ImageFont:
    for path in ("/System/Library/Fonts/AppleSDGothicNeo.ttc",
                 "/System/Library/Fonts/Supplemental/Arial.ttf"):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _fit(path: Path, size: tuple[int, int]) -> Image.Image:
    image = Image.open(path).convert("RGB")
    image.thumbnail(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", size, "#111111")
    canvas.paste(image, ((size[0] - image.width) // 2, (size[1] - image.height) // 2))
    return canvas


def _pixel_delta(start: Path, end: Path) -> dict:
    a = Image.open(start).convert("RGB").resize((192, 336), Image.Resampling.LANCZOS)
    b = Image.open(end).convert("RGB").resize(a.size, Image.Resampling.LANCZOS)
    stat = ImageStat.Stat(ImageChops.difference(a, b))
    mean = sum(stat.mean) / (3 * 255)
    rms = sum(stat.rms) / (3 * 255)
    return {"mean_absolute_delta": round(mean, 4), "rms_delta": round(rms, 4),
            "interpretation": "whole-frame proxy only; cannot separate intended action from camera/background drift"}


def _prompt_audit(attempt: Path, method_root: Path, plate_root: Path,
                  out: Path) -> Path:
    """Expose the actual comparison prompts after the blind human review."""
    lines = [
        "# 4단계 카나리아 프롬프트 감사",
        "",
        f"- attempt: `{attempt}`",
        "- 아래 `plate prompt`와 `end state`는 비교 이미지를 만들 때 사용한 4단계 핵심 지시다.",
        "- 링크된 `start-prompt.txt`와 `end-prompt.txt`에는 1단계 방향·정의, 2단계 시트 순서, "
        "4단계 전체 shot 계약까지 포함된 실제 5단계 전달문이 있다.",
        "- `H3 motion prompt`는 다음 영상 단계용이며 이번 5단계 이미지 생성에는 직접 쓰이지 않았다.",
        "",
        "- 같은 prompt hash는 핵심 4단계 지시가 같다는 뜻이다. 이 경우 한 장씩의 차이는 방식 효과가 아니라 생성 변동일 수 있다.",
        "",
        "| 후보 | 실제 방식 | 핵심 차이 | plate hash | end hash | 요청 후보 수 |",
        "|---|---|---|---|---|---:|",
    ]
    for blind_id, method_id in BLIND.items():
        method = METHODS[method_id]
        design = json.loads((method_root / method_id / "shot-design.json").read_text(encoding="utf-8"))
        shot = next(item for item in design["shots"]
                    if item["shot_id"] == design["canary"]["shot_id"])
        plate_hash = hashlib.sha256(str(shot.get("plate_prompt", "")).encode()).hexdigest()[:8]
        end_hash = hashlib.sha256(str(shot.get("end_state", "")).encode()).hexdigest()[:8]
        lines.append(
            f"| {blind_id} | `{method_id}` | {method['title']} | `{plate_hash}` | "
            f"`{end_hash}` | {shot.get('candidate_count', 1)} |"
        )

    for blind_id, method_id in BLIND.items():
        design_path = method_root / method_id / "shot-design.json"
        design = json.loads(design_path.read_text(encoding="utf-8"))
        canary_id = design["canary"]["shot_id"]
        shot = next(item for item in design["shots"] if item["shot_id"] == canary_id)
        start_full = plate_root / method_id / "start-prompt.txt"
        end_full = plate_root / method_id / "end-prompt.txt"
        lines.extend([
            "",
            f"## 후보 {blind_id} · `{method_id}`",
            "",
            f"가설: {METHODS[method_id]['hypothesis']}",
            "",
            f"카나리아: `{shot['shot_id']}` / `{shot['beat_id']}` / H3 `{shot['h3_route']}` / "
            f"후보 수 `{shot['candidate_count']}`",
            "",
            f"- [실제 5단계 START 전체 프롬프트](<{start_full.resolve()}>)",
            (f"- [실제 5단계 END 전체 프롬프트](<{end_full.resolve()}>)"
             if end_full.read_text(encoding="utf-8").strip() else
             "- END 프롬프트 없음: 이 방식은 끝 상태를 설계하지 않았다."),
            "",
            "### 4단계 plate prompt",
            "",
            "```text",
            str(shot.get("plate_prompt", "")),
            "```",
            "",
            "### 시작·끝 상태",
            "",
            f"- START: {shot.get('start_state') or '명시 없음'}",
            f"- END: {shot.get('end_state') or '명시 없음'}",
            f"- semantic path: {shot.get('semantic_motion_path') or '명시 없음'}",
            f"- change budget: {shot.get('change_budget') or '명시 없음'}",
            "",
            "### H3 motion prompt",
            "",
            "```text",
            str(shot.get("h3_motion_prompt", "")),
            "```",
        ])
    target = out / "prompt-audit.md"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def build(attempt: Path) -> dict:
    contract = load_contract(attempt)
    source = attempt / contract.stage_for("plate", "05-plate") / "qa" / "experiments" / "stage4-methods"
    out = attempt / contract.stage_for("shot_design", "04-shot-design") / "qa" / "experiments" / "comparison"
    out.mkdir(parents=True, exist_ok=True)
    key = {"schema_version": "stage4-blind-key.v1", "created_at": _now(), "mapping": BLIND,
           "do_not_show_before_human_selection": True}
    (out / "blind-key.json").write_text(json.dumps(key, ensure_ascii=False, indent=2), encoding="utf-8")

    tile_w, tile_h, header = 760, 700, 74
    board = Image.new("RGB", (tile_w * 2, (tile_h + header) * 2), "#202020")
    draw = ImageDraw.Draw(board)
    title_font, small_font = _font(34), _font(22)
    metrics = {}
    for index, (blind_id, method_id) in enumerate(BLIND.items()):
        folder = source / method_id
        start, end = folder / "start.png", folder / "end.png"
        x, y = (index % 2) * tile_w, (index // 2) * (tile_h + header)
        draw.rectangle((x, y, x + tile_w - 1, y + header - 1), fill="#111111")
        draw.text((x + 22, y + 16), f"후보 {blind_id}", font=title_font, fill="white")
        draw.text((x + tile_w // 2 - 36, y + 23), "START", font=small_font, fill="#8bd3ff")
        draw.text((x + tile_w - 110, y + 23), "END", font=small_font, fill="#ffd28b")
        half = tile_w // 2
        board.paste(_fit(start, (half, tile_h)), (x, y + header))
        if end.exists():
            board.paste(_fit(end, (half, tile_h)), (x + half, y + header))
            metrics[blind_id] = _pixel_delta(start, end)
        else:
            blank = Image.new("RGB", (half, tile_h), "#292929")
            bd = ImageDraw.Draw(blank)
            bd.multiline_text((42, tile_h // 2 - 50), "끝 상태를\n설계하지 않은 방식", font=title_font,
                              fill="#c8c8c8", align="center", spacing=12)
            board.paste(blank, (x + half, y + header))
            metrics[blind_id] = {"not_applicable": True}
    board_path = out / "blind-comparison.png"
    board.save(board_path, quality=95)

    packet = {
        "schema_version": "stage4-human-comparison.v1", "created_at": _now(),
        "attempt": str(attempt), "comparison_board": str(board_path),
        "fixed_input": "same immutable stages 01-03; same canary beat per candidate",
        "legacy_gate_failures": "recorded but non-blocking for this experiment",
        "evaluation_order": [
            "시작판이 실제로 동작 시작 전인가",
            "끝판에서 지시한 변화가 충분히 보이는가",
            "시작/끝 사이에 카메라·배경·정체성 등 불변 요소가 유지됐는가",
            "이 상태판이 H3가 잘못된 방향/과다 변화 없이 움직일 여지를 주는가",
        ],
        "one_question": "전체 4단계 기본 방식으로 발전시킬 후보는 A/B/C/D 중 무엇인가?",
        "answer_modes": ["select", "combine", "preserve_and_change", "free_text"],
        "ai_scores_hidden_until_human_choice": True,
        "ai_review_sealed": str(out / "ai-review.sealed.json"),
        "human_selection": None,
        "pixel_change_proxy": metrics,
    }
    packet_path = out / "human-review.json"
    if packet_path.exists():
        previous = json.loads(packet_path.read_text(encoding="utf-8"))
        for field in ("human_selection", "human_observations", "human_reviewed_at"):
            if previous.get(field) is not None:
                packet[field] = previous[field]
        if packet.get("human_reviewed_at"):
            packet["ai_scores_hidden_until_human_choice"] = False
    packet_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
    prompt_audit = _prompt_audit(
        attempt,
        attempt / contract.stage_for("shot_design", "04-shot-design") / "qa" / "experiments" / "methods",
        source,
        out,
    )
    return {"board": str(board_path), "human_review": str(packet_path),
            "blind_key": str(out / "blind-key.json"), "prompt_audit": str(prompt_audit),
            "pixel_change_proxy": metrics}


def main() -> int:
    parser = argparse.ArgumentParser(description="build blind stage04 method comparison")
    parser.add_argument("attempt", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.attempt), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
