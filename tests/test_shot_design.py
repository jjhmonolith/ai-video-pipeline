import json
import shutil
import tempfile
import unittest
from pathlib import Path

from ai_video_pipeline.contract import Contract
from ai_video_pipeline.execution_mode import set_execution_mode
from ai_video_pipeline.h3_runtime import PROFILE_ID
from ai_video_pipeline.shot_compiler import compile_plate_chain, compile_shot_pack
from ai_video_pipeline.shot_design import (
    _camera,
    _lighting_contract,
    _motion_complexity,
    _split_beat,
    _compile_temporal,
    _reference_fulfillment_plan,
    check,
    compile_scenario,
    gather,
    run,
)
from ai_video_pipeline.stage4_experiment import METHODS


ROOT = Path(__file__).resolve().parents[1]
ATTEMPTS = [
    ROOT / "runs/sky-village-plumber/attempts/v1-pilot",
    ROOT / "runs/luxury-penthouse-tour/attempts/v1-pilot",
]
CAR_ATTEMPT = ROOT / "runs/fictional-ferrari-track-review/attempts/v1-pilot"


class ShotDesignCompilerTests(unittest.TestCase):
    def _compile(self, attempt: Path) -> tuple[Contract, dict, dict]:
        contract = Contract.load(attempt)
        source = gather(attempt, contract)
        return contract, source, compile_scenario(attempt, contract, source)

    def test_both_regression_topics_compile_to_h3_only_and_conserve_time(self):
        for attempt in ATTEMPTS:
            contract, source, design = self._compile(attempt)
            self.assertEqual(design["engine_policy"]["video_engine"], PROFILE_ID)
            self.assertFalse(design["engine_policy"]["other_video_engines_allowed"])
            self.assertAlmostEqual(design["total_edit_seconds"],
                                   float(contract.get("duration_seconds")))
            self.assertEqual(design["source_scenario_sha256"],
                             compile_scenario(attempt, contract, source)["source_scenario_sha256"])
            report = check(design, contract, source["scenario"])
            self.assertTrue(report["form_ok"], report["problems"])
            self.assertFalse(
                design["human_gate"]["transition_to_stage05_requires_human_confirmation"])

    def test_successful_stage04_emits_immediate_stage05_handoff(self):
        with tempfile.TemporaryDirectory() as root:
            attempt = Path(root) / "attempt"
            shutil.copytree(ATTEMPTS[1], attempt)

            result = run(attempt, force=True)

            self.assertTrue(result["form_ok"])
            self.assertFalse(result["stage05_handoff"]["human_confirmation_required"])
            self.assertEqual(result["stage05_handoff"]["policy"],
                             "start_immediately_after_stage04_form_ok")

    def test_explicit_fast_track_changes_review_authority_without_changing_prompts(self):
        with tempfile.TemporaryDirectory() as root:
            attempt = Path(root) / "attempt"
            shutil.copytree(ATTEMPTS[1], attempt)
            set_execution_mode(attempt, "fast_track", by="user", reason="autonomous run")
            contract = Contract.load(attempt)
            source = gather(attempt, contract)
            design = compile_scenario(attempt, contract, source)

            self.assertEqual(design["execution_mode"]["mode"], "fast_track")
            self.assertFalse(design["human_gate"]["required"])
            self.assertTrue(design["human_gate"]["auto_approve_allowed"])
            self.assertEqual(design["human_gate"]["resolution_mode"], "ai_fast_track")
            self.assertTrue(check(design, contract, source["scenario"])["form_ok"])
            for shot in design["shots"]:
                self.assertFalse(shot["candidate_policy"]["human_required"])
                self.assertTrue(shot["candidate_policy"]["auto_promotion_allowed"])
                self.assertFalse(shot["plate_candidate_policy"]["human_final_review_required"])
                self.assertTrue(shot["plate_candidate_policy"]["auto_promotion_allowed"])

    def test_exact_motion_uses_first_only_separately_from_camera_policy(self):
        saw_transit = False
        saw_locked_precision = False
        for attempt in ATTEMPTS:
            _, _, design = self._compile(attempt)
            exact = [shot for shot in design["shots"]
                     if shot["motion_control"]["exact_motion_required"]]
            self.assertTrue(exact)
            for shot in exact:
                self.assertEqual(shot["h3_generation"]["route"], "i2v")
                self.assertEqual(shot["h3_generation"]["anchor_policy"], "first_only")
                self.assertFalse(shot["h3_generation"]["last_frame_allowed"])
                self.assertIsNotNone(shot["state_pair"]["end_state_id"])
                self.assertEqual(shot["state_pair"]["end_state_usage"], "qa_target_only")
                self.assertEqual(shot["candidate_policy"]["candidate_count"], 1)
                self.assertEqual(shot["candidate_policy"]["max_attempts"], 10)
                self.assertEqual(shot["candidate_policy"]["strategy"],
                                 "one_take_then_review_append_retry")
                self.assertEqual(shot["plate_candidate_policy"]["start_candidates"], 1)
                self.assertEqual(shot["plate_candidate_policy"]["strategy"],
                                 "sequential_ai_review")
                self.assertEqual(shot["plate_candidate_policy"]["max_attempts"], 10)
                self.assertTrue(shot["plate_candidate_policy"]["stop_on_ai_pass"])
                self.assertEqual(shot["plate_candidate_policy"]["exhaustion_policy"],
                                 "use_attempt_10_for_human_review")
                self.assertEqual(shot["plate_candidate_policy"]["end_edits_per_selected_start"], 0)
                self.assertEqual(shot["plate_candidate_policy"]["last_frame_policy"],
                                 "disabled_in_production")
                self.assertFalse(shot["plate_candidate_policy"]["auto_promotion_allowed"])
                self.assertEqual(shot["motion_control"]["guide_plan"], [{
                    "progress": 0.0,
                    "state_role": "start",
                    "h3_input": "first_frame",
                    "state_id": shot["state_pair"]["start_state_id"],
                }])
                direction = shot["motion_control"]["screen_direction_contract"]
                if direction["required"]:
                    saw_transit = True
                    self.assertEqual(shot["camera_policy"], "natural")
                    self.assertNotIn("camera viewpoint", shot["state_pair"]["invariants"])
                    self.assertIn("camera motion continuity", shot["state_pair"]["invariants"])
                else:
                    saw_locked_precision = True
                    self.assertEqual(shot["camera_policy"], "locked")
                    self.assertIn("camera viewpoint", shot["state_pair"]["invariants"])
        self.assertTrue(saw_transit)
        self.assertTrue(saw_locked_precision)

    def test_start_plate_is_explicitly_before_action_and_failure_returns_to_stage05(self):
        for attempt in ATTEMPTS:
            _, _, design = self._compile(attempt)
            for shot in design["shots"]:
                start = design["states"][shot["state_pair"]["start_state_id"]]
                self.assertIn("strictly before the action", start["prompt"])
                self.assertIn("Do not show contact, displacement, rotation", start["prompt"])
                self.assertIn("regenerate stage05", shot["plate_acceptance"]["on_fail"])
                self.assertIn("does not generate an end plate",
                              shot["plate_candidate_policy"]["pair_selection"])
                pack = compile_shot_pack([shot], {"runtime": PROFILE_ID})
                self.assertEqual(pack["shots"][0]["anchor_policy"], "first_only")
                self.assertIsNone(pack["shots"][0]["last_plate"])

    def test_compound_sentences_without_sub_beats_are_not_claimed_as_atomic(self):
        attempt = ATTEMPTS[1]
        contract, source, design = self._compile(attempt)
        report = check(design, contract, source["scenario"])
        warnings = [item for item in report["warnings"]
                    if item["code"] == "manual-atomic-segmentation-required"]
        self.assertTrue(warnings)
        self.assertTrue(any(not shot["atomicity"]["one_primary_action_per_shot"]
                            for shot in design["shots"]))

    def test_explicit_single_sub_beat_overrides_explanatory_prose_conjunctions(self):
        segments = _split_beat({
            "id": "B01",
            "seconds": 5,
            "what_happens": "배관은 고정된 채 손잡이만 돌고, 완료 위치에서 멈춘다.",
            "sub_beats": [{
                "id": "B01-a",
                "actor_subject_id": "actor",
                "action": "손잡이만 완료 위치까지 돌린다",
                "target_subject_id": "target",
                "target_part_id": "wheel",
                "result_state": "closed",
                "split_after": True,
            }],
        })
        self.assertEqual(len(segments), 1)
        self.assertEqual(
            segments[0]["_stage04_atomization"]["source"], "stage03_sub_beats"
        )
        self.assertFalse(
            segments[0]["_stage04_atomization"]["manual_segmentation_required"]
        )
        self.assertEqual(_motion_complexity(segments[0])[1], 1)

    def test_temporal_compiler_separates_edit_time_capture_time_and_capability_debt(self):
        compiled = _compile_temporal({
            "edit_target_seconds": 8, "tolerance_seconds": .5,
            "head_handle_seconds": .5, "tail_handle_seconds": .5,
            "temporal_mode": "slow_motion", "dramatic_reason": "extend recognition",
            "execution_method": "post_retime", "source_playback_rate": .5,
            "time_domains": {"subject": "half_speed", "world": "half_speed",
                             "camera": "real_time"},
        }, 24)
        self.assertEqual(compiled["edit_target_seconds"], 8)
        self.assertLess(compiled["requested_generation_seconds"], 8)
        self.assertEqual(compiled["edit_operation"], "trim_handles_then_retime")
        self.assertFalse(compiled["generation_blocked"])

        blocked = _compile_temporal({
            "edit_target_seconds": 4, "temporal_mode": "bullet_time_orbit",
            "execution_method": "model_native", "dramatic_reason": "inspect impact",
            "time_domains": {"subject": "frozen", "world": "frozen", "camera": "active"},
        }, 24)
        self.assertTrue(blocked["generation_blocked"])
        self.assertTrue(blocked["capability_debt"])

    def test_stage03_reference_debt_becomes_stage05_before_plate_work(self):
        plan = _reference_fulfillment_plan({"sequences": [{"id": "SQ01", "scenes": [{
            "id": "SC01", "production_requirements": [{
                "id": "NEW-prop", "name": "hero prop", "asset_class": "scene_only_hero_prop",
                "description": "a unique object", "reference_policy": "scene_reference",
            }, {
                "id": "NEW-dressing", "name": "background books",
                "asset_class": "background_dressing", "description": "soft background",
                "reference_policy": "prompt_only",
            }],
        }]}]})
        self.assertEqual(plan["generation_required_count"], 1)
        self.assertEqual(plan["phase_order"][0],
                         "5A_generate_and_validate_reference_debt")
        hero = next(item for item in plan["assets"] if item["id"] == "NEW-prop")
        self.assertTrue(hero["generation_required"])
        self.assertTrue(hero["image_generation_prompt"].startswith(
            "STRUCTURED PRODUCTION REFERENCE"))

    def test_stair_descent_is_transit_with_natural_camera(self):
        camera, policy, _, _ = _camera(
            {"what_happens": "인물이 나선 계단을 내려가 아래층에 도착한다."},
            exact=True,
        )
        self.assertEqual(policy, "natural")
        self.assertEqual(camera["movement"], "팔로우 샷")

    def test_crossing_entry_threshold_is_transit_with_natural_camera(self):
        camera, policy, _, _ = _camera(
            {
                "what_happens": (
                    "민채가 열린 전용 엘리베이터 문턱을 넘어 "
                    "도착 갤러리 안으로 두 걸음 들어와 멈춘다."
                )
            },
            exact=True,
        )
        self.assertEqual(policy, "natural")
        self.assertEqual(camera["movement"], "팔로우 샷")

    def test_camera_framing_does_not_hardcode_portrait_orientation(self):
        camera, _, _, _ = _camera(
            {"what_happens": "카드가 화면 중앙에 나타난다."},
            exact=True,
        )
        self.assertIn("화면 안", camera["framing"])
        self.assertNotIn("세로 프레임", camera["framing"])

    def test_penthouse_lighting_does_not_leak_vehicle_terms(self):
        lighting = _lighting_contract({"penthouse": {
            "kind": "setting",
            "concept": "a two-level urban residence",
            "architecture": {"salon": "double-height interior"},
            "lighting": "blue-hour ambience with warm concealed practicals",
        }}, "penthouse", {"what_happens": "The host lowers one hand."})
        prompt = json.dumps(lighting)
        self.assertEqual(lighting["space"], "interior")
        self.assertNotIn("tyre", prompt)
        self.assertNotIn("underbody", prompt)
        self.assertNotIn("red paint", prompt)
        self.assertIn("architectural contact shadows", prompt)

    def test_explicit_camera_pullback_overrides_exact_state_lock(self):
        camera, policy, size, _ = _camera(
            {"what_happens": "카메라가 위와 뒤로 빠지며 전체 포트폴리오 맵이 드러난다."},
            exact=True,
        )
        self.assertEqual(policy, "directed")
        self.assertEqual(camera["movement"], "드론 풀백")
        self.assertEqual(size, "롱샷")

    def test_reference_geometry_and_screen_direction_are_explicit_gates(self):
        _, _, plumber = self._compile(ATTEMPTS[0])
        plumber_cards = [shot for shot in plumber["shots"] if shot["beat_id"] == "B07"]
        locks = " ".join(lock for shot in plumber_cards
                         for lock in shot["state_pair"]["geometry_locks"])
        self.assertIn("valve wheel center", locks)
        self.assertIn("declared object 'toolkit'", locks)
        self.assertTrue(any(
            lock["subject_id"] == "toolkit" and "contents" in lock["locked_fields"]
            for shot in plumber_cards for lock in shot["state_pair"]["reference_locks"]
        ))

        contract, source, penthouse = self._compile(ATTEMPTS[1])
        transit = next(shot for shot in penthouse["shots"] if shot["beat_id"] == "B02")
        direction = transit["motion_control"]["screen_direction_contract"]
        self.assertTrue(direction["required"])
        self.assertTrue(direction["generation_blocked_until_resolved"])
        self.assertIsNone(direction["screen_direction_vector"])
        report = check(penthouse, contract, source["scenario"])
        self.assertTrue(any(item["code"] == "screen-direction-annotation-required"
                            for item in report["warnings"]))
        pack = compile_shot_pack([transit], {"runtime": PROFILE_ID})
        self.assertTrue(pack["shots"][0]["generation_blocked"])

    def test_frame_object_and_cast_prompts_are_compiled_from_contract_data(self):
        contract, source, design = self._compile(CAR_ATTEMPT)
        frame_marker = "Landscape production plate (1344x768 native frame)"
        forbidden = ("Vertical production plate", "tool bag silhouette",
                     "zipper and pockets", "every visible tool")

        self.assertGreaterEqual(len(design["states"]), 14)
        for state in design["states"].values():
            self.assertIn(frame_marker, state["prompt"])
            self.assertFalse(any(term in state["prompt"] for term in forbidden))
        for shot in design["shots"]:
            self.assertFalse(any(term in shot["motion_prompt"] for term in forbidden))
            self.assertIn("declared object 'ferrari-fulgore'",
                          " ".join(shot["state_pair"]["geometry_locks"]))

        for beat_id in ("B05", "B06", "B07"):
            shot = next(
                item for item in design["shots"]
                if item["beat_id"] == beat_id and len(item["cast_presence"]) == 2
            )
            self.assertEqual(shot["composition"], "투샷")
            self.assertIn("투샷", shot["camera"]["framing"])
            self.assertIn("Exactly one adult professional driver occupies the left driving seat",
                          shot["motion_prompt"])
            self.assertNotIn("No driver, crew member or other person is visible",
                             shot["motion_prompt"])

        report = check(design, contract, source["scenario"])
        leak_codes = {"cast-composition", "topic-specific-lock-leak",
                      "plate-frame-contract", "conditional-clause-branch"}
        self.assertFalse(any(item["code"] in leak_codes for item in report["problems"]),
                         report["problems"])

    def test_semantic_gate_rejects_the_three_legacy_compiler_leaks(self):
        contract, source, design = self._compile(CAR_ATTEMPT)
        shot = next(item for item in design["shots"] if len(item["cast_presence"]) == 2)
        shot["composition"] = "싱글"
        shot["state_pair"]["geometry_locks"].append(
            "tool bag silhouette, opening, zipper and pockets stay fixed"
        )
        state = design["states"][shot["state_pair"]["start_state_id"]]
        state["prompt"] = state["prompt"].replace(
            "Landscape production plate (1344x768 native frame)",
            "Vertical production plate",
        )
        report = check(design, contract, source["scenario"])
        codes = {item["code"] for item in report["problems"]}
        self.assertTrue({"cast-composition", "topic-specific-lock-leak",
                         "plate-frame-contract"}.issubset(codes))

    def test_interaction_geometry_blocks_impossible_tool_contact(self):
        contract, source, design = self._compile(ATTEMPTS[0])
        shot = next(item for item in design["shots"] if item["beat_id"] == "B07")
        shot["interaction_contracts"] = [{
            "fit_contract": {
                "tool_capacity_part_id": "pipe-wrench.jaws",
                "target_extent_part_id": "coupling-01.outer-diameter",
                "tool_capacity_mm": 50,
                "target_extent_mm": 60,
                "minimum_capacity_ratio": 1.15,
            },
            "axis_contract": {
                "tool_action_plane_part_id": "pipe-wrench.jaw-plane",
                "target_axis_part_id": "coupling-01.axis",
                "relation": "perpendicular",
                "target_angle_deg": 70,
                "max_error_deg": 5,
            },
            "projection_contract": {
                "mechanical_truth_over_tool_hero_view": False,
                "hero_three_quarter_tool_view_forbidden": False,
            },
        }]
        report = check(design, contract, source["scenario"])
        codes = {item["code"] for item in report["problems"]}
        self.assertIn("interaction-fit-contract", codes)
        self.assertIn("interaction-axis-contract", codes)
        self.assertIn("interaction-projection-contract", codes)

    def test_relevant_stage02_whole_boards_are_mandatory_for_stage05_and_h3(self):
        for attempt in ATTEMPTS:
            contract, source, design = self._compile(attempt)
            available = source["reference_status"]["canonical_boards"]
            self.assertTrue(source["reference_status"]["whole_boards_required"])
            for shot in design["shots"]:
                requirements = shot["reference_requirements"]
                ids = requirements["canonical_stage02_sheet_subject_ids"]
                self.assertTrue(ids)
                self.assertTrue(requirements["canonical_stage02_sheets_required"])
                self.assertTrue(requirements["whole_boards_required"])
                self.assertFalse(requirements["supplemental_references_replace_canonical_boards"])
                self.assertTrue(all(subject_id in available for subject_id in ids))
                pack = compile_shot_pack([shot], {"runtime": PROFILE_ID})
                compiled = pack["shots"][0]
                self.assertEqual(compiled["required_stage02_sheet_subject_ids"], ids)
                self.assertTrue(compiled["reference_policy"]["whole_stage02_boards_required"])
                self.assertFalse(
                    compiled["reference_policy"]["supplemental_manuals_replace_canonical_boards"]
                )

    def test_missing_stage02_pixels_allow_only_a_non_production_stage04_draft(self):
        contract, source, design = self._compile(ATTEMPTS[1])
        design["reference_status"] = {
            **source["reference_status"],
            "canonical_boards": {},
            "missing_subjects": sorted(contract.elements()),
            "design_without_pixels_allowed": True,
            "plate_generation_allowed": False,
        }
        report = check(design, contract, source["scenario"])
        self.assertTrue(report["form_ok"], report["problems"])
        codes = {item["code"] for item in report["warnings"]}
        self.assertIn("canonical-stage02-board-missing", codes)
        self.assertIn("references-not-production-ready", codes)
        self.assertFalse(report["production_ready"])

    def test_missing_stage02_pixels_are_form_error_without_draft_permission(self):
        contract, source, design = self._compile(ATTEMPTS[1])
        design["reference_status"] = {
            **source["reference_status"],
            "canonical_boards": {},
            "missing_subjects": sorted(contract.elements()),
            "design_without_pixels_allowed": False,
            "plate_generation_allowed": False,
        }
        report = check(design, contract, source["scenario"])
        codes = {item["code"] for item in report["problems"]}
        self.assertIn("canonical-stage02-board-missing", codes)
        self.assertFalse(report["form_ok"])

    def test_stage04_decides_and_prompts_multiview_multistate_interaction_manuals(self):
        contract, source, plumber = self._compile(ATTEMPTS[0])
        mechanical = next(
            shot for shot in plumber["shots"]
            if shot["beat_id"] == "B07"
            and shot["supplemental_reference_plan"]["manual_type"] == "mechanical_interaction"
        )
        plan = mechanical["supplemental_reference_plan"]
        self.assertEqual(plan["manual_type"], "mechanical_interaction")
        manual = plan["manuals"][0]
        self.assertGreaterEqual(len(manual["panels"]), 6)
        self.assertGreaterEqual(len(manual["views"]), 3)
        self.assertGreaterEqual(len(manual["states"]), 3)
        self.assertIsNone(manual["image_generation_prompt"])
        self.assertIn("BLOCKED DRAFT", manual["draft_generation_prompt"])
        self.assertTrue(manual["output_assets"]["clean_board"]["send_to_h3"])
        self.assertFalse(manual["output_assets"]["annotated_qa_board"]["send_to_h3"])

        assembly = next(
            shot for shot in plumber["shots"]
            if shot["beat_id"] == "B08"
            and shot["supplemental_reference_plan"]["manual_type"] == "assembly_sequence"
        )
        self.assertIn("parts_and_interfaces",
                      [panel["role"] for panel in
                       assembly["supplemental_reference_plan"]["manuals"][0]["panels"]])

        penthouse = self._compile(ATTEMPTS[1])[2]
        walking = next(shot for shot in penthouse["shots"] if shot["beat_id"] == "B02")
        self.assertEqual(walking["supplemental_reference_plan"]["decision"], "not_required")
        self.assertFalse(walking["supplemental_reference_plan"]["manuals"])

        plate_pack = compile_plate_chain(
            [mechanical], plumber["states"],
            {"model": contract.image_model, "reference_status": source["reference_status"]},
        )
        self.assertEqual(plate_pack["reference_manuals"][0]["manual_id"], manual["manual_id"])
        motion_pack = compile_shot_pack([mechanical], {"runtime": PROFILE_ID})
        self.assertIn(manual["manual_id"],
                      motion_pack["shots"][0]["required_interaction_manual_ids"])
        self.assertIn("interaction_manual_generation_or_approval_pending",
                      motion_pack["shots"][0]["generation_block_reasons"])

    def test_resolved_interaction_contract_produces_renderable_manual_prompt(self):
        contract = Contract.load(ATTEMPTS[0])
        source = gather(ATTEMPTS[0], contract)
        for beat in source["scenario"]["beats"]:
            if beat["id"] == "B07":
                beat["interaction_contracts"] = [{
                    "interaction_id": "B07-I01",
                    "tool_subject_id": "toolkit",
                    "target_subject_id": "pipe-warren",
                    "tool_part_id": "toolkit.pipe-wrench.jaws",
                    "target_part_id": "pipe-warren.coupling-01",
                    "fixed_part_ids": ["pipe-warren.fixed-left", "pipe-warren.fixed-right"],
                    "moving_part_ids": ["pipe-warren.coupling-01"],
                    "result_state": "coupling rotates around its axis while both pipes stay fixed",
                    "fit_contract": {
                        "tool_capacity_part_id": "toolkit.pipe-wrench.jaws",
                        "target_extent_part_id": "pipe-warren.coupling-01.outer-diameter",
                        "tool_capacity_mm": 60,
                        "target_extent_mm": 40,
                        "minimum_capacity_ratio": 1.15,
                    },
                    "axis_contract": {
                        "tool_action_plane_part_id": "toolkit.pipe-wrench.jaw-plane",
                        "target_axis_part_id": "pipe-warren.coupling-01.axis",
                        "relation": "perpendicular",
                        "target_angle_deg": 90,
                        "max_error_deg": 3,
                    },
                    "projection_contract": {
                        "mechanical_truth_over_tool_hero_view": True,
                        "hero_three_quarter_tool_view_forbidden": True,
                    },
                }]
                break
        design = compile_scenario(ATTEMPTS[0], contract, source)
        shot = next(item for item in design["shots"] if item["beat_id"] == "B07")
        manual = shot["supplemental_reference_plan"]["manuals"][0]
        self.assertEqual(manual["prompt_status"], "ready")
        self.assertFalse(manual["unresolved_contract_fields"])
        self.assertIn("READY FOR RENDERING", manual["image_generation_prompt"])
        self.assertIn("look directly along the target axis", manual["image_generation_prompt"])

    def test_articulated_manual_uses_kinematics_without_inventing_a_tool(self):
        contract = Contract.load(ATTEMPTS[1])
        source = gather(ATTEMPTS[1], contract)
        for beat in source["scenario"]["beats"]:
            if beat["id"] == "B05":
                beat["interaction_contracts"] = [{
                    "interaction_id": "B05-I01",
                    "interaction_type": "articulated_mechanism",
                    "sub_beat_id": "B05-a",
                    "actor_subject_id": "host-seoa",
                    "target_subject_id": "skyline-penthouse",
                    "target_part_id": "master-suite.sheer-panel-track",
                    "fixed_part_ids": ["master-suite.ceiling", "master-suite.floor-track"],
                    "moving_part_ids": ["master-suite.sheer-panel"],
                    "result_state": "the sheer panel closes along its track",
                    "kinematic_contract": {
                        "motion_type": "slide",
                        "axis_or_track_part_id": "master-suite.sheer-panel-track",
                        "start_state": "fully open",
                        "mid_state": "half closed",
                        "end_state": "fully closed",
                    },
                }]
                break
        design = compile_scenario(ATTEMPTS[1], contract, source)
        shot = next(item for item in design["shots"] if item["beat_id"] == "B05")
        plan = shot["supplemental_reference_plan"]
        self.assertEqual(plan["manual_type"], "articulated_mechanism")
        manual = plan["manuals"][0]
        self.assertEqual(manual["prompt_status"], "ready")
        self.assertFalse(manual["unresolved_contract_fields"])
        prompt = manual["image_generation_prompt"]
        self.assertIn("EXHAUSTIVE PART MOTION LOCK", prompt)
        self.assertIn("every unlisted part is fixed", prompt)
        self.assertIn("ARTICULATED STATE LOCK", prompt)
        self.assertIn("P1, P2 and P3 are three views of the exact same declared start configuration",
                      prompt)
        self.assertIn("must never reverse, oscillate, switch pivots", prompt)
        report = check(design, contract, source["scenario"])
        self.assertFalse(any(item["code"] in {
            "interaction-fit-contract", "interaction-axis-contract",
            "interaction-projection-contract", "interaction-tool-contract",
        } for item in report["problems"]))


