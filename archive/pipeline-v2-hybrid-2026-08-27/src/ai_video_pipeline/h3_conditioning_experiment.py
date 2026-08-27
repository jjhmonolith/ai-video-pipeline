"""Run the stage-04 canaries as an H3 anchor ablation.

The experiment changes one runtime input at a time for each method:

* ``paired``: reference sheets + first plate + last plate + identical prompt
* ``first_only``: reference sheets + first plate + identical prompt

The same seed, duration, reference order and prompt are used inside each pair.
M1 intentionally has no last plate, so it participates only as a first-only
baseline.  All artifacts remain below ``06-motion/qa/experiments`` and cannot
be mistaken for production clips.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contract import load as load_contract
from .h3_runtime import ComfyClient, H3Request, H3Settings, generate
from .stage4_comparison import BLIND
from .stage4_experiment import METHODS

SCHEMA = "h3-anchor-ablation.v1"
EXPERIMENT_ID = "h3-first-last-vs-first-only-v1"
METHOD_ORDER = list(METHODS)


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _copy_input(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists() or _sha_file(source) != _sha_file(destination):
        shutil.copy2(source, destination)
    return destination


def _topic_addendum(topic: str) -> str:
    if topic == "sky-village-plumber":
        return """CONTROLLED SUBJECT MOTION — Keep the camera completely locked. The husky plumber stays at the same working position. First, rotate the large valve wheel around its existing hub without translating or resizing the wheel. The wheel center, outer diameter, rim thickness, hub size and spoke count remain exactly fixed. Next, remove only the red-handled pipe wrench from its existing slot. Every other visible tool in the bag keeps the same identity, count, color, order and position. Finally, bring the wrench to the same pipe connection and loosen that one connection slowly. Do not move, replace, duplicate or redesign the bag, tools, valve, pipes or background. Do not invent water bursts or a new action. Only the hands, the selected wrench, the wheel's angular pose, the contacted connector and their contact shadows may change."""
    if topic == "luxury-penthouse-tour":
        return """CONTROLLED SUBJECT MOTION — Keep the camera completely locked with no pan, tilt, dolly, zoom or reframing. The host begins at the elevator threshold. Before stepping, she turns her hips, feet and torso toward the penthouse interior. She then walks naturally forward in the direction her body faces, away from the camera and deeper into the living room along the floor axis. She must never backpedal, moonwalk or step backward while facing the camera. Her screen scale may decrease only slightly and continuously as she moves away. After arriving, she stops walking and makes one restrained presenting gesture along the long sightline. Preserve her identity, face, hair, suit, body proportions, architecture, furniture, lighting and all background geometry. Do not add another person or action."""
    raise ValueError(f"unknown topic {topic}")


def _reference_binding(sheets: list[dict]) -> str:
    lines = [
        "REFERENCE BINDING — The reference sheets define identity and design only. "
        "The first frame defines the actual shot composition. Never reproduce a sheet grid, board or labels."
    ]
    for index, item in enumerate(sheets, start=1):
        lines.append(f"<Picture {index}> is the canonical reference sheet for {item['subject_id']}.")
    return "\n".join(lines)


def _resolve_asset(path_text: str, project_root: Path) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else project_root / path


