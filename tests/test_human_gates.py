import json
import tempfile
import unittest
from pathlib import Path

from ai_video_pipeline.human_gates import (
    GateContractError,
    load_catalog,
    resolve_required_gates,
    validate_judgment_packet,
    validate_feedback_delta,
)

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "contracts" / "human-gates.v1.json"
EXAMPLE = ROOT / "examples" / "g7-pacing-review.json"


class GateCatalogTests(unittest.TestCase):
    def test_catalog_defines_exactly_g1_through_g10_with_executable_contracts(self):
        catalog = load_catalog(CATALOG)
        self.assertEqual([g["gate_id"] for g in catalog["gates"]], [f"G{i}" for i in range(1, 11)])
        for gate in catalog["gates"]:
            self.assertTrue(gate["owner_roles"])
            self.assertTrue(gate["stages"])
            self.assertTrue(gate["trigger_dimensions"])
            self.assertTrue(gate["required_evidence"])
            self.assertTrue(gate["question_contract"]["single_decision"])
            self.assertIn(gate["authority"], {"human_required", "human_release_only"})

    def test_performance_hero_take_routes_to_g3_and_never_auto_approves(self):
        catalog = load_catalog(CATALOG)
        result = resolve_required_gates(
            catalog,
            {
                "stage": "shot_exception_review",
                "dimensions": ["performance"],
                "hero_take": True,
                "critic_disagreement": True,
                "ai_margin": 0.2,
            },
        )
        self.assertEqual(result["gate_ids"], ["G3"])
        self.assertTrue(result["human_required"])
        self.assertFalse(result["auto_approve_allowed"])
        self.assertIn("hero_take", result["reasons"])

    def test_rough_cut_routes_rhythm_and_sound_to_separate_gates(self):
        catalog = load_catalog(CATALOG)
        result = resolve_required_gates(
            catalog,
            {"stage": "rough_cut_review", "dimensions": ["rhythm", "sound"]},
        )
        self.assertEqual(result["gate_ids"], ["G7", "G8"])

    def test_release_with_culture_risk_routes_to_g10(self):
        catalog = load_catalog(CATALOG)
        result = resolve_required_gates(
            catalog,
            {"stage": "final_qa_pending", "dimensions": ["culture_ethics"], "release": True},
        )
        self.assertEqual(result["gate_ids"], ["G10"])
        self.assertFalse(result["auto_approve_allowed"])

    def test_explicit_fast_track_resolves_internal_gate_without_human_pause(self):
        catalog = load_catalog(CATALOG)
        result = resolve_required_gates(catalog, {
            "stage": "shot_exception_review",
            "dimensions": ["performance"],
            "hero_take": True,
            "execution_mode": "fast_track",
        })
        self.assertEqual(result["gate_ids"], ["G3"])
        self.assertFalse(result["human_required"])
        self.assertTrue(result["auto_approve_allowed"])
        self.assertEqual(result["resolution_mode"], "ai_fast_track")
        self.assertTrue(result["accepted_defect_record_required"])
        self.assertFalse(result["external_side_effects_authorized"])


class JudgmentPacketTests(unittest.TestCase):
    def test_checked_in_g7_example_is_valid(self):
        catalog = load_catalog(CATALOG)
        packet = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        self.assertEqual(validate_judgment_packet(packet, catalog), [])

    def test_packet_requires_comparable_options_with_strength_and_loss(self):
        catalog = load_catalog(CATALOG)
        packet = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        packet["options"][1].pop("loss")
        with self.assertRaisesRegex(GateContractError, "options.1.loss"):
            validate_judgment_packet(packet, catalog)

    def test_packet_rejects_recommendation_outside_options(self):
        catalog = load_catalog(CATALOG)
        packet = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        packet["ai_recommendation"] = "Z"
        with self.assertRaisesRegex(GateContractError, "ai_recommendation"):
            validate_judgment_packet(packet, catalog)

    def test_feedback_delta_preserves_priority_and_accepted_defect(self):
        delta = {
            "gate_id": "G7",
            "scope_ids": ["scene_12"],
            "keep": ["subdued_expression", "no_music"],
            "change": ["cut_out_plus_12_frames"],
            "forbid": ["expository_insert"],
            "priority_order": ["performance_authenticity", "comprehension", "pace"],
            "accepted_defects": ["background_hand_mismatch_0.2s"],
            "regeneration_scope": "none",
            "verification_question": "12프레임 hold가 과장 없이 상처를 읽히게 하는가?",
            "user_words": "B로 가되 음악은 넣지 말자",
        }
        self.assertEqual(validate_feedback_delta(delta), [])

    def test_feedback_delta_cannot_omit_human_words(self):
        delta = {
            "gate_id": "G3", "scope_ids": ["S07"], "keep": [], "change": [],
            "forbid": [], "priority_order": ["performance"], "accepted_defects": [],
            "regeneration_scope": "S07_end", "verification_question": "표정이 유지되는가?",
        }
        with self.assertRaisesRegex(GateContractError, "user_words"):
            validate_feedback_delta(delta)


if __name__ == "__main__":
    unittest.main()