class Stage4ExperimentArtifactTests(unittest.TestCase):
    def test_four_methods_keep_fixed_input_hash_and_are_not_production_outputs(self):
        for attempt in ATTEMPTS:
            root = attempt / "04-shot-design/qa/experiments/methods"
            payloads = [json.loads((root / method / "shot-design.json").read_text())
                        for method in METHODS]
            self.assertEqual({item["method_id"] for item in payloads}, set(METHODS))
            self.assertEqual(len({item["experiment_meta"]["fixed_input_sha256"]
                                  for item in payloads}), 1)
            self.assertTrue(all(item["experiment_meta"]["not_production_approved"]
                                for item in payloads))

    def test_stage05_canaries_carry_stage01_stage02_and_full_stage04_shot(self):
        for attempt in ATTEMPTS:
            root = attempt / "05-plate/qa/experiments/stage4-methods"
            for method in METHODS:
                bundle = json.loads((root / method / "input-bundle.json").read_text())
                self.assertEqual(bundle["method_id"], method)
                self.assertTrue(bundle["stage01_direction"])
                self.assertTrue(bundle["stage01_relevant_definitions"])
                self.assertTrue(bundle["stage02_sheets"])
                self.assertTrue(bundle["stage04_canary_shot"])
                self.assertTrue(bundle["legacy_gate_failures_non_blocking"])
                self.assertTrue(bundle["not_production_approved"])


if __name__ == "__main__":
    unittest.main()
