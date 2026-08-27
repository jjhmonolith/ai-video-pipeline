import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from ai_video_pipeline.contract import Contract
from ai_video_pipeline.lifecycle import canonical_digest, direction_impact
from ai_video_pipeline.premise import PROPOSE_RULES, plan_questions
from ai_video_pipeline.scenario import (
    SCENARIO_SCHEMA,
    ScenarioError,
    check as check_scenario,
    gather,
)
from ai_video_pipeline.sheets import audit_references
from ai_video_pipeline.subjects import approval_digest, check_subject


ROOT = Path(__file__).resolve().parents[1]
ATTEMPTS = [
    ROOT / "runs/sky-village-plumber/attempts/v1-pilot",
    ROOT / "runs/luxury-penthouse-tour/attempts/v1-pilot",
]


class RegressionAttemptTests(unittest.TestCase):
    def test_both_attempts_are_equal_current_loader_fixtures(self):
        contracts = [Contract.load(path) for path in ATTEMPTS]
        self.assertTrue(all(c.delivery_frame for c in contracts))
        self.assertTrue(all(c.spatial_graph.get("nodes") for c in contracts))

    def test_existing_scenarios_expose_quality_warnings(self):
        expected_overloaded = [
            {"B02", "B06", "B07", "B08", "B09"},
            {"B03", "B05", "B06"},
        ]
        for attempt, expected in zip(ATTEMPTS, expected_overloaded):
            contract = Contract.load(attempt)
            story = json.loads((attempt / "03-scenario/output/scenario.json").read_text())
            report = check_scenario(story, contract)
            warned = {w["beat_id"] for w in report["warnings"]
                      if w["code"] in {"action-overcrowded", "beat-time-overflow"}}
            self.assertTrue(expected <= warned, (attempt.name, expected - warned))
            self.assertTrue(any(w["code"] == "sublocation-missing"
                                for w in report["warnings"]))

    def test_fresh_scenario_generation_cannot_consume_unreviewed_whole_boards(self):
        attempt = ATTEMPTS[1]
        with self.assertRaises(ScenarioError) as caught:
            gather(attempt, Contract.load(attempt))
        self.assertIn("human_review_required", str(caught.exception))

    def test_interacted_object_without_part_contract_is_reported(self):
        attempt = ATTEMPTS[0]
        contract = Contract.load(attempt)
        story = json.loads((attempt / "03-scenario/output/scenario.json").read_text())
        beat = next(item for item in story["beats"] if item["id"] == "B07")
        beat["object_roles"] = [{"subject_id": "toolkit", "role": "interacted_with"}]
        report = check_scenario(story, contract)
        self.assertTrue(any(item["code"] == "interaction-contract-missing"
                            and item["beat_id"] == "B07"
                            for item in report["warnings"]))


class SceneDesignContractTests(unittest.TestCase):
    def test_new_story_can_invent_a_prop_when_it_declares_reference_debt(self):
        contract = Contract(
            path=Path("contract.json"), root=Path("."), digest="test",
            data={
                "runtime_contract": {"mode": "fixed", "target_seconds": 12},
                "subjects": {"declared": {
                    "hero": {"kind": "character"}, "room": {"kind": "setting"},
                }},
                "scenario": {"acts": [{"id": "main"}]}, "clauses": [],
            },
        )
        story = {
            "schema_version": SCENARIO_SCHEMA,
            "sequences": [{"id": "SQ01", "scenes": [{
                "id": "SC01", "act_id": "main", "scene_intent": "reveal a clue",
                "scene_role": "turn", "pov_owner": "hero", "dramatic_question": "what changed?",
                "entry_state": "uncertain", "exit_state": "understands",
                "where_subject_id": "room", "sublocation_id": "room",
                "estimated_edit_range_seconds": [8, 14],
                "pacing": {"tempo": "유예", "reason": "discovery needs a held reaction"},
                "temporal_intent": {"candidate_modes": ["time_freeze"],
                                    "dramatic_reason": "hold the discovery"},
                "events": [{"id": "E01", "actor_subject_id": "hero",
                            "target_subject_id": "NEW-key", "action": "finds the key",
                            "visible_change": "the key enters view", "result_state": "found"}],
                "cast_presence": [{"subject_id": "hero", "role": "actor"}],
                "object_roles": [{"subject_id": "NEW-key", "role": "interacted_with"}],
                "visual_focus": ["NEW-key"],
                "production_requirements": [{
                    "id": "NEW-key", "name": "brass key",
                    "asset_class": "scene_only_hero_prop", "description": "a worn brass key",
                    "reference_policy": "scene_reference", "used_by_event_ids": ["E01"],
                    "resolution_notes": [],
                }],
            }]}],
        }
        report = check_scenario(story, contract)
        self.assertTrue(report["ok"], report["problems"])
        self.assertEqual(report["reference_debt_count"], 1)
        self.assertNotIn("beats", report)


