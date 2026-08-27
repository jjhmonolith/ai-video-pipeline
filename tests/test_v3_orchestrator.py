from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ai_video_pipeline.v3.orchestrator import (
    OrchestratorError,
    approve,
    initialize,
    load_state,
    review,
    set_mode,
    submit,
    work_order,
)
from ai_video_pipeline.v3.specs import CRITIC_CRITERIA, DEFAULT_NORMAL_HUMAN_GATES, STAGE_INDEX


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stage01_artifact(order: dict, direction: str) -> dict:
    return {
        "schema_version": "llm-stage-artifact.v1",
        "pipeline_version": "3.0",
        "stage_id": "01-premise",
        "attempt_id": order["attempt_id"],
        "authored_by": "test author",
        "authored_at": now(),
        "input_receipts": order["input_receipts"],
        "creative_decisions": [{"decision": "runtime", "reason": "brief", "evidence": direction}],
        "content": {
            "direction": {"verbatim": direction, "interpretation": "test production"},
            "runtime_contract": {"mode": "fixed", "target_seconds": 12, "reason": "format"},
            "frame": {"width": 1344, "height": 768, "fps": 24, "orientation": "landscape"},
            "delivery_frame": {"width": 1920, "height": 1080, "fps": 24, "orientation": "landscape"},
            "subjects": [{
                "subject_id": "CHAR-01",
                "kind": "character",
                "purpose": "host",
                "reference_required": True,
                "definition": {"identity": "anonymous host", "invariants": ["same person"]},
            }],
            "contract_clauses": [],
        },
    }


def critique(stage_id: str, artifact_hash: str, decision: str = "pass",
             *, accepted_defects: list[str] | None = None,
             failure_classes: list[str] | None = None) -> dict:
    criteria = []
    for index, (criterion_id, _) in enumerate(CRITIC_CRITERIA[stage_id]):
        failed = decision == "fail" and index == 0
        criteria.append({
            "criterion_id": criterion_id,
            "status": "fail" if failed else "pass",
            "evidence": "specific failing evidence" if failed else "specific passing evidence",
        })
    return {
        "schema_version": "llm-stage-critique.v1",
        "stage_id": stage_id,
        "artifact_sha256": artifact_hash,
        "reviewer": "fresh-context test critic",
        "reviewed_at": now(),
        "summary": f"{decision} after evidence review",
        "decision": decision,
        "criteria": criteria,
        "failure_classes": (failure_classes if failure_classes is not None
                            else (["quality"] if decision == "fail" else [])),
        "accepted_defects": accepted_defects or [],
    }


class OrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.attempt = Path(self.temp.name) / "attempt-v3"
        self.direction = "가로 12초 익명 호스트 테스트"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_for_order(self, order: dict, payload: dict) -> Path:
        path = self.attempt / order["artifact_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def write_critique(self, order: dict, payload: dict) -> Path:
        path = self.attempt / order["critique_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def test_normal_stage01_pass_reaches_human_gate_then_advances(self) -> None:
        initialize(self.attempt, self.direction)
        order = work_order(self.attempt)
        self.assertEqual(order["stage_skill"], "video-stage01-premise")
        self.write_for_order(order, stage01_artifact(order, self.direction))
        submitted = submit(self.attempt)
        self.assertEqual(submitted["status"], "critic_required")
        self.write_critique(order, critique("01-premise", submitted["artifact_sha256"]))
        result = review(self.attempt)
        self.assertEqual(result["status"], "human_gate")
        advanced = approve(self.attempt, "01-premise", by="user", decision="approve")
        self.assertEqual(advanced["next_stage"], "02-sheet")
        self.assertTrue((self.attempt / "01-premise/receipt.json").is_file())
        sheet_order = work_order(self.attempt)
        board_input = sheet_order["stage_inputs"]["boards"][0]
        self.assertEqual(board_input["canvas_contract"]["orientation"], "landscape")
        self.assertTrue(board_input["canvas_contract"]["independent_of_video_frame"])
        self.assertEqual(len(board_input["required_panel_ids"]), 9)
        self.assertEqual(board_input["source_definition"], {"identity": "anonymous host", "invariants": ["same person"]})
        self.assertIn("명세보다 정의가 우선", board_input["writer_rules"])
        self.assertIn("FIXED LAYOUT", board_input["sheet_specification"])

    def test_fast_track_pass_seals_without_internal_gate(self) -> None:
        initialize(self.attempt, self.direction, mode="fast_track", by="user",
                   reason="explicit autonomous production")
        order = work_order(self.attempt)
        self.write_for_order(order, stage01_artifact(order, self.direction))
        submitted = submit(self.attempt)
        self.write_critique(order, critique("01-premise", submitted["artifact_sha256"]))
        result = review(self.attempt)
        self.assertEqual(result["next_stage"], "02-sheet")
        self.assertEqual(load_state(self.attempt)["status"], "running")

    def test_critic_failure_gets_distinct_next_strategy(self) -> None:
        initialize(self.attempt, self.direction, mode="fast_track", by="user", reason="test")
        first = work_order(self.attempt)
        self.write_for_order(first, stage01_artifact(first, self.direction))
        submitted = submit(self.attempt)
        self.write_critique(first, critique("01-premise", submitted["artifact_sha256"], "fail"))
        failed = review(self.attempt)
        self.assertEqual(failed["status"], "needs_repair")
        second = work_order(self.attempt)
        self.assertEqual(second["attempt_number"], 2)
        self.assertNotEqual(second["variation_strategy"], first["variation_strategy"])
        self.assertTrue(second["failed_criteria"])

    def test_direction_drift_fails_deterministic_submission(self) -> None:
        initialize(self.attempt, self.direction)
        order = work_order(self.attempt)
        artifact = stage01_artifact(order, "different direction")
        self.write_for_order(order, artifact)
        result = submit(self.attempt)
        self.assertEqual(result["status"], "needs_repair")
        self.assertIn("direction-drift", {item["code"] for item in result["problems"]})

    def test_switching_passed_normal_gate_to_fast_track_advances(self) -> None:
        initialize(self.attempt, self.direction)
        order = work_order(self.attempt)
        self.write_for_order(order, stage01_artifact(order, self.direction))
        submitted = submit(self.attempt)
        self.write_critique(order, critique("01-premise", submitted["artifact_sha256"]))
        self.assertEqual(review(self.attempt)["status"], "human_gate")
        result = set_mode(self.attempt, "fast_track", by="user", reason="explicit request")
        self.assertEqual(result["next_stage"], "02-sheet")

    def test_critique_path_cannot_escape_attempt(self) -> None:
        initialize(self.attempt, self.direction, mode="fast_track", by="user", reason="test")
        order = work_order(self.attempt)
        self.write_for_order(order, stage01_artifact(order, self.direction))
        submitted = submit(self.attempt)
        outside = Path(self.temp.name) / "outside.json"
        outside.write_text(json.dumps(critique("01-premise", submitted["artifact_sha256"])), encoding="utf-8")
        with self.assertRaises(OrchestratorError):
            review(self.attempt, outside)

    def test_stage04_is_not_a_pre_stage05_human_gate(self) -> None:
        self.assertNotIn("04-shot-design", DEFAULT_NORMAL_HUMAN_GATES)
        self.assertIn("05-plate", DEFAULT_NORMAL_HUMAN_GATES)

    def test_stage055_sits_between_plate_and_motion_without_a_human_gate(self) -> None:
        self.assertLess(STAGE_INDEX["05-plate"], STAGE_INDEX["05.5-motion-prompt"])
        self.assertLess(STAGE_INDEX["05.5-motion-prompt"], STAGE_INDEX["06-motion"])
        self.assertNotIn("05.5-motion-prompt", DEFAULT_NORMAL_HUMAN_GATES)

    def test_fast_track_attempt_10_accepts_only_recorded_quality_defect(self) -> None:
        initialize(self.attempt, self.direction, mode="fast_track", by="user", reason="test retry limit")
        result = None
        for number in range(1, 11):
            order = work_order(self.attempt)
            self.assertEqual(order["attempt_number"], number)
            self.write_for_order(order, stage01_artifact(order, self.direction))
            submitted = submit(self.attempt)
            defects = ["minor non-safety aesthetic defect remains"] if number == 10 else []
            self.write_critique(order, critique(
                "01-premise", submitted["artifact_sha256"], "fail",
                accepted_defects=defects, failure_classes=["quality"],
            ))
            result = review(self.attempt)
        self.assertEqual(result["next_stage"], "02-sheet")
        receipt = json.loads((self.attempt / "01-premise/receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["resolution"], "fast_track_attempt_10")
        self.assertEqual(receipt["accepted_defects"], ["minor non-safety aesthetic defect remains"])


if __name__ == "__main__":
    unittest.main()
