"""Compose stage-05 canary inputs for the M1–M4 stage-04 comparison.

Every bundle carries the selected stage-04 shot, the stage-01 direction and
relevant definitions, and the stage-02 sheet paths/hashes.  Historical sheet
gate failures are intentionally non-blocking only inside this experiment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .contract import Contract, load as load_contract
from .stage4_experiment import METHODS


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _strip_definition(spec: dict) -> dict:
    return {key: value for key, value in spec.items()
            if key not in {"provenance", "evidence", "evidence_context_legacy", "decisions"}}


def _sheet_for(attempt: Path, contract: Contract, subject_id: str) -> Path:
    return attempt / contract.stage_for("sheet", "02-sheet") / "output" / "sheets" / f"{subject_id}.png"


def _start_prompt(bundle: dict) -> str:
    shot = bundle["stage04_canary_shot"]
    return "\n\n".join([
        "Use case: illustration-story or photorealistic-natural according to the fixed stage-01 brief",
        "Asset type: controlled experimental stage-05 canary; one 9:16 cinematic production plate",
        "Primary request from stage 04:\n" + shot["plate_prompt"],
        "Fixed stage-01 direction (do not reinterpret):\n" +
        json.dumps(bundle["stage01_direction"], ensure_ascii=False, indent=2),
        "Fixed stage-01 relevant subject descriptions:\n" +
        json.dumps(bundle["stage01_relevant_definitions"], ensure_ascii=False, indent=2),
        "Full selected stage-04 shot contract:\n" + json.dumps(shot, ensure_ascii=False, indent=2),
        "Input images: the attached stage-02 sheets correspond in order to: " +
        ", ".join(item["subject_id"] for item in bundle["stage02_sheets"]),
        "Constraints: use the attached sheets only for the identity, wardrobe, object design, "
        "setting geometry, materials and style declared by their subject ids. Produce a single "
        "cinematic frame, never a board, grid, collage, split screen, diagram or labels. Preserve "
        "every invariant in the stage-04 shot. No readable text, logos, signatures or watermark.",
    ])


def _end_prompt(bundle: dict) -> str:
    shot = bundle["stage04_canary_shot"]
    if not shot.get("end_state"):
        return ""
    return "\n\n".join([
        "Use case: precise-object-edit",
        "Asset type: controlled experimental stage-05 canary end-state plate",
        "Primary request: edit the start plate into exactly this final observable state:\n" +
        shot["end_state"],
        "Input images: Image 1 is the stage-05 start plate edit target. Remaining images are "
        "the fixed stage-02 sheets in this order: " +
        ", ".join(item["subject_id"] for item in bundle["stage02_sheets"]),
        "Fixed stage-01 direction (do not reinterpret):\n" +
        json.dumps(bundle["stage01_direction"], ensure_ascii=False, indent=2),
        "Fixed stage-01 relevant subject descriptions:\n" +
        json.dumps(bundle["stage01_relevant_definitions"], ensure_ascii=False, indent=2),
        "Allowed change:\n" + json.dumps(shot.get("allowed_change", []), ensure_ascii=False),
        "Invariants that must remain pixel-consistent:\n" +
        json.dumps(shot.get("invariants", []), ensure_ascii=False),
        "Full selected stage-04 shot contract:\n" + json.dumps(shot, ensure_ascii=False, indent=2),
        "Constraints: change only the action state. Keep the same camera, crop, background "
        "geometry, lighting direction, subject identity, face, wardrobe, proportions and object "
        "design. Single cinematic frame. No text, grid, labels, logos or watermark.",
    ])


def compose(attempt: Path, force: bool = False) -> dict:
    contract = load_contract(attempt)
    premise = attempt / contract.stage_for("premise", "01-premise") / "output"
    direction = json.loads((premise / "direction.json").read_text(encoding="utf-8"))
    subject_dir = attempt / contract.get("subjects", {}).get(
        "directory", f'{contract.stage_for("premise", "01-premise")}/output/subjects')
    root = attempt / contract.stage_for("plate", "05-plate") / "qa" / "experiments" / "stage4-methods"
    records = []
    for method_id in METHODS:
        method_path = (attempt / contract.stage_for("shot_design", "04-shot-design") / "qa" /
                       "experiments" / "methods" / method_id / "shot-design.json")
        design = json.loads(method_path.read_text(encoding="utf-8"))
        canary_id = design["canary"]["shot_id"]
        shot = next(item for item in design["shots"] if item["shot_id"] == canary_id)
        subject_ids = list(dict.fromkeys(
            [sid for sid in shot.get("subject_ids", []) if sid]
            + ([shot.get("where_subject_id")] if shot.get("where_subject_id") else [])))
        definitions = {}
        sheets = []
        for sid in subject_ids:
            definition = subject_dir / f"{sid}.json"
            sheet = _sheet_for(attempt, contract, sid)
            if definition.exists():
                definitions[sid] = _strip_definition(json.loads(definition.read_text(encoding="utf-8")))
            if sheet.exists():
                sheets.append({"subject_id": sid, "path": str(sheet), "sha256": _file_sha(sheet),
                               "historical_whole_board": True})
        bundle = {
            "schema_version": "stage5-method-canary-input.v1",
            "created_at": _now(), "method_id": method_id,
            "comparison_blind_id": None,
            "experiment_only": True, "not_production_approved": True,
            "legacy_gate_failures_non_blocking": True,
            "stage01_direction": direction,
            "stage01_relevant_definitions": definitions,
            "stage02_sheets": sheets,
            "stage04_output": str(method_path), "stage04_sha256": _file_sha(method_path),
            "stage04_canary_shot": shot,
        }
        folder = root / method_id
        folder.mkdir(parents=True, exist_ok=True)
        bundle["start_prompt"] = _start_prompt(bundle)
        bundle["end_prompt"] = _end_prompt(bundle)
        target = folder / "input-bundle.json"
        if force or not target.exists():
            target.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
            (folder / "start-prompt.txt").write_text(bundle["start_prompt"], encoding="utf-8")
            (folder / "end-prompt.txt").write_text(bundle["end_prompt"], encoding="utf-8")
        records.append({"method_id": method_id, "bundle": str(target),
                        "sheets": len(sheets), "has_end": bool(bundle["end_prompt"])})
    manifest = {"schema_version": "stage5-method-canary-manifest.v1", "attempt": str(attempt),
                "created_at": _now(), "records": records}
    target = root / "manifest.json"
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="compose stage05 canary bundles for stage04 methods")
    parser.add_argument("attempt", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    print(json.dumps(compose(args.attempt, args.force), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