class LifecycleTests(unittest.TestCase):
    def test_a_supplement_marks_older_subjects_for_revalidation(self):
        attempt = Path(tempfile.mkdtemp())
        data = {
            "contract_id": "T", "attempt": "a",
            "frame": {"width": 1, "height": 1, "fps": 24, "applies_to": []},
            "delivery_frame": {"width": 1, "height": 1, "fps": 24,
                               "applies_to": [],
                               "transform": {"allowed": False, "operation": "none"}},
            "stages": {"premise": "01-premise", "sheet": "02-sheet", "scenario": "03-scenario"},
            "subjects": {"declared": {"hero": {"kind": "character"}}},
            "clauses": [],
        }
        contract_path = attempt / "01-premise/output/contract.json"
        contract_path.parent.mkdir(parents=True)
        contract_path.write_text(json.dumps(data))
        subject = attempt / "01-premise/output/subjects/hero.json"
        subject.parent.mkdir(parents=True)
        subject.write_text(json.dumps({"provenance": {"decided_at": "2026-01-01T00:00:00+00:00"}}))
        contract = Contract.load(attempt)
        report = direction_impact(attempt, contract, {
            "direction": "first", "supplements": [
                {"direction": "changed", "received_at": "2026-01-02T00:00:00+00:00"}
            ]})
        self.assertEqual(report["artifacts"][0]["status"], "revalidation_required")
        self.assertFalse(report["downstream_allowed"])

    def test_a_scoped_sheet_direction_revalidation_clears_timestamp_drift(self):
        attempt = Path(tempfile.mkdtemp())
        data = {
            "contract_id": "T", "attempt": "a",
            "frame": {"width": 1, "height": 1, "fps": 24, "applies_to": []},
            "delivery_frame": {"width": 1, "height": 1, "fps": 24,
                               "applies_to": [],
                               "transform": {"allowed": False, "operation": "none"}},
            "stages": {"premise": "01-premise", "sheet": "02-sheet", "scenario": "03-scenario"},
            "subjects": {"declared": {"module": {"kind": "subject"}}},
            "clauses": [],
        }
        contract_path = attempt / "01-premise/output/contract.json"
        contract_path.parent.mkdir(parents=True)
        contract_path.write_text(json.dumps(data))
        sheet = attempt / "02-sheet/output/sheets/module.png"
        sheet.parent.mkdir(parents=True)
        sheet.write_bytes(b"sheet")
        direction = {"direction": "first", "supplements": [
            {"direction": "faceless people", "received_at": "2026-01-02T00:00:00+00:00"}
        ]}
        receipt = attempt / "02-sheet/receipt.json"
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(json.dumps({"sheets": [{
            "element": "module", "created_at": "2026-01-01T00:00:00+00:00",
            "direction_revalidation": {
                "status": "compatible",
                "direction_sha256": canonical_digest(direction),
                "revalidated_at": "2026-01-03T00:00:00+00:00",
                "basis": "the module contains no people",
            },
        }]}))
        report = direction_impact(attempt, Contract.load(attempt), direction)
        artifact = next(item for item in report["artifacts"]
                        if item["artifact_type"] == "reference_sheet")
        self.assertEqual(artifact["status"], "compatible")
        self.assertEqual(artifact["timestamp_source"],
                         "sheet.receipt.direction_revalidation.revalidated_at")
        self.assertTrue(report["downstream_allowed"])

    def test_approval_is_invalidated_when_the_definition_changes(self):
        spec = {"name": "A", "provenance": {"approved_by": "reviewer"}}
        spec["provenance"]["approved_subject_sha256"] = approval_digest(spec)
        self.assertEqual(spec["provenance"]["approved_subject_sha256"], approval_digest(spec))
        spec["name"] = "B"
        self.assertNotEqual(spec["provenance"]["approved_subject_sha256"], approval_digest(spec))


