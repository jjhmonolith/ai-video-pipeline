from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from PIL import Image

from ai_video_pipeline.contract import Contract
from ai_video_pipeline.execution_mode import set_execution_mode
from ai_video_pipeline.stage5 import (
    PLATE_AI_ATTEMPT_REVIEW_SCHEMA,
    PLATE_MAX_ATTEMPTS,
    PLATE_REFERENCE_COMPARISON_CRITERIA,
    PLATE_REFERENCE_REVIEW_SCHEMA,
    Stage5Error,
    UNIVERSAL_RENDER_CONTRACT_VERSION,
    apply_review,
    audit_inputs,
    finalize_codex_jobs,
    prepare_codex_jobs,
    record_ai_plate_review,
    record_ai_reference_review,
)


CONTRACT = {
    "contract_id": "STAGE5-TEST",
    "attempt": "v2",
    "stages": {
        "premise": "01-premise", "sheet": "02-sheet", "scenario": "03-scenario",
        "shot_design": "04-shot-design", "plate": "05-plate", "motion": "06-motion",
        "edit": "07-edit", "review": "08-review",
    },
    "frame": {"width": 768, "height": 1344, "fps": 24,
              "applies_to": ["05-plate", "06-motion"], "upscale": {"allowed": False}},
    "delivery_frame": {"width": 768, "height": 1344, "fps": 24,
                       "applies_to": ["07-edit"],
                       "transform": {"allowed": False, "operation": "none"}},
    "motion": {"runtime": "minimax-h3-local-768p", "frame_source": "frame"},
    "audio": {"h3_native_audio": "discard", "target_language": "ko",
              "dialogue_source": "approved_script_only",
              "lip_sync": "only_when_onscreen_speaker_is_explicit"},
    "image": {
        "model": "gpt-image-2", "quality": "high",
        "api_sizes": ["1024x1536", "1536x1024"],
        "roles": {
            "plate": {"deliver_at": "frame", "quality": "high"},
            "sheet": {"deliver_at": "max", "orientation": "landscape", "quality": "high"},
        },
    },
    "subjects": {"directory": "01-premise/output/subjects",
                 "declared": {"hero": {"kind": "character"},
                              "room": {"kind": "setting"}}},
    "clauses": [],
}


def file_sha(path: Path, short: bool = False) -> str:
    value = hashlib.sha256(path.read_bytes()).hexdigest()
    return value[:16] if short else value


