from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image

from ai_video_pipeline.v3.integrity import (
    file_sha256,
    stage02_authoring_inputs,
    stage02_meta_prompt_sha256,
    text_sha256,
)
from ai_video_pipeline.v3.orchestrator import initialize, load_state, review, submit, work_order
from ai_video_pipeline.v3.specs import CRITIC_CRITERIA


def now(offset: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=offset)).isoformat()


class EndToEndFastTrackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.attempt = Path(self.temp.name) / "full-v3"
        self.direction = "5-second landscape two-person key exchange"
        initialize(self.attempt, self.direction, mode="fast_track", by="user",
                   reason="end-to-end autonomous test")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def media(self, relative: str, *, image: bool = False,
              image_size: tuple[int, int] = (100, 60)) -> str:
        path = self.attempt / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if image:
            Image.new("RGB", image_size, "gray").save(path)
        else:
            path.write_bytes(b"test-media")
        return relative

    def artifact(self, order: dict, content: dict) -> dict:
        return {
            "schema_version": "llm-stage-artifact.v1",
            "pipeline_version": "3.0",
            "stage_id": order["stage_id"],
            "attempt_id": order["attempt_id"],
            "authored_by": "end-to-end test author",
            "authored_at": now(),
            "input_receipts": order["input_receipts"],
            "creative_decisions": [{"decision": "fixture", "reason": "exercise contract"}],
            "content": content,
        }

    def pass_critique(self, order: dict, artifact_hash: str) -> dict:
        return {
            "schema_version": "llm-stage-critique.v1",
            "stage_id": order["stage_id"],
            "artifact_sha256": artifact_hash,
            "reviewer": "fresh-context test critic",
            "reviewed_at": now(),
            "summary": "all declared criteria have concrete test evidence",
            "decision": "pass",
            "criteria": [
                {"criterion_id": criterion_id, "status": "pass", "evidence": "fixture-specific evidence"}
                for criterion_id, _ in CRITIC_CRITERIA[order["stage_id"]]
            ],
            "failure_classes": [],
            "accepted_defects": [],
        }

    def run_stage(self, content: dict) -> dict:
        order = work_order(self.attempt)
        artifact_path = self.attempt / order["artifact_path"]
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(json.dumps(self.artifact(order, content), ensure_ascii=False), encoding="utf-8")
        submitted = submit(self.attempt)
        self.assertEqual(submitted["status"], "critic_required", submitted)
        critique_path = self.attempt / order["critique_path"]
        critique_path.write_text(json.dumps(self.pass_critique(order, submitted["artifact_sha256"])), encoding="utf-8")
        return review(self.attempt)

    def test_fast_track_can_seal_all_nine_stage_contracts(self) -> None:
        self.run_stage({
            "direction": {"verbatim": self.direction, "interpretation": "relationship beat"},
            "runtime_contract": {"mode": "fixed", "target_seconds": 5, "reason": "test format"},
            "frame": {"width": 100, "height": 60, "fps": 24, "orientation": "landscape"},
            "delivery_frame": {"width": 200, "height": 120, "fps": 24, "orientation": "landscape"},
            "subjects": [
                {"subject_id": "CHAR-01", "kind": "character", "purpose": "host",
                 "reference_required": True, "definition": {"identity": "host"}},
                {"subject_id": "CHAR-02", "kind": "character", "purpose": "guest",
                 "reference_required": True, "definition": {"identity": "guest"}},
            ],
        })

        board_paths = {}
        boards = []
        bound_inputs = {
            item["subject_id"]: item
            for item in stage02_authoring_inputs(self.attempt)["boards"]
        }
        for subject in ("CHAR-01", "CHAR-02"):
            path = self.media(
                f"02-sheet/qa/attempts/A01/media/{subject}.png",
                image=True,
                image_size=(1672, 941),
            )
            board_paths[subject] = path
            prompt = f"complete canonical nine-panel identity board for {subject}"
            meta = {
                "schema_version": "reference-board-meta-prompt.v2",
                "input_contract": bound_inputs[subject],
                "sheet_policy": {
                    "purpose": "identity proof",
                    "background": "light neutral studio",
                    "consistency": "one unchanged identity",
                    "layout_logic": "canonical nine-panel grid",
                    "labeling_policy": "short canonical headings",
                    "proof_goal": "identity, construction, material, and alternate views",
                },
                "panel_plan": [{
                    "panel_id": panel_id,
                    "purpose": f"proof for {panel_id}",
                    "must_show": [f"complete {panel_id} content"],
                } for panel_id in bound_inputs[subject]["required_panel_ids"]],
                "image_prompt": prompt,
                "image_prompt_sha256": text_sha256(prompt),
            }
            meta["meta_prompt_sha256"] = stage02_meta_prompt_sha256(meta)
            boards.append({
                "board_id": f"BOARD-{subject}", "subject_id": subject,
                "structured_meta_prompt": meta,
                "requested": [1672, 941], "selected_image": path, "selected_attempt": 1,
                "attempts": [{
                    "attempt": 1, "variation_strategy": "base_contract_execution",
                    "prompt": prompt, "candidate_path": path,
                    "decision": "pass", "review": {"decision": "pass", "evidence": "all nine panels and identity visible"},
                }],
            })
        self.run_stage({"boards": boards, "cross_board_review": {"decision": "pass", "evidence": "consistent"}})

        self.run_stage({
            "sequences": [{
                "sequence_id": "SEQ-01", "intent": "trust changes",
                "scenes": [{
                    "scene_id": "SC-01", "slugline": "INT. ROOM — DAY", "intent": "offer trust",
                    "role": "relationship turn", "pov_owner": "CHAR-01",
                    "dramatic_question": "will the guest accept", "entry_state": "uncertain",
                    "exit_state": "agreement", "estimated_edit_range_seconds": [4, 7],
                    "density_reasoning": "one readable exchange",
                    "events": [{
                        "event_id": "EV-001", "action": "host offers the key",
                        "actor_subject_id": "CHAR-01", "target_subject_id": "NEW-KEY-01",
                        "visible_change": "key enters shared space", "result_state": "guest accepts",
                    }],
                    "production_requirements": [{
                        "requirement_id": "NEW-KEY-01", "name": "key", "asset_class": "prop",
                        "description": "distinctive metal key", "reference_policy": "new_sheet",
                    }],
                }],
            }],
            "reference_debt_summary": ["NEW-KEY-01"],
        })

        self.run_stage({
            "scene_plans": [{
                "scene_id": "SC-01",
                "treatment": {"intent": "offer trust", "pov": "host", "blocking": "face to face",
                              "coverage_logic": "hold both people and key in relation"},
                "setups": [{
                    "setup_id": "SU-01", "camera_position": "across table",
                    "lighting_continuity": "stable window light",
                    "shots": [{
                        "shot_id": "SH-001", "event_ids": ["EV-001"], "purpose": "complete exchange",
                        "composition": "two_shot", "frame_size": "MS",
                        "visible_cast_ids": ["CHAR-01", "CHAR-02"],
                        "required_reference_subject_ids": ["CHAR-01", "CHAR-02", "NEW-KEY-01"],
                        "start_state": "host holds key before extending it",
                        "action_contract": "host offers; guest accepts", "end_state": "guest holds key",
                        "camera": {"movement": "locked", "speed": "none", "framing": "balanced two-shot",
                                   "end": "hold on agreement", "angle": "eye level",
                                   "lens_behavior": "natural perspective", "rationale": "preserve relationship"},
                        "performance": {"phases": [{"phase": "offer", "action": "extend key"},
                                                    {"phase": "accept", "action": "take key"}]},
                        "timing": {"edit_target_seconds": 5, "temporal_mode": "real_time",
                                   "dramatic_reason": "read both reactions", "execution_method": "continuous take",
                                   "time_domains": {"subject": "real time", "world": "real time", "camera": "real time"}},
                        "included_in_timeline": True,
                    }],
                }],
            }],
            "timeline_total_seconds": 5,
        })

        key_ref = self.media("05-plate/qa/attempts/A01/media/references/key.png", image=True)
        plate = self.media("05-plate/qa/attempts/A01/media/plates/SH-001.png", image=True)
        references = []
        for subject in ("CHAR-01", "CHAR-02"):
            references.append({
                "reference_id": f"REF-{subject}", "subject_or_requirement_id": subject,
                "origin": "stage02", "purpose": "identity", "requested": [1672, 941],
                "selected_image": board_paths[subject],
                "review": {"decision": "pass", "evidence": "current identity review"},
            })
        references.append({
            "reference_id": "REF-NEW-KEY-01", "subject_or_requirement_id": "NEW-KEY-01",
            "origin": "stage05", "purpose": "prop identity", "requested": [100, 60],
            "selected_image": key_ref, "selected_attempt": 1,
            "attempts": [{
                "attempt": 1, "variation_strategy": "base_contract_execution", "prompt": "key reference",
                "candidate_path": key_ref, "decision": "pass",
                "review": {"decision": "pass", "evidence": "key geometry visible"},
            }],
            "review": {"decision": "pass", "evidence": "usable key reference"},
        })
        self.run_stage({
            "references": references,
            "global_reference_preflight": {
                "reference_ids": ["REF-CHAR-01", "REF-CHAR-02", "REF-NEW-KEY-01"],
                "decision": "pass", "evidence": "all three references agree",
            },
            "references_completed_at": now(), "plates_started_at": now(1),
            "plates": [{
                "shot_id": "SH-001", "role": "start", "end_plate": None,
                "reference_ids": ["REF-CHAR-01", "REF-CHAR-02", "REF-NEW-KEY-01"],
                "requested": [100, 60], "selected_image": plate, "selected_attempt": 1,
                "attempts": [{
                    "attempt": 1, "variation_strategy": "base_contract_execution", "prompt": "start two-shot",
                    "candidate_path": plate, "decision": "pass",
                    "review": {"decision": "pass", "evidence": "both people and key match references"},
                }],
            }],
        })

        c01_prompt = (
            "From the approved two-shot, the host extends the key once and the guest accepts it; "
            "both reactions remain visible while the camera stays locked and holds on agreement."
        )
        self.run_stage({
            "shots": [{
                "shot_id": "SH-001",
                "scenario_context": {
                    "scene_id": "SC-01", "event_ids": ["EV-001"],
                    "dramatic_function": "make the trust exchange readable",
                    "entry_to_exit_change": "uncertainty becomes agreement",
                },
                "shot_intent": "complete the key exchange in one relationship two-shot",
                "start_plate": plate,
                "start_plate_sha256": file_sha256(self.attempt / plate),
                "reference_bindings": [{
                    "reference_id": reference["reference_id"],
                    "path": reference["selected_image"],
                    "sha256": file_sha256(self.attempt / reference["selected_image"]),
                } for reference in references],
                "plate_observation": {
                    "visible_start_state": "host holds the key before the seated guest",
                    "spatial_relations": "host and guest share a balanced left-right two-shot",
                    "contact_and_occupancy": "the host hand occupies the key; guest hands are free",
                    "composition_and_motion_affordances": "the center gap permits one clear handoff",
                },
                "realization_status": "ready",
                "adaptation_reason": "no adaptation; the approved plate already supports the handoff",
                "motion_realization": {
                    "opening_transition": "the host hand begins moving from the exact held-key pose",
                    "ordered_action_phases": [
                        {"phase": "offer", "action": "host extends the key",
                         "visible_result": "key enters shared center space"},
                        {"phase": "accept", "action": "guest takes the key",
                         "visible_result": "guest finishes holding the key"},
                    ],
                    "performance_direction": "uncertainty softens into mutual acknowledgment",
                    "world_response": "room and window light remain stable",
                    "camera_execution": "camera remains locked in the balanced two-shot",
                    "shooting_technique_translation": "continuous locked coverage preserves both reactions",
                    "temporal_execution": "subject, world, and camera remain in real time",
                    "ending_state": "guest holds the key while both register agreement",
                },
                "continuity_constraints": ["preserve both identities, one key, and stable room lighting"],
                "generator_translation": "one ordered image-to-video action with a locked camera",
                "final_c01_prompt": c01_prompt,
                "refinement_rationale": "the prompt begins at the visible hand occupancy and uses the open center",
            }],
        })

        motion = self.media("06-motion/qa/attempts/A01/media/SH-001/C01.mp4")
        self.run_stage({
            "shots": [{
                "shot_id": "SH-001", "start_plate": plate, "selected_candidate": "C01",
                "candidates": [{
                    "candidate_id": "C01", "variation_strategy": "base_contract_execution",
                    "prompt": c01_prompt, "video_path": motion,
                    "review": {"decision": "pass", "evidence": "single ordered exchange and continuity"},
                }],
            }],
            "cross_shot_review": {"decision": "pass", "evidence": "one coherent shot"},
        })

        master = self.media("07-edit/output/master.mp4")
        self.run_stage({
            "timeline": [{
                "shot_id": "SH-001", "source_video": motion, "source_in_seconds": 0,
                "source_out_seconds": 5, "edit_seconds": 5, "playback_rate": 1,
                "editorial_reason": "hold complete exchange", "transition": {"type": "cut"},
                "sound_intent": "room tone",
            }],
            "output_video": master,
            "master_review": {"decision": "pass", "evidence": "runtime and continuity pass"},
        })

        receipts = []
        for stage_id in ("01-premise", "02-sheet", "03-scenario", "04-shot-design",
                         "05-plate", "05.5-motion-prompt", "06-motion", "07-edit"):
            path = self.attempt / stage_id / "receipt.json"
            receipts.append({"stage_id": stage_id, "path": f"{stage_id}/receipt.json",
                             "sha256": file_sha256(path)})
        result = self.run_stage({
            "stage_receipts": receipts,
            "master_video": master,
            "review_dimensions": [{"dimension": "contract_fidelity", "decision": "pass", "evidence": "pass"}],
            "defects": [],
            "release_decision": {"release_eligible": True, "reason": "internal QA passed",
                                 "external_publish_authorized": False, "human_release_receipt": None},
        })
        self.assertEqual(result["status"], "complete")
        self.assertEqual(load_state(self.attempt)["status"], "complete")


if __name__ == "__main__":
    unittest.main()