class ResearchPlanTests(unittest.TestCase):
    def test_question_limit_is_persisted_at_plan_unit_not_result_unit(self):
        attempt = Path(tempfile.mkdtemp())
        data = {
            "contract_id": "T", "attempt": "a", "duration_seconds": 30,
            "frame": {"width": 1, "height": 1, "fps": 24, "applies_to": []},
            "delivery_frame": {"width": 1, "height": 1, "fps": 24,
                               "applies_to": [],
                               "transform": {"allowed": False, "operation": "none"}},
            "research": {"max_questions": 2, "max_image_questions": 1},
            "subjects": {"declared": {"hero": {"kind": "character"}}},
            "clauses": [],
        }
        target = attempt / "01-premise/output/contract.json"
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps(data))
        (attempt / "01-premise/output/direction.json").write_text(json.dumps({"direction": "x"}))
        response = SimpleNamespace(output_text=json.dumps({"questions": [
            {"ask": "a", "mode": "image"}, {"ask": "b", "mode": "image"},
            {"ask": "c", "mode": "text"},
        ]}))
        client = SimpleNamespace(responses=SimpleNamespace(create=lambda **_: response))
        with patch("ai_video_pipeline.premise._client", return_value=client):
            planned = plan_questions(attempt, Contract.load(attempt))
        self.assertEqual(len(planned), 2)
        doc = json.loads((attempt / "01-premise/output/research-plan.json").read_text())
        self.assertEqual(doc["planned_question_count"], 2)
        self.assertEqual(doc["limits"]["max_questions"], 2)


class SheetReferenceContractTests(unittest.TestCase):
    def test_pixel_existence_never_becomes_semantic_pass(self):
        source = ATTEMPTS[1]
        report = audit_references(source, Contract.load(source))
        self.assertFalse(report["reference_ready"])
        doc = json.loads(Path(report["panel_manifest"]).read_text())
        panel = doc["sheets"][0]["panels"][0]
        self.assertIsNone(panel["crop_coordinates"])
        self.assertIsNone(panel["reference_crop_path"])
        self.assertEqual(panel["review_status"], "human_review_required")
        self.assertIn("canonical_owner", doc["sheets"][0])
        self.assertTrue(panel["reference_role_candidates"])
        self.assertEqual(panel["binds_part_ids"], [])
        self.assertEqual(panel["binds_interaction_site_ids"], [])
        self.assertEqual(panel["mechanical_fit_evidence"]["minimum_capacity_ratio"], 1.15)
        self.assertIsNone(panel["mechanical_fit_evidence"]["target_angle_deg"])
        checks = {item["check_id"] for review in
                  json.loads(Path(report["semantic_review"]).read_text())["reviews"]
                  for item in review["checks"]}
        self.assertIn("mechanical_scale_and_axis_feasibility", checks)
        self.assertIn("never H3 conditioning inputs", doc["policy"])

    def test_professional_tool_definition_requires_capacity_and_axis_facts(self):
        self.assertIn("capacity_contract", PROPOSE_RULES)
        self.assertIn("action-plane/axis", PROPOSE_RULES)


if __name__ == "__main__":
    unittest.main()
