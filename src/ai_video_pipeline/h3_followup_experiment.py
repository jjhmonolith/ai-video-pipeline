"""Run the H3 camera/anchor and affordance/anchor follow-up experiment.

The experiment is deliberately split into a one-seed canary phase (14 clips)
and a two-seed main phase (28 clips).  It uses H3 only.  Reference packs,
anchors, prompts and seeds are persisted before submission so a blind review
can later prove which variable changed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import queue
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contract import load as load_contract
from .h3_runtime import ComfyClient, H3Request, H3Settings, generate

EXPERIMENT_ID = "stage4-camera-anchor-affordance-v2"
SCHEMA = "h3-camera-anchor-affordance.v1"
SEEDS = {
    "L1": [862711, 862712, 862713],
    "M1": [862721, 862722, 862723],
}
CAMERA_POLICIES = ("natural", "soft_follow", "locked")
ANCHOR_POLICIES = ("first_only", "paired")
REFERENCE_PACKS = ("identity_only", "identity_plus_affordance")
TASKS = ("seat_wrench", "turn_coupling")


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _asset(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(path)
    return {"path": str(path.resolve()), "sha256": _sha_file(path)}


def _reference(path: Path, subject_id: str, role: str, bindings: list[str]) -> dict:
    return {**_asset(path), "subject_id": subject_id, "role": role,
            "bindings": bindings}


def _l1_prompt(camera_policy: str) -> str:
    camera = {
        "locked": (
            "CAMERA — completely locked at the elevator threshold. No pan, tilt, dolly, "
            "zoom, stabilization drift or reframing."
        ),
        "natural": (
            "CAMERA — allow only one small, naturally motivated continuous camera response "
            "to the walking subject: a modest forward drift or slight re-centering is allowed, "
            "but no orbit, cut, abrupt reframe or overtake."
        ),
        "soft_follow": (
            "CAMERA — one smooth soft follow from behind. Move forward along the same floor "
            "axis at the host's walking pace, gently re-center her, never overtake or orbit, "
            "and finish without a correction or bounce."
        ),
    }[camera_policy]
    return "\n\n".join([
        "REFERENCE BINDING — Picture 1 defines the host identity and cream wardrobe only. "
        "Picture 2 defines the penthouse world-space architecture and lighting only. The first "
        "frame defines the actual starting composition. Never reproduce a board, studio backdrop "
        "or reference pose.",
        camera,
        (
            "ACTION TIMELINE — 0-18%: the host smoothly lowers her raised presenting arm until "
            "both arms rest naturally. 18-42%: she turns feet first, then hips and torso fully "
            "toward the living room. 42-92%: she walks exactly three natural forward steps in the "
            "direction her body faces, away from camera and deeper into the room. 92-100%: she "
            "continues facing the room with both arms down. She never backpedals, moonwalks, looks "
            "back, turns to camera, raises an arm again or makes a new presenting gesture."
        ),
        (
            "INVARIANTS — same woman, face, long dark wavy hair, cream suit, body proportions, "
            "architecture, furniture identity, window geometry, city, lighting direction and "
            "exposure. Projection changes are allowed only when caused by the declared camera "
            "motion. No people, film crew, cameras, lamps, new objects, flicker or exposure pump."
        ),
        (
            "AUDIO/PERFORMANCE — no dialogue. Keep her mouth naturally closed; do not lip-sync. "
            "The generated soundtrack will be discarded."
        ),
        "OUTPUT — one continuous five-second shot, no cut, transition, split screen, text or watermark.",
    ])


def _m1_prompt(task: str, with_affordance: bool) -> str:
    refs = (
        "REFERENCE BINDING — Picture 1 defines the exact single red pipe wrench identity. "
        "Picture 2 demonstrates the physically correct wrench-jaw contact on the knurled coupling; "
        "use it only as a contact/axis reference, never as another object or frame. The first frame "
        "defines the actual composition."
        if with_affordance else
        "REFERENCE BINDING — Picture 1 defines the exact single red pipe wrench identity only. "
        "The first frame defines the actual composition and interaction geometry."
    )
    action = {
        "seat_wrench": (
            "ACTION TIMELINE — 0-15%: hold the prepared pose. 15-75%: move both gloved hands and "
            "the one red wrench together along one short direct approach toward the black knurled "
            "coupling. 75-90%: the upper and lower silver jaws close onto opposite sides of that "
            "coupling with visible metal-to-metal contact. 90-100%: stop and hold the fully seated "
            "wrench. Do not rotate the coupling or pull the handle."
        ),
        "turn_coupling": (
            "ACTION TIMELINE — the wrench starts already fully seated. 0-15%: hold contact. 15-80%: "
            "both hands pull the red handle through one small smooth downward arc of about fifteen "
            "degrees while the jaws remain closed on the coupling. Only the dark knurled coupling "
            "rotates by the same small amount around the horizontal pipe axis; the brass index mark "
            "moves with it. 80-100%: stop and hold. Do not release, re-grip or perform a second turn."
        ),
    }[task]
    return "\n\n".join([
        refs,
        "CAMERA — completely locked close side view. No pan, tilt, dolly, zoom, shake or reframing.",
        action,
        (
            "MECHANICAL INVARIANTS — exactly one wrench and two gloved hands. Preserve wrench jaw, "
            "adjustment nut, red body and handle geometry. The coupling stays connected. Both adjacent "
            "silver pipe sections, background pipes, brickwork, lighting and camera remain fixed. "
            "No hand-tool or tool-pipe interpenetration. No pipe bending, detachment, cap, plug, leak, "
            "water discharge, disappearing object, invented object or extra limb."
        ),
        (
            "AUDIO/PERFORMANCE — no dialogue and no reaction beat. The generated soundtrack will be "
            "discarded."
        ),
        "OUTPUT — one continuous five-second shot, no cut, transition, split screen, text or watermark.",
    ])


def _attempt(project_root: Path, topic: str) -> Path:
    return (project_root / "runs" / topic / "attempts" / "v1-pilot").resolve()


def _root(attempt: Path, contract: Any) -> Path:
    return (attempt / contract.stage_for("motion", "06-motion") / "qa" /
            "experiments" / EXPERIMENT_ID)


def _l1_manifest(project_root: Path) -> dict:
    topic = "luxury-penthouse-tour"
    attempt = _attempt(project_root, topic)
    contract = load_contract(attempt)
    root = _root(attempt, contract)
    inputs = root / "inputs"
    start = _asset(inputs / "locomotion-start.png")
    identity = _reference(inputs / "host-identity-reference.png", "host-seoa",
                          "identity_reference", ["host-seoa"])
    geometry = _reference(inputs / "penthouse-geometry-reference.png", "skyline-penthouse",
                          "environment_geometry_reference", ["threshold-to-living-axis"])
    records = []
    for camera_policy in CAMERA_POLICIES:
        end = _asset(inputs / f"locomotion-end-{camera_policy.replace('_', '-')}.png")
        prompt = _l1_prompt(camera_policy)
        for anchor_policy in ANCHOR_POLICIES:
            for seed_index, seed in enumerate(SEEDS["L1"], 1):
                record_id = f"L1--{camera_policy}--{anchor_policy}--s{seed_index}"
                records.append({
                    "record_id": record_id, "study_id": "L1-locomotion-camera-anchor",
                    "topic": topic, "phase": "pilot" if seed_index == 1 else "main",
                    "factors": {"camera_policy": camera_policy,
                                "anchor_policy": anchor_policy, "seed_index": seed_index},
                    "seconds": 5.0, "seed": seed, "width": contract.frame.width,
                    "height": contract.frame.height, "reference_size": "match",
                    "first_frame": start,
                    "last_frame": end if anchor_policy == "paired" else None,
                    "references": [identity, geometry],
                    "prompt": prompt, "prompt_sha256": _sha_text(prompt),
                    "output_dir": str(root / "clips" / record_id),
                    "h3_native_audio": "discard", "not_production_approved": True,
                    "status": "prepared",
                })
    return {
        "schema_version": SCHEMA, "experiment_id": EXPERIMENT_ID,
        "study_id": "L1-locomotion-camera-anchor", "created_at": _now(),
        "attempt": str(attempt), "topic": topic, "video_engine": "minimax-h3-local-768p",
        "legacy_stage01_03_failures_non_blocking_for_experiment": True,
        "controlled_variables": [
            "same first frame", "same two selective references", "same action prompt within camera policy",
            "same seed within anchor pair", "same H3 runtime/settings", "same five-second duration",
        ],
        "independent_variables": ["camera_policy", "anchor_policy"], "records": records,
    }


def _m1_manifest(project_root: Path) -> dict:
    topic = "sky-village-plumber"
    attempt = _attempt(project_root, topic)
    contract = load_contract(attempt)
    root = _root(attempt, contract)
    inputs = root / "inputs"
    identity = _reference(inputs / "wrench-identity-reference.png", "pipe-wrench",
                          "identity_reference", ["pipe-wrench"])
    affordance = _reference(
        inputs / "wrench-coupling-affordance-reference.png", "coupling-01",
        "motion_affordance_reference",
        ["pipe-wrench.jaws", "pipe-wrench.handle", "coupling-01", "fixed-pipe-left", "fixed-pipe-right"],
    )
    records = []
    for task in TASKS:
        start = _asset(inputs / f"{task.replace('_', '-')}-start.png")
        end = _asset(inputs / f"{task.replace('_', '-')}-end.png")
        for reference_pack in REFERENCE_PACKS:
            references = [identity] + ([affordance]
                                       if reference_pack == "identity_plus_affordance" else [])
            prompt = _m1_prompt(task, reference_pack == "identity_plus_affordance")
            for anchor_policy in ANCHOR_POLICIES:
                for seed_index, seed in enumerate(SEEDS["M1"], 1):
                    record_id = (f"M1--{task}--{reference_pack}--"
                                 f"{anchor_policy}--s{seed_index}")
                    records.append({
                        "record_id": record_id, "study_id": "M1-mechanical-affordance-anchor",
                        "topic": topic, "phase": "pilot" if seed_index == 1 else "main",
                        "factors": {"task": task, "reference_pack": reference_pack,
                                    "anchor_policy": anchor_policy, "seed_index": seed_index},
                        "seconds": 5.0, "seed": seed, "width": contract.frame.width,
                        "height": contract.frame.height, "reference_size": "match",
                        "first_frame": start,
                        "last_frame": end if anchor_policy == "paired" else None,
                        "references": references,
                        "prompt": prompt, "prompt_sha256": _sha_text(prompt),
                        "output_dir": str(root / "clips" / record_id),
                        "h3_native_audio": "discard", "not_production_approved": True,
                        "status": "prepared",
                    })
    return {
        "schema_version": SCHEMA, "experiment_id": EXPERIMENT_ID,
        "study_id": "M1-mechanical-affordance-anchor", "created_at": _now(),
        "attempt": str(attempt), "topic": topic, "video_engine": "minimax-h3-local-768p",
        "legacy_stage01_03_failures_non_blocking_for_experiment": True,
        "controlled_variables": [
            "same task-specific first frame", "same wrench identity reference",
            "same action prompt within reference pack", "same seed within anchor pair",
            "same H3 runtime/settings", "same locked camera", "same five-second duration",
        ],
        "independent_variables": ["reference_pack", "anchor_policy", "task"],
        "records": records,
    }


def prepare(project_root: Path, force: bool = False) -> list[dict]:
    manifests = [_l1_manifest(project_root.resolve()), _m1_manifest(project_root.resolve())]
    for manifest in manifests:
        root = Path(manifest["records"][0]["output_dir"]).parents[1]
        root.mkdir(parents=True, exist_ok=True)
        target = root / "manifest.json"
        if target.exists() and not force:
            existing = json.loads(target.read_text(encoding="utf-8"))
            old = [(r["record_id"], r["prompt_sha256"], r["first_frame"]["sha256"],
                    (r.get("last_frame") or {}).get("sha256")) for r in existing["records"]]
            new = [(r["record_id"], r["prompt_sha256"], r["first_frame"]["sha256"],
                    (r.get("last_frame") or {}).get("sha256")) for r in manifest["records"]]
            if old != new:
                raise RuntimeError(f"prepared manifest changed; use --force-prepare after review: {target}")
            manifest = existing
        else:
            target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifests


def _run_record(record: dict, server: str) -> dict:
    client = ComfyClient(server)
    references = tuple(client.upload_image(item["path"]) for item in record["references"])
    first = client.upload_image(record["first_frame"]["path"])
    last = client.upload_image(record["last_frame"]["path"]) if record.get("last_frame") else None
    request = H3Request(
        prompt=record["prompt"], width=int(record["width"]), height=int(record["height"]),
        seconds=float(record["seconds"]), seed=int(record["seed"]), first_frame=first,
        last_frame=last, references=references, reference_size=record["reference_size"],
        filename_prefix=f"video/{EXPERIMENT_ID}/{record['topic']}/{record['record_id']}",
    )
    result = generate(request, Path(record["output_dir"]), H3Settings(), server, 3600.0)
    return {**record, "server": server, "status": "completed", "completed_at": _now(),
            "generation": result}


def run(project_root: Path, phase: str, servers: list[str], force_prepare: bool = False) -> dict:
    if not servers:
        raise ValueError("at least one H3 server is required")
    manifests = prepare(project_root, force_prepare)
    selected = [record for manifest in manifests for record in manifest["records"]
                if phase == "all" or record["phase"] == phase]
    results: dict[str, dict] = {}
    pending = []
    for record in selected:
        existing = sorted(Path(record["output_dir"]).glob("*.mp4"))
        if existing:
            results[record["record_id"]] = {
                **record, "status": "completed_existing",
                "generation": {"files": [str(existing[0])]},
            }
        else:
            pending.append(record)

    write_lock = threading.Lock()

    def write_progress() -> None:
        by_topic: dict[str, list[dict]] = {}
        for item in results.values():
            by_topic.setdefault(item["topic"], []).append(item)
        for manifest in manifests:
            topic_records = sorted(by_topic.get(manifest["topic"], []),
                                   key=lambda item: item["record_id"])
            root = Path(manifest["records"][0]["output_dir"]).parents[1]
            payload = {**{k: v for k, v in manifest.items() if k != "records"},
                       "phase": phase, "updated_at": _now(), "servers": servers,
                       "selected_record_count": sum(
                           1 for r in manifest["records"]
                           if phase == "all" or r["phase"] == phase),
                       "records": topic_records,
                       "all_completed": bool(topic_records) and all(
                           r["status"].startswith("completed") for r in topic_records),
                       "failed": [r["record_id"] for r in topic_records
                                  if r["status"] == "failed"]}
            (root / f"receipt-{phase}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    pending_queue: queue.Queue[dict] = queue.Queue()
    for record in pending:
        pending_queue.put(record)

    def worker(server: str) -> list[dict]:
        done = []
        while True:
            try:
                record = pending_queue.get_nowait()
            except queue.Empty:
                break
            print(f"START {record['record_id']} {server}", flush=True)
            try:
                result = _run_record(record, server)
                elapsed = result["generation"].get("elapsed_seconds")
                print(f"DONE {record['record_id']} {elapsed}s", flush=True)
            except Exception as error:  # noqa: BLE001 - persist failed GPU work for restart
                result = {**record, "server": server, "status": "failed",
                          "failed_at": _now(), "error": repr(error)}
                print(f"FAILED {record['record_id']} {error!r}", flush=True)
            with write_lock:
                results[record["record_id"]] = result
                write_progress()
            done.append(result)
            pending_queue.task_done()
        return done

    with write_lock:
        write_progress()
    with ThreadPoolExecutor(max_workers=len(servers)) as pool:
        futures = [pool.submit(worker, server) for server in servers if pending]
        for future in as_completed(futures):
            future.result()
    with write_lock:
        write_progress()
    ordered = [results[r["record_id"]] for r in selected if r["record_id"] in results]
    return {
        "experiment_id": EXPERIMENT_ID, "phase": phase, "selected": len(selected),
        "completed": sum(r["status"].startswith("completed") for r in ordered),
        "failed": [r["record_id"] for r in ordered if r["status"] == "failed"],
        "all_completed": len(ordered) == len(selected) and all(
            r["status"].startswith("completed") for r in ordered),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="run the H3 stage-04 follow-up experiment")
    parser.add_argument("project_root", type=Path)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--force-prepare", action="store_true")
    parser.add_argument("--phase", choices=["pilot", "main", "all"], default="pilot")
    parser.add_argument("--server", action="append", default=[])
    args = parser.parse_args()
    if args.prepare_only:
        manifests = prepare(args.project_root, args.force_prepare)
        result = {"experiment_id": EXPERIMENT_ID,
                  "records": sum(len(item["records"]) for item in manifests),
                  "pilot": sum(r["phase"] == "pilot" for m in manifests for r in m["records"]),
                  "main": sum(r["phase"] == "main" for m in manifests for r in m["records"])}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    result = run(args.project_root, args.phase,
                 args.server or ["http://127.0.0.1:18188"], args.force_prepare)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["all_completed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
