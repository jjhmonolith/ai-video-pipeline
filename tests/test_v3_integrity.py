from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from ai_video_pipeline.v3.integrity import (
    file_sha256,
    stage02_authoring_inputs,
    stage02_meta_prompt_sha256,
    text_sha256,
    validate_artifact,
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def envelope(stage_id: str, content: dict) -> dict:
    return {
        "schema_version": "llm-stage-artifact.v1",
        "pipeline_version": "3.0",
        "stage_id": stage_id,
        "attempt_id": "v3-test",
        "authored_by": "test LLM",
        "authored_at": now(),
        "input_receipts": [],
        "creative_decisions": [],
        "content": content,
    }


def premise() -> dict:
    return envelope("01-premise", {
        "direction": {"verbatim": "two-person landscape test"},
        "runtime_contract": {"mode": "fixed", "target_seconds": 5},
        "frame": {"width": 1344, "height": 768, "fps": 24, "orientation": "landscape"},
        "delivery_frame": {"width": 1920, "height": 1080, "fps": 24, "orientation": "landscape"},
        "subjects": [
            {"subject_id": "CHAR-01", "kind": "character", "purpose": "host",
             "reference_required": True, "definition": {"identity": "host"}},
            {"subject_id": "CHAR-02", "kind": "character", "purpose": "guest",
             "reference_required": True, "definition": {"identity": "guest"}},
        ],
    })


def sheet_meta(input_contract: dict, prompt: str) -> dict:
    policy = {
        "purpose": "identity and production reference",
        "background": "light neutral reference-board background",
        "consistency": "one unchanged identity and design system",
        "layout_logic": "canonical nine-panel editorial grid",
        "labeling_policy": "short canonical headings only",
        "proof_goal": "prove identity, construction, materials, scale, and alternate views",
    }
    panels = [{
        "panel_id": panel_id,
        "purpose": f"production proof for {panel_id}",
        "must_show": [f"complete canonical {panel_id} content"],
    } for panel_id in input_contract["required_panel_ids"]]
    meta = {
        "schema_version": "reference-board-meta-prompt.v2",
        "input_contract": input_contract,
        "sheet_policy": policy,
        "panel_plan": panels,
        "image_prompt": prompt,
        "image_prompt_sha256": text_sha256(prompt),
    }
    meta["meta_prompt_sha256"] = stage02_meta_prompt_sha256(meta)
    return meta


def scenario(with_camera: bool = False) -> dict:
    scene = {
        "scene_id": "SC-01",
        "intent": "reveal trust",
        "role": "relationship turn",
        "pov_owner": "CHAR-01",
        "dramatic_question": "will the guest agree",
        "entry_state": "uncertain",
        "exit_state": "agreement",
        "estimated_edit_range_seconds": [4, 7],
        "events": [{
            "event_id": "EV-001",
            "action": "host offers a newly invented key",
            "actor_subject_id": "CHAR-01",
            "target_subject_id": "NEW-KEY-01",
            "visible_change": "key moves into view",
            "result_state": "guest acknowledges it",
        }],
        "production_requirements": [{
            "requirement_id": "NEW-KEY-01",
            "name": "signature key",
            "asset_class": "prop",
            "description": "distinctive metal key",
            "reference_policy": "new_sheet",
        }],
    }
    if with_camera:
        scene["camera"] = "dolly"
    return envelope("03-scenario", {
        "sequences": [{"sequence_id": "SEQ-01", "scenes": [scene]}],
        "reference_debt_summary": ["NEW-KEY-01"],
    })


class IntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.attempt = Path(self.temp.name) / "attempt"
        self.attempt.mkdir()
        self.write_output("01-premise", premise())

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_output(self, stage_id: str, payload: dict) -> None:
        path = self.attempt / stage_id / "output/stage-artifact.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def image(self, relative: str, size: tuple[int, int]) -> str:
        path = self.attempt / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", size, "white").save(path)
        return relative

    def stage02_board(self, subject_id: str, prompt: str | None = None,
                      *, actual_size: tuple[int, int] = (1672, 941),
                      requested: list[int] | None = None) -> dict:
        prompt = prompt or f"complete canonical nine-panel board for {subject_id}"
        contract = next(
            item for item in stage02_authoring_inputs(self.attempt)["boards"]
            if item["subject_id"] == subject_id
        )
        path = self.image(f"02-sheet/qa/attempts/A01/{subject_id}.png", actual_size)
        return {
            "board_id": f"BOARD-{subject_id}",
            "subject_id": subject_id,
            "structured_meta_prompt": sheet_meta(contract, prompt),
            "requested": requested or [1672, 941],
            "selected_image": path,
            "selected_attempt": 1,
            "attempts": [{
                "attempt": 1,
                "variation_strategy": "base_contract_execution",
                "prompt": prompt,
                "candidate_path": path,
                "decision": "pass",
                "review": {"decision": "pass", "evidence": "all nine panels and identity visible"},
            }],
        }

    def motion_prompt_content(self) -> dict:
        self.write_output("03-scenario", scenario())
        self.write_output("04-shot-design", envelope("04-shot-design", {
            "scene_plans": [{
                "scene_id": "SC-01",
                "setups": [{
                    "setup_id": "SU-01",
                    "shots": [{
                        "shot_id": "SH-001",
                        "event_ids": ["EV-001"],
                        "included_in_timeline": True,
                    }],
                }],
            }],
        }))
        reference = self.image("02-sheet/qa/attempts/A01/host.png", (100, 60))
        plate = self.image("05-plate/qa/attempts/A01/plate.png", (100, 60))
        self.write_output("05-plate", envelope("05-plate", {
            "references": [{
                "reference_id": "REF-CHAR-01",
                "selected_image": reference,
            }],
            "plates": [{
                "shot_id": "SH-001",
                "selected_image": plate,
                "reference_ids": ["REF-CHAR-01"],
            }],
        }))
        return {
            "shots": [{
                "shot_id": "SH-001",
                "scenario_context": {
                    "scene_id": "SC-01",
                    "event_ids": ["EV-001"],
                    "dramatic_function": "make the trust offer readable",
                    "entry_to_exit_change": "uncertainty becomes agreement",
                },
                "shot_intent": "show one complete key handoff",
                "start_plate": plate,
                "start_plate_sha256": file_sha256(self.attempt / plate),
                "reference_bindings": [{
                    "reference_id": "REF-CHAR-01",
                    "path": reference,
                    "sha256": file_sha256(self.attempt / reference),
                }],
                "plate_observation": {
                    "visible_start_state": "host holds the key before offering it",
                    "spatial_relations": "host is left and guest is right",
                    "contact_and_occupancy": "host hand holds the only key",
                    "composition_and_motion_affordances": "the center space is open for the handoff",
                },
                "realization_status": "ready",
                "adaptation_reason": "no adaptation; the pose already supports the event",
                "motion_realization": {
                    "opening_transition": "the host hand starts from the visible held-key pose",
                    "ordered_action_phases": [{
                        "phase": "offer", "action": "host extends the key",
                        "visible_result": "key reaches the shared center",
                    }],
                    "performance_direction": "the host moves deliberately and the guest acknowledges",
                    "world_response": "the room remains stable",
                    "camera_execution": "camera remains locked",
                    "shooting_technique_translation": "continuous two-shot preserves both reactions",
                    "temporal_execution": "subject, world, and camera remain in real time",
                    "ending_state": "guest accepts the offered key",
                },
                "continuity_constraints": ["preserve identities, one key, and stable lighting"],
                "generator_translation": "one ordered image-to-video action from the exact first frame",
                "final_c01_prompt": "From the approved still, the host offers the key once as the locked camera holds both reactions.",
                "refinement_rationale": "the action begins from the visible occupied hand and open center",
            }],
        }

    def test_stage01_orientation_is_derived_from_dimensions(self) -> None:
        artifact = premise()
        artifact["content"]["frame"]["orientation"] = "portrait"
        report = validate_artifact(self.attempt, "01-premise", artifact)
        self.assertIn("orientation", {item["code"] for item in report["problems"]})

    def test_stage02_accepts_minor_pixel_variance_as_warning(self) -> None:
        boards = [self.stage02_board(subject, actual_size=(1668, 941))
                  for subject in ("CHAR-01", "CHAR-02")]
        report = validate_artifact(self.attempt, "02-sheet", envelope("02-sheet", {
            "boards": boards,
            "cross_board_review": {"decision": "pass", "evidence": "both identities consistent"},
        }))
        self.assertTrue(report["form_ok"], report["problems"])
        self.assertEqual({item["code"] for item in report["warnings"]}, {"minor-pixel-variance"})

    def test_stage02_rejects_retry_without_prior_failure(self) -> None:
        path2 = self.image("02-sheet/qa/attempts/A01/two.png", (1672, 941))
        board = self.stage02_board("CHAR-01", "one")
        board["selected_image"] = path2
        board["selected_attempt"] = 2
        board["attempts"].append({
            "attempt": 2, "variation_strategy": "retry", "prompt": "two",
            "candidate_path": path2, "decision": "pass",
            "review": {"decision": "pass", "evidence": "passed"},
        })
        # Add the other required subject so this assertion isolates retry policy.
        other = self.stage02_board("CHAR-02", "other")
        report = validate_artifact(self.attempt, "02-sheet", envelope("02-sheet", {
            "boards": [board, other],
            "cross_board_review": {"decision": "pass", "evidence": "both identities consistent"},
        }))
        self.assertIn("retry-without-failure", {item["code"] for item in report["problems"]})

    def test_stage02_landscape_sheet_is_independent_of_portrait_video(self) -> None:
        artifact = premise()
        artifact["content"]["frame"] = {
            "width": 768, "height": 1344, "fps": 24, "orientation": "portrait",
        }
        artifact["content"]["delivery_frame"] = {
            "width": 1080, "height": 1920, "fps": 24, "orientation": "portrait",
        }
        self.write_output("01-premise", artifact)
        boards = [self.stage02_board(subject) for subject in ("CHAR-01", "CHAR-02")]
        report = validate_artifact(self.attempt, "02-sheet", envelope("02-sheet", {
            "boards": boards,
            "cross_board_review": {"decision": "pass", "evidence": "landscape boards complete"},
        }))
        self.assertTrue(report["form_ok"], report["problems"])

    def test_stage02_rejects_video_ratio_as_sheet_canvas(self) -> None:
        boards = [self.stage02_board(subject) for subject in ("CHAR-01", "CHAR-02")]
        boards[0] = self.stage02_board(
            "CHAR-01", actual_size=(941, 1672), requested=[941, 1672],
        )
        report = validate_artifact(self.attempt, "02-sheet", envelope("02-sheet", {
            "boards": boards,
            "cross_board_review": {"decision": "pass", "evidence": "reviewed"},
        }))
        self.assertIn("sheet-canvas", {item["code"] for item in report["problems"]})

    def test_stage02_rejects_three_panel_simplification(self) -> None:
        boards = [self.stage02_board(subject) for subject in ("CHAR-01", "CHAR-02")]
        meta = boards[0]["structured_meta_prompt"]
        meta["panel_plan"] = meta["panel_plan"][:3]
        meta["meta_prompt_sha256"] = stage02_meta_prompt_sha256(meta)
        report = validate_artifact(self.attempt, "02-sheet", envelope("02-sheet", {
            "boards": boards,
            "cross_board_review": {"decision": "pass", "evidence": "reviewed"},
        }))
        self.assertIn("sheet-panel-contract", {item["code"] for item in report["problems"]})

    def test_stage02_rejects_reconstructed_source_definition(self) -> None:
        boards = [self.stage02_board(subject) for subject in ("CHAR-01", "CHAR-02")]
        meta = boards[0]["structured_meta_prompt"]
        meta["input_contract"]["source_definition"] = {"identity": "summarized host"}
        meta["meta_prompt_sha256"] = stage02_meta_prompt_sha256(meta)
        report = validate_artifact(self.attempt, "02-sheet", envelope("02-sheet", {
            "boards": boards,
            "cross_board_review": {"decision": "pass", "evidence": "reviewed"},
        }))
        self.assertIn("meta-input-drift", {item["code"] for item in report["problems"]})

    def test_stage02_a01_must_use_bound_image_prompt_verbatim(self) -> None:
        boards = [self.stage02_board(subject) for subject in ("CHAR-01", "CHAR-02")]
        boards[0]["attempts"][0]["prompt"] = "improvised flat prompt"
        report = validate_artifact(self.attempt, "02-sheet", envelope("02-sheet", {
            "boards": boards,
            "cross_board_review": {"decision": "pass", "evidence": "reviewed"},
        }))
        self.assertIn("prompt-binding", {item["code"] for item in report["problems"]})

    def test_stage03_allows_new_reference_debt_but_rejects_camera(self) -> None:
        good = validate_artifact(self.attempt, "03-scenario", scenario())
        self.assertTrue(good["form_ok"], good["problems"])
        bad = validate_artifact(self.attempt, "03-scenario", scenario(with_camera=True))
        self.assertIn("premature-shot-design", {item["code"] for item in bad["problems"]})

    def test_stage04_rejects_single_label_for_two_visible_people(self) -> None:
        self.write_output("03-scenario", scenario())
        artifact = envelope("04-shot-design", {
            "scene_plans": [{
                "scene_id": "SC-01",
                "treatment": {"intent": "reveal trust", "pov": "host", "blocking": "face to face",
                              "coverage_logic": "show relationship and key"},
                "setups": [{
                    "setup_id": "SU-01", "lighting_continuity": "stable window light",
                    "shots": [{
                        "shot_id": "SH-001", "event_ids": ["EV-001"], "purpose": "relationship turn",
                        "composition": "single", "frame_size": "MS",
                        "visible_cast_ids": ["CHAR-01", "CHAR-02"],
                        "required_reference_subject_ids": ["CHAR-01", "CHAR-02", "NEW-KEY-01"],
                        "camera": {"movement": "locked", "speed": "none", "framing": "both people",
                                   "end": "hold", "angle": "eye level", "rationale": "observe choice"},
                        "performance": {"phases": [{"phase": "offer", "action": "offers key"}]},
                        "timing": {"edit_target_seconds": 5, "temporal_mode": "real_time",
                                   "dramatic_reason": "allow response", "execution_method": "continuous take",
                                   "time_domains": {"subject": "real time", "world": "real time", "camera": "real time"}},
                        "included_in_timeline": True,
                    }],
                }],
            }],
        })
        report = validate_artifact(self.attempt, "04-shot-design", artifact)
        self.assertIn("cast-composition", {item["code"] for item in report["problems"]})

    def test_stage055_accepts_plate_grounded_prompt_refinement(self) -> None:
        content = self.motion_prompt_content()
        report = validate_artifact(
            self.attempt, "05.5-motion-prompt", envelope("05.5-motion-prompt", content)
        )
        self.assertTrue(report["form_ok"], report["problems"])

    def test_stage055_cannot_return_the_plate_for_regeneration(self) -> None:
        content = self.motion_prompt_content()
        content["shots"][0]["realization_status"] = "blocked"
        report = validate_artifact(
            self.attempt, "05.5-motion-prompt", envelope("05.5-motion-prompt", content)
        )
        self.assertIn("realization-status", {item["code"] for item in report["problems"]})

    def test_stage06_c01_must_use_stage055_prompt_verbatim(self) -> None:
        content = self.motion_prompt_content()
        self.write_output(
            "05.5-motion-prompt", envelope("05.5-motion-prompt", content)
        )
        video = self.attempt / "06-motion/qa/attempts/A01/media/SH-001/C01.mp4"
        video.parent.mkdir(parents=True, exist_ok=True)
        video.write_bytes(b"test video")
        artifact = envelope("06-motion", {
            "shots": [{
                "shot_id": "SH-001",
                "start_plate": content["shots"][0]["start_plate"],
                "selected_candidate": "C01",
                "candidates": [{
                    "candidate_id": "C01",
                    "variation_strategy": "base_contract_execution",
                    "prompt": "silently rewritten C01 prompt",
                    "video_path": str(video.relative_to(self.attempt)),
                    "review": {"decision": "pass", "evidence": "test evidence"},
                }],
            }],
        })
        report = validate_artifact(self.attempt, "06-motion", artifact)
        self.assertIn("c01-prompt-drift", {item["code"] for item in report["problems"]})


if __name__ == "__main__":
    unittest.main()