def prepare(attempt: Path, seconds: float = 5.0, force: bool = False) -> dict:
    attempt = attempt.resolve()
    project_root = Path(__file__).resolve().parents[2]
    contract = load_contract(attempt)
    topic = attempt.parents[1].name
    plate_root = (attempt / contract.stage_for("plate", "05-plate") / "qa" /
                  "experiments" / "stage4-methods")
    method_root = (attempt / contract.stage_for("shot_design", "04-shot-design") / "qa" /
                   "experiments" / "methods")
    root = (attempt / contract.stage_for("motion", "06-motion") / "qa" /
            "experiments" / EXPERIMENT_ID)
    input_root = root / "inputs"
    root.mkdir(parents=True, exist_ok=True)

    topic_seed = 862601 if topic == "sky-village-plumber" else 862602
    records: list[dict[str, Any]] = []
    exclusions = []
    for method_id in METHOD_ORDER:
        bundle_path = plate_root / method_id / "input-bundle.json"
        design_path = method_root / method_id / "shot-design.json"
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        design = json.loads(design_path.read_text(encoding="utf-8"))
        shot = next(item for item in design["shots"]
                    if item["shot_id"] == design["canary"]["shot_id"])

        staged_start = _copy_input(
            plate_root / method_id / "start.png",
            input_root / f"{method_id}-start.png",
        )
        end_source = plate_root / method_id / "end.png"
        staged_end = (_copy_input(end_source, input_root / f"{method_id}-end.png")
                      if end_source.exists() else None)
        staged_sheets = []
        for sheet in bundle["stage02_sheets"]:
            source = _resolve_asset(sheet["path"], project_root)
            target = input_root / f"sheet-{sheet['subject_id']}{source.suffix.lower()}"
            staged = _copy_input(source, target)
            staged_sheets.append({"subject_id": sheet["subject_id"], "path": str(staged),
                                  "sha256": _sha_file(staged)})

        prompt = "\n\n".join([
            _reference_binding(staged_sheets),
            str(shot["h3_motion_prompt"]),
            _topic_addendum(topic),
            "OUTPUT — one continuous natural shot with no cut, transition, split screen, text or watermark.",
        ])
        conditions = ["first_only"] + (["paired"] if staged_end else [])
        if not staged_end:
            exclusions.append({"method_id": method_id, "condition": "paired",
                               "reason": "method intentionally defines no end plate"})
        for condition in conditions:
            record_id = f"{method_id}--{condition}"
            records.append({
                "record_id": record_id,
                "method_id": method_id,
                "stage4_blind_id": next(key for key, value in BLIND.items() if value == method_id),
                "condition": condition,
                "topic": topic,
                "seconds": seconds,
                "seed": topic_seed,
                "width": contract.frame.width,
                "height": contract.frame.height,
                "reference_size": "match",
                "first_frame": {"path": str(staged_start), "sha256": _sha_file(staged_start)},
                "last_frame": ({"path": str(staged_end), "sha256": _sha_file(staged_end)}
                               if condition == "paired" and staged_end else None),
                "reference_sheets": staged_sheets,
                "prompt": prompt,
                "prompt_sha256": _sha_text(prompt),
                "output_dir": str(root / "clips" / record_id),
                "not_production_approved": True,
                "status": "prepared",
            })

    manifest = {
        "schema_version": SCHEMA,
        "experiment_id": EXPERIMENT_ID,
        "created_at": _now(),
        "attempt": str(attempt),
        "topic": topic,
        "hypothesis": (
            "reference sheets + first frame + explicit motion route may outperform the same inputs "
            "with a visually inconsistent last frame"
        ),
        "controlled_variables": [
            "same H3 runtime and settings", "same prompt within each method pair",
            "same reference sheets and order", "same first frame", "same seed", "same duration",
        ],
        "independent_variable": "last frame present versus absent",
        "legacy_stage01_03_failures_non_blocking_for_experiment": True,
        "exclusions": exclusions,
        "records": records,
    }
    target = root / "manifest.json"
    if force or not target.exists():
        target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def _run_record(record: dict, server: str) -> dict:
    client = ComfyClient(server)
    uploaded_refs = tuple(client.upload_image(item["path"])
                          for item in record["reference_sheets"])
    first = client.upload_image(record["first_frame"]["path"])
    last = (client.upload_image(record["last_frame"]["path"])
            if record.get("last_frame") else None)
    request = H3Request(
        prompt=record["prompt"], width=int(record["width"]), height=int(record["height"]),
        seconds=float(record["seconds"]), seed=int(record["seed"]),
        first_frame=first, last_frame=last, references=uploaded_refs,
        reference_size=record["reference_size"],
        filename_prefix=f"video/{EXPERIMENT_ID}/{record['topic']}/{record['record_id']}",
    )
    result = generate(request, Path(record["output_dir"]), H3Settings(), server, 3600.0)
    return {**record, "server": server, "status": "completed", "completed_at": _now(),
            "generation": result}


def run(attempt: Path, servers: list[str], force: bool = False) -> dict:
    manifest = prepare(attempt, force=force)
    root = Path(manifest["records"][0]["output_dir"]).parents[1]
    pending = []
    completed = []
    for record in manifest["records"]:
        output_dir = Path(record["output_dir"])
        existing = sorted(output_dir.glob("*.mp4"))
        if existing and not force:
            completed.append({**record, "status": "completed_existing",
                              "generation": {"files": [str(path) for path in existing]}})
        else:
            pending.append(record)

    # One sequential queue per GPU-backed server.  This avoids simultaneous
    # model jobs on the same ComfyUI instance while still using both GPUs.
    queues = [[] for _ in servers]
    for index, record in enumerate(pending):
        queues[index % len(servers)].append(record)

    def worker(server: str, queue: list[dict]) -> list[dict]:
        results = []
        for record in queue:
            print(f"START {record['topic']} {record['record_id']} {server}", flush=True)
            result = _run_record(record, server)
            print(f"DONE {record['topic']} {record['record_id']} "
                  f"{result['generation']['elapsed_seconds']}s", flush=True)
            results.append(result)
        return results

    with ThreadPoolExecutor(max_workers=len(servers)) as pool:
        futures = [pool.submit(worker, server, queue)
                   for server, queue in zip(servers, queues) if queue]
        for future in as_completed(futures):
            completed.extend(future.result())
    completed.sort(key=lambda item: item["record_id"])
    manifest["completed_at"] = _now()
    manifest["servers"] = servers
    manifest["records"] = completed
    manifest["all_completed"] = len(completed) == len(queues[0]) + len(queues[1]) if len(queues) == 2 else not pending
    manifest["all_completed"] = all(item["status"].startswith("completed") for item in completed)
    target = root / "receipt.json"
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="H3 first+last versus first-only comparison")
    parser.add_argument("attempt", type=Path)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--server", action="append", default=[])
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.prepare_only:
        result = prepare(args.attempt, args.seconds, args.force)
    else:
        result = run(args.attempt, args.server or ["http://127.0.0.1:18188"], args.force)
    print(json.dumps({
        "experiment_id": result["experiment_id"], "topic": result["topic"],
        "records": len(result["records"]), "all_completed": result.get("all_completed", False),
    }, ensure_ascii=False, indent=2))
    return 0 if args.prepare_only or result.get("all_completed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
