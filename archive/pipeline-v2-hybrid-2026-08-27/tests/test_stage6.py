from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from ai_video_pipeline.contract import Contract
from ai_video_pipeline.execution_mode import set_execution_mode
from ai_video_pipeline.stage6 import Stage6Error, prepare
from ai_video_pipeline.stage6_finish import append_retries


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Stage6PrepareTests(unittest.TestCase):
    def setUp(self):
        self.attempt = Path(tempfile.mkdtemp())
        contract_data = {
            "contract_id": "STAGE6-TEST", "attempt": "v1",
            "stages": {"premise": "01-premise", "plate": "05-plate", "motion": "06-motion"},
            "frame": {"width": 768, "height": 1344, "fps": 24,
                      "applies_to": ["05-plate", "06-motion"],
                      "upscale": {"allowed": False}},
            "delivery_frame": {"width": 768, "height": 1344, "fps": 24,
                               "applies_to": ["07-edit"],
                               "transform": {"allowed": False, "operation": "none"}},
            "motion": {"runtime": "minimax-h3-local-768p", "frame_source": "frame"},
            "audio": {"h3_native_audio": "discard", "target_language": "ko",
                      "dialogue_source": "approved_script_only",
                      "lip_sync": "only_when_onscreen_speaker_is_explicit"},
            "image": {"model": "gpt-image-2", "quality": "high", "api_sizes": [],
                      "roles": {}},
            "subjects": {"declared": {}}, "clauses": [],
        }
        contract_path = self.attempt / "01-premise/output/contract.json"
        contract_path.parent.mkdir(parents=True)
        contract_path.write_text(json.dumps(contract_data), encoding="utf-8")
        contract = Contract.load(self.attempt)
        plate = self.attempt / "05-plate/output/plates/S01.png"
        ref = self.attempt / "02-sheet/output/sheets/hero.png"
        plate.parent.mkdir(parents=True)
        ref.parent.mkdir(parents=True)
        Image.new("RGB", (768, 1344), "black").save(plate)
        Image.new("RGB", (1536, 1024), "blue").save(ref)
        handoff = {
            "schema_version": "stage5-h3-handoff.v1", "status": "ready", "ready": True,
            "contract": {"sha256": contract.digest,
                         "stage_frame": {"width": 768, "height": 1344, "fps": 24}},
            "shots": [{"shot_id": "S01", "first_plate": {"path": str(plate.relative_to(self.attempt)),
                        "sha256": sha(plate)}, "canonical_stage02_sheets": [
                        {"subject_id": "hero", "path": str(ref.relative_to(self.attempt)),
                         "sha256": sha(ref)}], "approved_interaction_manuals": [],
                        "motion_prompt": "A slow natural wave.\nSCREEN DIRECTION — not required."}],
        }
        handoff_path = self.attempt / "05-plate/output/h3-conditioning.json"
        handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
        pack_path = self.attempt / "06-motion/prompts/shot-pack.json"
        pack_path.parent.mkdir(parents=True)
        pack_path.write_text(json.dumps({"video_engine": "minimax-h3-local-768p", "shots": [{
            "shot": "S01", "generation_seconds": 5.0,
            "candidate_policy": {"candidate_count": 1, "max_attempts": 10},
            "generation_blocked": True,
        }]}), encoding="utf-8")

    def test_prepares_one_reference_bound_take_before_review(self):
        first = prepare(self.attempt)
        second = prepare(self.attempt)
        self.assertEqual(first, second)
        self.assertEqual(first["job_count"], 1)
        self.assertEqual([job["candidate_id"] for job in first["jobs"]],
                         ["C01"])
        self.assertTrue(first["selection_contract"]["append_retry_only_after_review_failure"])
        self.assertEqual(first["selection_contract"]["max_varied_attempts_per_artifact"], 10)
        self.assertIn("<Picture 1>", first["jobs"][0]["prompt"])
        self.assertIn("LOCKED COMPOSITION GUARD", first["jobs"][0]["prompt"])
        self.assertIn("exact first-plate inventory", first["jobs"][0]["prompt"])
        self.assertFalse(first["jobs"][0]["status"] == "completed")

    def test_rejects_unresolved_screen_direction_prompt(self):
        path = self.attempt / "05-plate/output/h3-conditioning.json"
        handoff = json.loads(path.read_text(encoding="utf-8"))
        handoff["shots"][0]["motion_prompt"] = (
            "SCREEN DIRECTION — unresolved. Do not generate H3 until approved.")
        path.write_text(json.dumps(handoff), encoding="utf-8")
        with self.assertRaisesRegex(Stage6Error, "미해결"):
            prepare(self.attempt)

    def test_review_failure_appends_exactly_one_varied_take(self):
        set_execution_mode(self.attempt, "fast_track", by="user", reason="autonomous retry")
        manifest = prepare(self.attempt)
        selection = self.attempt / "06-motion/qa/ai-fast-track/selection.json"
        selection.parent.mkdir(parents=True, exist_ok=True)
        selection.write_text(json.dumps({
            "needs_retry": [{"shot_id": "S01", "feedback": "hand contact drift"}],
        }), encoding="utf-8")
        result = append_retries(self.attempt)
        self.assertEqual(result["appended"], ["S01-C02"])
        updated = json.loads((self.attempt / "06-motion/qa/manifest.json").read_text())
        self.assertEqual([job["candidate_id"] for job in updated["jobs"]], ["C01", "C02"])
        self.assertNotEqual(updated["jobs"][0]["prompt_sha256"],
                            updated["jobs"][1]["prompt_sha256"])
        self.assertIn("hand contact drift", updated["jobs"][1]["prompt"])

    def test_fast_track_manifest_uses_ai_selection_and_invalidates_normal_manifest(self):
        normal = prepare(self.attempt)
        self.assertTrue(normal["selection_contract"]["human_approval_required"])
        set_execution_mode(self.attempt, "fast_track", by="user", reason="autonomous run")
        with self.assertRaisesRegex(Stage6Error, "--force"):
            prepare(self.attempt)
        fast = prepare(self.attempt, force=True)
        self.assertEqual(fast["execution_mode"]["mode"], "fast_track")
        self.assertFalse(fast["selection_contract"]["human_approval_required"])
        self.assertTrue(fast["selection_contract"]["auto_approve_allowed"])
        self.assertIn("automatic continuation", fast["candidate_policy"])


if __name__ == "__main__":
    unittest.main()
