import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_video_pipeline.contract import Contract
from ai_video_pipeline.contract_gate import check_frames, check_prompt_packs, check_receipts


CONTRACT = {
    "contract_id": "T",
    "attempt": "v1",
    "frame": {"width": 768, "height": 1344, "fps": 24,
              "applies_to": ["05-plate", "06-motion"]},
    "delivery_frame": {
        "width": 768, "height": 1344, "fps": 24,
        "applies_to": ["07-edit"],
        "transform": {"allowed": False, "operation": "none"},
    },
    "clauses": [
        {"id": "sheet-only", "en": "NO TEXT.", "applies_to": ["02-sheet"]},
    ],
}


class ReceiptIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.attempt = Path(tempfile.mkdtemp()) / "v1"
        target = self.attempt / "01-premise" / "output" / "contract.json"
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps(CONTRACT), encoding="utf-8")
        self.contract = Contract.load(self.attempt)

    def write_receipt(self, stage: str, digest: str) -> None:
        target = self.attempt / stage / "receipt.json"
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps({"contract": {"sha256": digest}}), encoding="utf-8")

    def test_a_receipt_is_checked_even_when_its_stage_has_no_prompt_clause(self):
        self.write_receipt("03-scenario", "obsolete")

        report = check_receipts(self.attempt, self.contract)

        self.assertEqual(report["receipts_checked"], 1)
        self.assertFalse(report["ok"])
        self.assertEqual(report["findings"][0]["receipt"], "03-scenario/receipt.json")

    def test_all_matching_stage_receipts_pass(self):
        self.write_receipt("02-sheet", self.contract.digest)
        self.write_receipt("03-scenario", self.contract.digest)

        report = check_receipts(self.attempt, self.contract)

        self.assertEqual(report["receipts_checked"], 2)
        self.assertTrue(report["ok"])

    def test_a_human_can_accept_a_narrow_recorded_compatibility_without_rewriting_the_receipt(self):
        self.write_receipt("02-sheet", "previous")
        target = self.attempt / "02-sheet" / "qa" / "contract-compatibility.json"
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps({
            "status": "accepted",
            "scope": "02-sheet",
            "receipt": "02-sheet/receipt.json",
            "recorded_contract_sha256": "previous",
            "current_contract_sha256": self.contract.digest,
            "accepted_by": "user",
            "basis": ["stage inputs and rules match"],
            "does_not_rewrite_original_receipt": True,
        }), encoding="utf-8")

        report = check_receipts(self.attempt, self.contract)

        self.assertTrue(report["ok"])
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["warnings"][0]["accepted_by"], "user")

    def test_a_revalidation_receipt_can_record_a_later_non_stage_change(self):
        target = self.attempt / "01-premise" / "qa" / "premise-revalidation-receipt-old.json"
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps({
            "contract": {"sha256": "previous"},
            "superseded_compatibility": {
                "status": "accepted",
                "recorded_contract_sha256": "previous",
                "current_contract_sha256": self.contract.digest,
                "basis": ["only a downstream clause changed"],
                "does_not_rewrite_original_receipt": True,
            },
        }), encoding="utf-8")
        report = check_receipts(self.attempt, self.contract)
        self.assertTrue(report["ok"])
        self.assertEqual(report["findings"], [])


class PromptScopeTests(unittest.TestCase):
    def setUp(self):
        self.attempt = Path(tempfile.mkdtemp()) / "v1"
        data = json.loads(json.dumps(CONTRACT))
        data["clauses"].append({
            "id": "character-only",
            "en": "NO REAL PERSON LIKENESS.",
            "applies_to": ["02-sheet"],
            "subject_kinds": ["character"],
        })
        target = self.attempt / "01-premise/output/contract.json"
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps(data), encoding="utf-8")
        self.contract = Contract.load(self.attempt)

    def test_gate_reports_a_kind_scoped_clause_leaking_into_a_setting_prompt(self):
        target = self.attempt / "02-sheet/prompts/room.json"
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps({
            "element": "room",
            "kind": "setting",
            "prompt": "Interior board. NO TEXT. NO REAL PERSON LIKENESS.",
        }), encoding="utf-8")

        report = check_prompt_packs(self.attempt, self.contract)

        self.assertFalse(report["ok"])
        self.assertEqual(report["findings"][0]["inapplicable_clauses"],
                         ["character-only"])


class FrameTargetTests(unittest.TestCase):
    def setUp(self):
        self.attempt = Path(tempfile.mkdtemp()) / "v1"
        data = json.loads(json.dumps(CONTRACT))
        data["delivery_frame"] = {
            "width": 1080, "height": 1920, "fps": 24,
            "applies_to": ["07-edit"],
            "transform": {
                "allowed": True,
                "operation": "center-crop-and-scale",
                "crop": {"width": 756, "height": 1344},
                "scale": 1.428571,
            },
        }
        target = self.attempt / "01-premise" / "output" / "contract.json"
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps(data), encoding="utf-8")
        self.contract = Contract.load(self.attempt)
        for relative in ("05-plate/output/plate.mp4", "07-edit/output/final.mp4"):
            path = self.attempt / relative
            path.parent.mkdir(parents=True)
            path.touch()

    @patch("ai_video_pipeline.contract_gate._probe")
    def test_generation_and_edit_outputs_use_different_declared_targets(self, probe):
        probe.side_effect = [(768, 1344), (1080, 1920)]
        report = check_frames(self.attempt, self.contract, ["*/output/*.mp4"])
        self.assertTrue(report["ok"])
        self.assertEqual(report["stage_targets"]["05-plate"], [768, 1344])
        self.assertEqual(report["stage_targets"]["07-edit"], [1080, 1920])

    @patch("ai_video_pipeline.contract_gate._probe", return_value=(768, 1344))
    def test_a_declared_transform_does_not_excuse_a_wrong_final_file(self, _probe):
        report = check_frames(self.attempt, self.contract, ["07-edit/output/*.mp4"])
        self.assertFalse(report["ok"])
        self.assertEqual(report["findings"][0]["contract"], [1080, 1920])


if __name__ == "__main__":
    unittest.main()
