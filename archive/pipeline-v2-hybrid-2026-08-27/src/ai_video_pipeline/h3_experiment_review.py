"""Probe, summarize and blind the H3 anchor-ablation clips."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat

from .contract import load as load_contract
from .h3_conditioning_experiment import EXPERIMENT_ID


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _font(size: int) -> ImageFont.ImageFont:
    for path in ("/System/Library/Fonts/AppleSDGothicNeo.ttc",
                 "/System/Library/Fonts/Supplemental/Arial.ttf"):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _probe(path: Path) -> dict:
    command = [
        "ffprobe", "-v", "error", "-show_entries",
        "stream=index,codec_type,codec_name,width,height,r_frame_rate,nb_frames:format=duration,size",
        "-of", "json", str(path),
    ]
    return json.loads(subprocess.run(command, check=True, capture_output=True, text=True).stdout)


def _extract(video: Path, destination: Path) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    for existing in destination.glob("*.png"):
        existing.unlink()
    command = [
        "ffmpeg", "-v", "error", "-y", "-i", str(video),
        "-vf", "select=eq(n\\,0)+eq(n\\,62)+eq(n\\,123)",
        "-vsync", "0", str(destination / "%02d.png"),
    ]
    subprocess.run(command, check=True)
    return sorted(destination.glob("*.png"))


def _copy_without_audio(source: Path, destination: Path) -> None:
    """Make a lossless video-only blind copy; H3 speech is not an evaluation input."""
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-i", str(source),
        "-map", "0:v:0", "-c:v", "copy", "-an", str(destination),
    ], check=True)


def _delta(a: Path, b: Path) -> dict:
    first = Image.open(a).convert("RGB").resize((192, 336), Image.Resampling.LANCZOS)
    second = Image.open(b).convert("RGB").resize(first.size, Image.Resampling.LANCZOS)
    stat = ImageStat.Stat(ImageChops.difference(first, second))
    return {
        "mean_absolute": round(sum(stat.mean) / (3 * 255), 4),
        "rms": round(sum(stat.rms) / (3 * 255), 4),
    }


def _fit(path: Path, size: tuple[int, int]) -> Image.Image:
    image = Image.open(path).convert("RGB")
    image.thumbnail(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", size, "#101010")
    canvas.paste(image, ((size[0] - image.width) // 2, (size[1] - image.height) // 2))
    return canvas


def build(attempt: Path) -> dict:
    attempt = attempt.resolve()
    contract = load_contract(attempt)
    root = (attempt / contract.stage_for("motion", "06-motion") / "qa" /
            "experiments" / EXPERIMENT_ID)
    receipt_path = root / "receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if not receipt.get("all_completed"):
        raise RuntimeError("generation receipt is not complete")

    records = []
    frame_root = root / "qa" / "frames"
    for record in receipt["records"]:
        files = [Path(item) for item in record["generation"]["files"] if item.endswith(".mp4")]
        if len(files) != 1 or not files[0].exists():
            raise RuntimeError(f"one local mp4 required for {record['record_id']}: {files}")
        video = files[0]
        frames = _extract(video, frame_root / record["record_id"])
        if len(frames) != 3:
            raise RuntimeError(f"expected first/mid/last frames for {record['record_id']}")
        probe = _probe(video)
        streams = probe.get("streams", [])
        video_stream = next(item for item in streams if item.get("codec_type") == "video")
        records.append({
            **record,
            "video": str(video),
            "probe": probe,
            "format_ok": (
                int(video_stream.get("width", 0)) == int(record["width"]) and
                int(video_stream.get("height", 0)) == int(record["height"]) and
                video_stream.get("r_frame_rate") == "24/1" and
                int(video_stream.get("nb_frames", 0)) == 124
            ),
            "audio_present": any(item.get("codec_type") == "audio" for item in streams),
            "frames": [str(path) for path in frames],
            "first_anchor_delta": _delta(Path(record["first_frame"]["path"]), frames[0]),
            "last_anchor_delta": (_delta(Path(record["last_frame"]["path"]), frames[-1])
                                  if record.get("last_frame") else None),
            "generated_first_to_mid_delta": _delta(frames[0], frames[1]),
            "generated_first_to_last_delta": _delta(frames[0], frames[-1]),
        })

    # The public copies never expose a method or condition in their filename.
    ordered = sorted(records, key=lambda item: hashlib.sha256(
        f"{receipt['topic']}::{item['record_id']}".encode()).hexdigest())
    mapping = {chr(65 + index): item["record_id"] for index, item in enumerate(ordered)}
    comparison = root / "comparison"
    blind_clips = comparison / "blind-clips"
    blind_clips.mkdir(parents=True, exist_ok=True)
    public_records = []
    for code, record_id in mapping.items():
        record = next(item for item in records if item["record_id"] == record_id)
        target = blind_clips / f"{code}.mp4"
        _copy_without_audio(Path(record["video"]), target)
        public_records.append({"candidate": code, "video": str(target),
                               "duration_seconds": float(record["seconds"])})

    # Two-column contact sheet; each tile shows first, middle and final frames.
    image_w, image_h, header = 230, 402, 52
    tile_w, tile_h = image_w * 3, image_h + header
    rows = (len(mapping) + 1) // 2
    board = Image.new("RGB", (tile_w * 2, tile_h * rows), "#202020")
    draw = ImageDraw.Draw(board)
    label_font, small_font = _font(30), _font(18)
    for index, (code, record_id) in enumerate(mapping.items()):
        record = next(item for item in records if item["record_id"] == record_id)
        x, y = (index % 2) * tile_w, (index // 2) * tile_h
        draw.rectangle((x, y, x + tile_w - 1, y + header - 1), fill="#0d0d0d")
        draw.text((x + 14, y + 9), f"후보 {code}", font=label_font, fill="white")
        for frame_index, label in enumerate(("START", "MID", "END")):
            draw.text((x + frame_index * image_w + image_w - 70, y + 18),
                      label, font=small_font, fill="#aad8ff")
            board.paste(_fit(Path(record["frames"][frame_index]), (image_w, image_h)),
                        (x + frame_index * image_w, y + header))
    board_path = comparison / "blind-contact-sheet.jpg"
    board.save(board_path, quality=92)

    html = [
        "<!doctype html><meta charset='utf-8'><title>H3 blind review</title>",
        "<style>body{background:#161616;color:#eee;font:16px system-ui;margin:24px}"
        ".grid{display:grid;grid-template-columns:repeat(2,minmax(300px,1fr));gap:24px}"
        ".card{background:#242424;padding:14px;border-radius:12px}video{width:100%;max-height:72vh}"
        "h2{margin:0 0 10px}</style>",
        "<h1>H3 블라인드 비교</h1><p>후보를 끝까지 본 뒤 방향·불변성·동작량을 평가하세요.</p><div class='grid'>",
    ]
    for item in public_records:
        html.append(
            f"<section class='card'><h2>후보 {item['candidate']}</h2>"
            f"<video controls loop playsinline src='blind-clips/{item['candidate']}.mp4'></video></section>"
        )
    html.append("</div>")
    html_path = comparison / "blind-review.html"
    html_path.write_text("\n".join(html), encoding="utf-8")

    qa = {
        "schema_version": "h3-anchor-ablation-qa.v1", "created_at": _now(),
        "topic": receipt["topic"], "records": records,
        "all_format_ok": all(item["format_ok"] for item in records),
        "blind_review_audio_policy": "H3 native audio removed before review",
        "measurement_warning": (
            "whole-frame pixel deltas confirm anchor proximity and total change only; "
            "they cannot separate intended motion from background or identity drift"
        ),
    }
    qa_path = root / "qa" / "automatic-qa.json"
    qa_path.parent.mkdir(parents=True, exist_ok=True)
    qa_path.write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")
    key_path = comparison / "blind-key.json"
    key_path.write_text(json.dumps({
        "schema_version": "h3-anchor-ablation-blind-key.v1", "created_at": _now(),
        "do_not_show_before_human_review": True, "mapping": mapping,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    review_path = comparison / "human-review.json"
    review_path.write_text(json.dumps({
        "schema_version": "h3-anchor-ablation-human-review.v1", "created_at": _now(),
        "topic": receipt["topic"], "blind_review": str(html_path),
        "contact_sheet": str(board_path), "candidates": public_records,
        "evaluation_exclusions": ["H3 native audio", "speech language", "lip sync"],
        "evaluation_order": [
            "requested subject motion and direction are natural",
            "subject identity and rigid geometry remain stable",
            "background and camera obey the prompt",
            "motion amount is neither too small nor too large",
            "the ending is usable rather than forced or frozen",
        ],
        "questions": [
            "best overall candidate",
            "candidates with wrong direction or invariant drift",
            "whether the clip looks constrained by an awkward end frame",
        ],
        "human_response": None,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"qa": str(qa_path), "blind_review": str(html_path),
            "contact_sheet": str(board_path), "human_review": str(review_path),
            "blind_key": str(key_path), "candidates": len(public_records)}


def main() -> int:
    parser = argparse.ArgumentParser(description="build a blind H3 experiment review")
    parser.add_argument("attempt", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.attempt), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