class Stage5Fixture(unittest.TestCase):
    def setUp(self):
        self.attempt = Path(tempfile.mkdtemp())
        contract_path = self.attempt / "01-premise/output/contract.json"
        contract_path.parent.mkdir(parents=True)
        contract_path.write_text(json.dumps(CONTRACT), encoding="utf-8")
        contract = Contract.load(self.attempt)

        qa = self.attempt / "01-premise/qa"
        qa.mkdir(parents=True)
        (qa / "report.json").write_text(json.dumps({
            "form_ok": True, "human_approved": True, "release_eligible": True,
            "production_state": "release_eligible",
        }), encoding="utf-8")
        (qa / "direction-impact.json").write_text(json.dumps({
            "unresolved_count": 0, "downstream_allowed": True,
        }), encoding="utf-8")

        sheets = self.attempt / "02-sheet/output/sheets"
        sheets.mkdir(parents=True)
        self.hero = sheets / "hero.png"
        self.room = sheets / "room.png"
        Image.new("RGB", (1536, 1024), "blue").save(self.hero)
        Image.new("RGB", (1536, 1024), "beige").save(self.room)
        sheet_qa = self.attempt / "02-sheet/qa"
        sheet_qa.mkdir(parents=True)
        (sheet_qa / "semantic-review.json").write_text(json.dumps({
            "reference_ready": True, "status": "approved",
        }), encoding="utf-8")

        self.manual = None
        self.design = self.make_design(contract)
        design_path = self.attempt / "04-shot-design/output/shot-cards.json"
        design_path.parent.mkdir(parents=True)
        design_path.write_text(json.dumps(self.design), encoding="utf-8")
        stage4_qa = self.attempt / "04-shot-design/qa"
        stage4_qa.mkdir(parents=True)
        (stage4_qa / "semantic-check.json").write_text(json.dumps({
            "form_ok": True, "production_ready": True, "warnings": [], "problems": [],
        }), encoding="utf-8")

    def make_design(self, contract: Contract, manual: dict | None = None) -> dict:
        plan = {"policy_version": "interaction-manual.v1", "required": bool(manual),
                "manuals": [manual] if manual else []}
        return {
            "schema_version": "shot-design.v1",
            "contract": contract.receipt_block("04-shot-design"),
            "reference_status": {"canonical_boards": {
                "hero": {"path": str(self.hero), "sha256": file_sha(self.hero, True)},
                "room": {"path": str(self.room), "sha256": file_sha(self.room, True)},
            }},
            "states": {"S01-START": {
                "state_id": "S01-START", "prompt": "One clean cinematic start frame.",
            }},
            "shots": [{
                "shot_id": "S01", "state_pair": {"start_state_id": "S01-START"},
                "reference_requirements": {
                    "canonical_stage02_sheet_subject_ids": ["hero", "room"]},
                "supplemental_reference_plan": plan,
                "plate_candidate_policy": {
                    "strategy": "sequential_ai_review", "start_candidates": 1,
                    "max_attempts": 10, "stop_on_ai_pass": True,
                    "exhaustion_policy": "use_attempt_10_for_human_review",
                },
                "plate_acceptance": {"start": ["action has not begun", "identity is stable"]},
                "motion_control": {"screen_direction_contract": {"required": False}},
                "motion_prompt": "A slow forward walk.",
            }],
        }

    def candidate_images(self, manifest: dict,
                         plate_size: tuple[int, int] | None = None) -> None:
        if manifest.get("phase") == "plates":
            manifest_path = (self.attempt / "05-plate/qa/codex/manifests" /
                             f'{manifest["manifest_id"]}.json')
            self.record_reference_preflight(manifest_path, manifest)
        for job in manifest["jobs"]:
            if job.get("asset_type") == "plate":
                path = self.attempt / str(job["retry_harness"]["attempt_path_pattern"]).format(
                    attempt=1)
            else:
                path = self.attempt / job["candidate_path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            requested = (list(plate_size)
                         if job.get("asset_type") == "plate" and plate_size
                         else job["requested"])
            Image.new("RGB", tuple(requested), "green").save(path)
            if job.get("asset_type") == "plate":
                review_path = path.with_suffix(".review.json")
                review_path.write_text(json.dumps({
                    "schema_version": PLATE_AI_ATTEMPT_REVIEW_SCHEMA,
                    "job_id": job["job_id"],
                    "decision": "pass",
                    "criteria": [
                        {"criterion": criterion, "status": "pass", "evidence": ["fixture"]}
                        for criterion in job["retry_harness"]["acceptance_criteria"]
                    ],
                    "feedback": "",
                    "reviewer": "fixture-ai-reviewer",
                    "reviewed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                }), encoding="utf-8")
                record_ai_plate_review(self.attempt, manifest_path, review_path)

    def load_manifest(self, result: dict) -> tuple[Path, dict]:
        path = Path(result["manifest"])
        return path, json.loads(path.read_text(encoding="utf-8"))

    def record_plate_attempt(self, manifest_path: Path, manifest: dict, decision: str,
                             feedback: str = "correct the failed criterion") -> dict:
        self.record_reference_preflight(manifest_path, manifest)
        job = manifest["jobs"][0]
        log_path = self.attempt / job["retry_harness"]["ai_review_log_path"]
        number = 1
        if log_path.exists():
            number += len(json.loads(log_path.read_text(encoding="utf-8"))["attempts"])
        candidate = self.attempt / str(
            job["retry_harness"]["attempt_path_pattern"]).format(attempt=number)
        candidate.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", tuple(job["requested"]), "green").save(candidate)
        criteria = []
        for index, criterion in enumerate(job["retry_harness"]["acceptance_criteria"]):
            status = "pass" if decision == "pass" or index else "fail"
            criteria.append({"criterion": criterion, "status": status,
                             "evidence": [f"attempt {number}: {status}"]})
        review_path = candidate.with_suffix(".review.json")
        review_path.write_text(json.dumps({
            "schema_version": PLATE_AI_ATTEMPT_REVIEW_SCHEMA,
            "job_id": job["job_id"], "decision": decision, "criteria": criteria,
            "feedback": "" if decision == "pass" else feedback,
            "reviewer": "fixture-ai-reviewer",
            "reviewed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }), encoding="utf-8")
        return record_ai_plate_review(self.attempt, manifest_path, review_path)

    def record_reference_preflight(self, manifest_path: Path, manifest: dict,
                                   decision: str = "pass") -> dict:
        config = manifest.get("reference_preflight") or {}
        log_path = self.attempt / str(config.get("ai_review_log_path") or "")
        if log_path.exists() and decision == "pass":
            return {"status": "reference_preflight_passed"}
        records = []
        for reference in config.get("references") or []:
            criteria = []
            for index, criterion in enumerate(config.get("criteria") or []):
                status = "pass" if decision == "pass" or index else "fail"
                criteria.append({"criterion": criterion, "status": status,
                                 "evidence": [f"fixture reference: {status}"]})
            records.append({**reference, "decision": decision, "criteria": criteria})
        review_path = manifest_path.with_suffix(".reference-review.json")
        review_path.write_text(json.dumps({
            "schema_version": PLATE_REFERENCE_REVIEW_SCHEMA,
            "manifest_id": manifest["manifest_id"],
            "references": records,
            "decision": decision,
            "reviewer": "fixture-ai-reference-reviewer",
            "reviewed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }), encoding="utf-8")
        return record_ai_reference_review(self.attempt, manifest_path, review_path)


class Stage5PlateWorkflowTests(Stage5Fixture):
    def test_audit_finds_complete_plate_inputs(self):
        audit = audit_inputs(self.attempt)
        self.assertEqual(audit["counts"]["shots"], 1)
        self.assertEqual(audit["counts"]["start_plate_prompts"], 1)
        self.assertTrue(audit["plate_generation_ready"])
        self.assertEqual(audit["blockers"], [])

    def test_unrecorded_premise_human_approval_does_not_block_stage04_to_stage05(self):
        report_path = self.attempt / "01-premise/qa/report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report.update({"human_approved": False, "release_eligible": False,
                       "production_state": "draft_unapproved"})
        report_path.write_text(json.dumps(report), encoding="utf-8")

        audit = audit_inputs(self.attempt)

        self.assertTrue(audit["plate_generation_ready"])
        self.assertEqual(audit["blockers"], [])
        self.assertIn("premise-human-approval-not-recorded",
                      {item["code"] for item in audit["warnings"]})

    def test_ai_selected_candidate_requires_human_review_before_promotion(self):
        result = prepare_codex_jobs(self.attempt, "plates")
        manifest_path, manifest = self.load_manifest(result)
        self.assertEqual(len(manifest["jobs"]), 1)
        self.assertEqual([item["role"] for item in manifest["jobs"][0]["reference_images"]],
                         ["canonical_stage02_reference_board"] * 2)
        self.candidate_images(manifest)

        finalized = finalize_codex_jobs(self.attempt, manifest_path, "desktop")
        self.assertEqual(finalized["approved"], 0)
        self.assertFalse((self.attempt / "05-plate/output/plates/S01.png").exists())

        review_path = Path(finalized["review_packets"][0])
        review = json.loads(review_path.read_text(encoding="utf-8"))
        review["decision"] = "approved"
        review["reviewer"] = "human-director"
        review["reviewed_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        review["selected_candidate"] = "AI-SELECTED"
        for criterion in review["criteria"]:
            criterion["status"] = "pass"
        review_path.write_text(json.dumps(review), encoding="utf-8")

        applied = apply_review(self.attempt, review_path)
        self.assertEqual(applied["decision"], "approved")
        self.assertTrue((self.attempt / "05-plate/output/plates/S01.png").exists())
        handoff = json.loads((self.attempt / "05-plate/output/h3-conditioning.json")
                             .read_text(encoding="utf-8"))
        self.assertTrue(handoff["ready"])
        self.assertIsNone(handoff["shots"][0]["last_plate"])

    def test_explicit_fast_track_applies_ai_plate_review_without_human_pause(self):
        set_execution_mode(self.attempt, "fast_track", by="user", reason="autonomous run")
        result = prepare_codex_jobs(self.attempt, "plates")
        manifest_path, manifest = self.load_manifest(result)
        self.assertEqual(manifest["execution_mode"]["mode"], "fast_track")
        self.assertEqual(manifest["jobs"][0]["retry_harness"]["exhaustion_policy"],
                         "use_attempt_10_with_accepted_defects")
        self.candidate_images(manifest)

        finalized = finalize_codex_jobs(self.attempt, manifest_path, "desktop")
        review_path = Path(finalized["review_packets"][0])
        review = json.loads(review_path.read_text(encoding="utf-8"))
        self.assertEqual(review["review_mode"], "ai_fast_track")
        self.assertFalse(review["human_approval_required"])
        self.assertTrue(review["auto_approve_allowed"])
        review.update({
            "decision": "approved",
            "reviewer": "codex-ai-fast-track-stage5",
            "reviewed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        })
        for criterion in review["criteria"]:
            criterion.update({"status": "pass", "evidence": ["fixture visual evidence"]})
        review_path.write_text(json.dumps(review), encoding="utf-8")

        applied = apply_review(self.attempt, review_path)
        self.assertEqual(applied["decision"], "approved")
        self.assertTrue((self.attempt / "05-plate/output/plates/S01.png").exists())
        receipt = json.loads((self.attempt / "05-plate/receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["plates"][0]["review_mode"], "ai_fast_track")

    def test_fast_track_accepts_non_safety_defect_only_after_tenth_attempt(self):
        set_execution_mode(self.attempt, "fast_track", by="user", reason="autonomous run")
        result = prepare_codex_jobs(self.attempt, "plates")
        manifest_path, manifest = self.load_manifest(result)
        for _ in range(PLATE_MAX_ATTEMPTS):
            outcome = self.record_plate_attempt(manifest_path, manifest, "fail")
        self.assertEqual(outcome["status"], "selected_for_ai_fast_track_review")
        self.assertEqual(outcome["selected_attempt"], PLATE_MAX_ATTEMPTS)

        review_path = Path(finalize_codex_jobs(
            self.attempt, manifest_path, "desktop")["review_packets"][0])
        review = json.loads(review_path.read_text(encoding="utf-8"))
        accepted_criterion = review["criteria"][0]["criterion"]
        review.update({
            "decision": "approved",
            "reviewer": "codex-ai-fast-track-stage5",
            "reviewed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "accepted_defects": [accepted_criterion],
        })
        for index, criterion in enumerate(review["criteria"]):
            criterion.update({
                "status": "accepted_defect" if index == 0 else "pass",
                "evidence": ["attempt 10 retained with bounded non-safety quality defect"],
            })
        review_path.write_text(json.dumps(review), encoding="utf-8")

        applied = apply_review(self.attempt, review_path)
        self.assertEqual(applied["decision"], "approved")
        receipt = json.loads((self.attempt / "05-plate/receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["plates"][0]["accepted_defects"], [accepted_criterion])

    def test_human_screen_direction_replaces_unresolved_h3_prompt_gate(self):
        direction = {
            "required": True,
            "generation_blocked_until_resolved": True,
            "allowed_depth_intents": [
                "toward_camera", "away_from_camera", "constant_depth"],
        }
        self.design["shots"][0]["motion_control"]["screen_direction_contract"] = direction
        self.design["shots"][0]["motion_prompt"] = (
            "Walk through the room.\nSCREEN DIRECTION — unresolved. Do not generate H3 until "
            "normalized start/end centers, direction vector and depth intent are approved."
        )
        design_path = self.attempt / "04-shot-design/output/shot-cards.json"
        design_path.write_text(json.dumps(self.design), encoding="utf-8")

        result = prepare_codex_jobs(self.attempt, "plates")
        manifest_path, manifest = self.load_manifest(result)
        self.candidate_images(manifest)
        review_path = Path(finalize_codex_jobs(
            self.attempt, manifest_path, "desktop")["review_packets"][0])
        review = json.loads(review_path.read_text(encoding="utf-8"))
        review.update({"decision": "approved", "reviewer": "human-director",
                       "reviewed_at": datetime.now().astimezone().isoformat(timespec="seconds")})
        for criterion in review["criteria"]:
            criterion["status"] = "pass"
        review["screen_direction"].update({
            "start_center_normalized": [0.5, 0.5],
            "end_center_normalized": [0.5, 0.5],
            "screen_direction_vector": [0.0, 0.0],
            "depth_intent": "constant_depth",
        })
        review_path.write_text(json.dumps(review), encoding="utf-8")

        apply_review(self.attempt, review_path)
        handoff = json.loads((self.attempt / "05-plate/output/h3-conditioning.json")
                             .read_text(encoding="utf-8"))
        prompt = handoff["shots"][0]["motion_prompt"]
        self.assertNotIn("unresolved", prompt)
        self.assertIn("human-approved start center [0.5, 0.5]", prompt)
        self.assertIn("depth intent constant_depth", prompt)

    def test_all_references_must_pass_before_any_start_image_review(self):
        result = prepare_codex_jobs(self.attempt, "plates")
        manifest_path, manifest = self.load_manifest(result)
        preflight = manifest["reference_preflight"]
        self.assertEqual(preflight["strategy"], "global_reference_barrier")
        self.assertTrue(preflight["must_complete_before_start_image"])
        self.assertEqual([item["subject_id"] for item in preflight["references"]],
                         ["hero", "room"])
        for criterion in PLATE_REFERENCE_COMPARISON_CRITERIA:
            self.assertIn(criterion,
                          manifest["jobs"][0]["retry_harness"]["acceptance_criteria"])

        failed = self.record_reference_preflight(manifest_path, manifest, "fail")
        self.assertEqual(failed["status"], "reference_repair_required")

        job = manifest["jobs"][0]
        candidate = self.attempt / str(
            job["retry_harness"]["attempt_path_pattern"]).format(attempt=1)
        candidate.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", tuple(job["requested"]), "green").save(candidate)
        review_path = candidate.with_suffix(".review.json")
        review_path.write_text(json.dumps({
            "schema_version": PLATE_AI_ATTEMPT_REVIEW_SCHEMA,
            "job_id": job["job_id"], "decision": "pass",
            "criteria": [
                {"criterion": criterion, "status": "pass", "evidence": ["fixture"]}
                for criterion in job["retry_harness"]["acceptance_criteria"]
            ],
            "feedback": "", "reviewer": "fixture-ai-reviewer",
            "reviewed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }), encoding="utf-8")
        with self.assertRaisesRegex(Stage5Error, "모든 reference preflight"):
            record_ai_plate_review(self.attempt, manifest_path, review_path)

    def test_reference_preflight_cannot_be_backfilled_after_start_generation(self):
        result = prepare_codex_jobs(self.attempt, "plates")
        manifest_path, manifest = self.load_manifest(result)
        job = manifest["jobs"][0]
        candidate = self.attempt / str(
            job["retry_harness"]["attempt_path_pattern"]).format(attempt=1)
        candidate.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", tuple(job["requested"]), "green").save(candidate)

        with self.assertRaisesRegex(Stage5Error, "시작 이미지 생성보다 먼저"):
            self.record_reference_preflight(manifest_path, manifest)

    def test_every_imagegen_job_gets_the_versioned_universal_render_contract(self):
        result = prepare_codex_jobs(self.attempt, "plates")
        _, manifest = self.load_manifest(result)
        receipt = manifest["universal_render_contract"]
        self.assertEqual(receipt["version"], UNIVERSAL_RENDER_CONTRACT_VERSION)
        self.assertTrue(receipt["sha256"])
        for job in manifest["jobs"]:
            prompt = job["imagegen_prompt"]
            self.assertEqual(job["universal_render_contract"], receipt)
            self.assertIn("UNIVERSAL PHYSICAL, LIGHTING AND OPTICAL CONTRACT", prompt)
            self.assertIn("Obey gravity, support and balance", prompt)
            self.assertIn("Honor every upstream lighting contract", prompt)
            self.assertIn("Shadow direction, softness, occlusion, reflections", prompt)
            self.assertIn("Perspective, scale, depth, occlusion and reflections", prompt)

    def test_optional_positive_start_state_override_is_applied_and_receipted(self):
        override_path = self.attempt / "05-plate/prompts/start-state-overrides.json"
        override_path.parent.mkdir(parents=True, exist_ok=True)
        override_path.write_text(json.dumps({
            "schema_version": "stage5-start-state-overrides.v1",
            "reason": "First batch depicted motion.",
            "shots": {"S01": {
                "positive_state": "Hero stands still with both feet planted.",
                "forbidden_state": "walking or reaching the destination",
            }},
        }), encoding="utf-8")

        result = prepare_codex_jobs(self.attempt, "plates")
        _, manifest = self.load_manifest(result)
        job = manifest["jobs"][0]
        self.assertIn("START-PLATE POSITIVE STATE OVERRIDE", job["imagegen_prompt"])
        self.assertIn("both feet planted", job["imagegen_prompt"])
        self.assertTrue(manifest["start_state_override_receipt"]["sha256"])
        pack = json.loads((self.attempt / job["prompt_path"]).read_text(encoding="utf-8"))
        self.assertEqual(pack["start_state_override"]["positive_state"],
                         "Hero stands still with both feet planted.")
        self.assertNotEqual(pack["upstream_prompt_sha256"], pack["prompt_sha256"])

    def test_small_plate_pixel_variance_is_normalized_and_recorded(self):
        result = prepare_codex_jobs(self.attempt, "plates")
        manifest_path, manifest = self.load_manifest(result)
        self.candidate_images(manifest, plate_size=(764, 1334))

        finalized = finalize_codex_jobs(self.attempt, manifest_path, "desktop")

        review = json.loads(Path(finalized["review_packets"][0]).read_text(encoding="utf-8"))
        record = review["candidates"][0]
        self.assertEqual(record["source_dimensions"], [764, 1334])
        self.assertEqual(record["delivered"], [768, 1344])
        self.assertEqual(record["fit"], "tolerance-upscale-and-crop")
        self.assertEqual(record["pixel_tolerance"]["allowed_deficit"], [7, 13])

    def test_approval_rejects_pending_criteria(self):
        result = prepare_codex_jobs(self.attempt, "plates")
        manifest_path, manifest = self.load_manifest(result)
        self.candidate_images(manifest)
        review_path = Path(finalize_codex_jobs(
            self.attempt, manifest_path, "cli")["review_packets"][0])
        review = json.loads(review_path.read_text(encoding="utf-8"))
        review.update({"decision": "approved", "reviewer": "human",
                       "reviewed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                       "selected_candidate": "AI-SELECTED"})
        review_path.write_text(json.dumps(review), encoding="utf-8")
        with self.assertRaises(Stage5Error):
            apply_review(self.attempt, review_path)

    def test_failed_review_retries_one_at_a_time_without_replacing_base_prompt(self):
        result = prepare_codex_jobs(self.attempt, "plates")
        manifest_path, manifest = self.load_manifest(result)
        base_prompt = manifest["jobs"][0]["imagegen_prompt"]

        retry = self.record_plate_attempt(
            manifest_path, manifest, "fail", "keep the action fully unstarted")

        self.assertEqual(retry["status"], "retry_required")
        self.assertEqual(retry["next_attempt"], 2)
        self.assertTrue(retry["imagegen_prompt"].startswith(base_prompt))
        self.assertIn("keep the action fully unstarted", retry["imagegen_prompt"])

        selected = self.record_plate_attempt(manifest_path, manifest, "pass")
        self.assertEqual(selected["status"], "selected_for_human_review")
        self.assertEqual(selected["selected_attempt"], 2)
        with self.assertRaises(Stage5Error):
            self.record_plate_attempt(manifest_path, manifest, "pass")

    def test_ten_consecutive_failures_select_attempt_ten_for_human_review(self):
        result = prepare_codex_jobs(self.attempt, "plates")
        manifest_path, manifest = self.load_manifest(result)
        for number in range(1, PLATE_MAX_ATTEMPTS + 1):
            outcome = self.record_plate_attempt(
                manifest_path, manifest, "fail", f"repair failed criterion {number}")

        self.assertEqual(outcome["status"], "selected_for_human_review")
        self.assertEqual(outcome["selected_attempt"], 10)
        self.assertEqual(outcome["selection_reason"], "max_attempts_exhausted")
        finalized = finalize_codex_jobs(self.attempt, manifest_path, "desktop")
        review = json.loads(Path(finalized["review_packets"][0]).read_text(encoding="utf-8"))
        self.assertTrue(review["ai_retry_harness"]["all_attempts_failed"])
        self.assertEqual(review["ai_retry_harness"]["attempt_count"], 10)


class Stage5ManualWorkflowTests(Stage5Fixture):
    def setUp(self):
        super().setUp()
        self.manual = {
            "manual_id": "S01-IM01", "unresolved_contract_fields": [],
            "image_generation_prompt": "One clean 2x3 interaction board.",
            "required_stage02_sheet_subject_ids": ["hero", "room"],
            "panels": [
                {"panel_id": f"P{i}", "role": "interaction", "state": f"state-{i}"}
                for i in range(1, 7)
            ],
            "approval": {"criteria": ["geometry is consistent", "contact is visible"]},
        }
        contract = Contract.load(self.attempt)
        self.design = self.make_design(contract, self.manual)
        (self.attempt / "04-shot-design/output/shot-cards.json").write_text(
            json.dumps(self.design), encoding="utf-8")

    def test_manual_is_ai_preflight_promoted_before_plate_jobs(self):
        with self.assertRaises(Stage5Error):
            prepare_codex_jobs(self.attempt, "plates")

        result = prepare_codex_jobs(self.attempt, "manuals")
        manifest_path, manifest = self.load_manifest(result)
        self.assertEqual(len(manifest["jobs"]), 1)
        self.candidate_images(manifest)
        finalized = finalize_codex_jobs(self.attempt, manifest_path, "desktop")
        review_path = Path(finalized["review_packets"][0])
        review = json.loads(review_path.read_text(encoding="utf-8"))
        self.assertEqual(review["review_mode"], "ai_preflight")
        self.assertFalse(review["human_approval_required"])
        self.assertTrue(review["auto_approve_allowed"])
        review.update({"decision": "approved", "reviewer": "codex-ai-manual-preflight",
                       "reviewed_at": datetime.now().astimezone().isoformat(timespec="seconds")})
        for criterion in review["criteria"]:
            criterion["status"] = "pass"
        review_path.write_text(json.dumps(review), encoding="utf-8")
        applied = apply_review(self.attempt, review_path)
        self.assertEqual(applied["decision"], "approved")
        receipt = json.loads((self.attempt / "05-plate/receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["manuals"][0]["review_mode"], "ai_preflight")

        plate_result = prepare_codex_jobs(self.attempt, "plates")
        _, plate_manifest = self.load_manifest(plate_result)
        roles = [item["role"] for item in plate_manifest["jobs"][0]["reference_images"]]
        self.assertEqual(roles[-1], "approved_clean_interaction_manual")

    def test_blocked_draft_manual_prompt_is_not_production_input(self):
        self.manual["unresolved_contract_fields"] = ["stage03.interaction_contracts"]
        self.manual["image_generation_prompt"] = None
        contract = Contract.load(self.attempt)
        (self.attempt / "04-shot-design/output/shot-cards.json").write_text(
            json.dumps(self.make_design(contract, self.manual)), encoding="utf-8")
        audit = audit_inputs(self.attempt)
        codes = {item["code"] for item in audit["blockers"]}
        self.assertIn("interaction-manual-spec-unresolved", codes)
        self.assertIn("interaction-manual-prompt-blocked", codes)


if __name__ == "__main__":
    unittest.main()
