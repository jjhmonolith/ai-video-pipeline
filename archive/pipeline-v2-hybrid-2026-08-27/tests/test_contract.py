import json
import tempfile
import unittest
from pathlib import Path

from ai_video_pipeline.contract import (
    Contract,
    ContractError,
    find_contract,
    scaffold,
    validate,
)
from ai_video_pipeline.run_layout import STAGE_ROLES

MINIMAL = {
    "contract_id": "T", "attempt": "a1",
    "frame": {"width": 768, "height": 1344, "fps": 24,
              "applies_to": ["05-plate", "06-motion"],
              "upscale": {"allowed": False}},
    "delivery_frame": {
        "width": 768, "height": 1344, "fps": 24,
        "applies_to": ["07-edit"],
        "transform": {"allowed": False, "operation": "none"},
    },
    "image": {
        "model": "gpt-image-2", "quality": "high",
        "api_sizes": ["1024x1024", "1024x1536", "1536x1024"],
        "roles": {
            "plate": {"deliver_at": "frame"},
            "sheet": {"deliver_at": "max", "orientation": "portrait"},
        },
    },
    "clauses": [
        {"id": "no-text", "en": "NO TEXT.", "applies_to": ["05-plate", "06-motion"]},
        {"id": "people", "when": "has_host", "en_true": "ONE PERSON.",
         "en_false": "NO PEOPLE.", "applies_to": ["05-plate"]},
        {"id": "physics", "en": "REAL PHYSICS.", "applies_to": ["06-motion"]},
    ],
}


def write(data: dict, root: Path, stage: str = "01-premise") -> Path:
    target = root / stage / "output" / "contract.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return target


class Fixture(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def contract(self, **overrides) -> Contract:
        data = json.loads(json.dumps(MINIMAL))
        data.update(overrides)
        write(data, self.root)
        return Contract.load(self.root)


class DiscoveryTests(Fixture):
    def test_the_contract_is_found_without_naming_a_stage(self):
        # 새 프로젝트가 단계를 다르게 번호 매겨도 찾아야 한다
        write(MINIMAL, self.root, stage="00-intake")
        self.assertEqual(find_contract(self.root).parent.parent.name, "00-intake")

    def test_the_earliest_stage_wins_when_several_publish_one(self):
        write(MINIMAL, self.root, stage="04-script")
        write(MINIMAL, self.root, stage="01-brief")
        self.assertEqual(find_contract(self.root).parent.parent.name, "01-brief")

    def test_a_file_path_is_accepted_directly(self):
        path = write(MINIMAL, self.root)
        self.assertEqual(find_contract(path), path)

    def test_a_missing_contract_is_an_error_that_says_so(self):
        with self.assertRaises(ContractError) as caught:
            Contract.load(self.root)
        self.assertIn("계약이 없다", str(caught.exception))


class FrameTests(Fixture):
    def test_the_frame_binds_only_the_stages_it_names(self):
        c = self.contract()
        self.assertTrue(c.frame_binds("05-plate"))
        self.assertFalse(c.frame_binds("02-sheet"))

    def test_a_frame_with_no_applies_to_binds_everything(self):
        data = json.loads(json.dumps(MINIMAL))
        data["frame"].pop("applies_to")
        write(data, self.root)
        self.assertTrue(Contract.load(self.root).frame_binds("02-sheet"))

    def test_an_explicit_empty_applies_to_binds_nothing(self):
        data = json.loads(json.dumps(MINIMAL))
        data["frame"]["applies_to"] = []
        write(data, self.root)
        self.assertFalse(Contract.load(self.root).frame_binds("02-sheet"))

    def test_delivery_frame_binds_only_the_final_edit(self):
        c = self.contract()
        self.assertEqual(c.frame_for_stage("05-plate"), c.frame)
        self.assertEqual(c.frame_for_stage("07-edit"), c.delivery_frame)
        self.assertIsNone(c.frame_for_stage("02-sheet"))


class ImagePlanTests(Fixture):
    def test_a_plate_is_the_frame_and_follows_it(self):
        """1단계에서 프레임을 바꾸면 판이 따라와야 한다. 도구를 고치지 않는다."""
        for width, height in [(768, 1344), (576, 1024), (832, 1472), (1024, 1024)]:
            data = json.loads(json.dumps(MINIMAL))
            data["frame"]["width"], data["frame"]["height"] = width, height
            data["delivery_frame"]["width"], data["delivery_frame"]["height"] = width, height
            root = Path(tempfile.mkdtemp())
            write(data, root)
            plan = Contract.load(root).image_plan("plate")
            self.assertEqual(plan.target, (width, height), f"{width}x{height}")

    def test_a_landscape_frame_orders_a_landscape_api_size(self):
        c = self.contract(
            frame={"width": 1344, "height": 768, "fps": 24},
            delivery_frame={"width": 1344, "height": 768, "fps": 24,
                            "applies_to": ["07-edit"],
                            "transform": {"allowed": False, "operation": "none"}},
        )
        self.assertEqual(c.image_plan("plate").api_size, "1536x1024")

    def test_a_portrait_frame_orders_a_portrait_api_size(self):
        self.assertEqual(self.contract().image_plan("plate").api_size, "1024x1536")

    def test_a_sheet_takes_the_largest_size_and_ignores_the_frame(self):
        sheet = self.contract().image_plan("sheet")
        self.assertEqual(sheet.target, (1024, 1536))
        self.assertEqual(sheet.fit, "exact")

    def test_the_sheet_does_not_move_when_the_frame_does(self):
        small = self.contract(
            frame={"width": 576, "height": 1024, "fps": 24},
            delivery_frame={"width": 576, "height": 1024, "fps": 24,
                            "applies_to": ["07-edit"],
                            "transform": {"allowed": False, "operation": "none"}},
        )
        self.assertEqual(small.image_plan("sheet").target, (1024, 1536))

    def test_the_plate_never_needs_upscaling_from_the_api(self):
        self.assertIn(self.contract().image_plan("plate").fit,
                      {"exact", "crop-and-downscale"})

    def test_an_unknown_role_names_the_roles_that_exist(self):
        with self.assertRaises(ContractError) as caught:
            self.contract().image_plan("poster")
        self.assertIn("plate", str(caught.exception))


class ClauseTests(Fixture):
    def test_a_stage_gets_only_the_clauses_bound_to_it(self):
        c = self.contract()
        self.assertEqual(c.clause_ids("06-motion"), ["no-text", "physics"])

    def test_a_conditional_clause_picks_its_branch(self):
        c = self.contract()
        self.assertIn("ONE PERSON.", c.clause_text("05-plate", {"has_host": True}))
        self.assertIn("NO PEOPLE.", c.clause_text("05-plate", {"has_host": False}))

    def test_a_conditional_clause_is_skipped_when_the_flag_is_absent(self):
        # 없는 플래그를 추측하면 있지도 않은 위반을 보고하게 된다
        self.assertNotIn("people", self.contract().clause_ids("05-plate"))

    def test_the_flags_a_contract_uses_are_discoverable(self):
        self.assertEqual(self.contract().condition_flags, ["has_host"])

    def test_clause_text_is_exactly_what_a_tool_appends(self):
        c = self.contract()
        text = c.clause_text("06-motion")
        for clause in c.clauses_for("06-motion"):
            self.assertIn(clause["text"], text)

    def test_a_kind_scoped_clause_does_not_leak_into_a_setting_sheet(self):
        data = json.loads(json.dumps(MINIMAL))
        data["clauses"].append({
            "id": "skin", "en": "NATURAL SKIN.", "applies_to": ["02-sheet"],
            "subject_kinds": ["character"],
        })
        write(data, self.root)
        contract = Contract.load(self.root)
        self.assertIn("skin", contract.clause_ids("02-sheet", subject_kind="character"))
        self.assertNotIn("skin", contract.clause_ids("02-sheet", subject_kind="setting"))


class ReceiptTests(Fixture):
    def test_the_block_carries_the_digest_and_the_frame(self):
        c = self.contract()
        block = c.receipt_block("05-plate", {"has_host": True}, role="plate")
        self.assertEqual(block["sha256"], c.digest)
        self.assertEqual(block["frame"], {"width": 768, "height": 1344, "fps": 24})
        self.assertEqual(block["delivery_frame"],
                         {"width": 768, "height": 1344, "fps": 24})
        self.assertEqual(block["stage_frame"],
                         {"width": 768, "height": 1344, "fps": 24})
        self.assertEqual(block["image_plan"]["target"], [768, 1344])

    def test_the_digest_moves_when_the_contract_moves(self):
        before = self.contract().digest
        after = self.contract(duration_seconds=90).digest
        self.assertNotEqual(before, after)

    def test_legacy_duration_is_stage1_fixed_runtime_without_a_tool_default(self):
        contract = self.contract(duration_seconds=37)
        self.assertEqual(contract.runtime_contract["mode"], "fixed")
        self.assertEqual(contract.runtime_contract["target_seconds"], 37)


class ValidationTests(unittest.TestCase):
    def test_runtime_contract_supports_fixed_range_and_open(self):
        for runtime in (
            {"mode": "fixed", "target_seconds": 45},
            {"mode": "range", "min_seconds": 30, "max_seconds": 60},
            {"mode": "open"},
        ):
            data = json.loads(json.dumps(MINIMAL))
            data["runtime_contract"] = runtime
            self.assertEqual(validate(data), [], runtime)

    def test_h3_audio_policy_requires_discard_and_approved_script(self):
        data = json.loads(json.dumps(MINIMAL))
        data["audio"] = {
            "h3_native_audio": "discard",
            "target_language": "ko",
            "dialogue_source": "approved_script_only",
            "lip_sync": "only_when_onscreen_speaker_is_explicit",
        }
        self.assertFalse(validate(data))
        data["audio"]["h3_native_audio"] = "use"
        self.assertTrue(any("h3_native_audio" in p for p in validate(data)))

    def test_a_conditional_clause_without_both_branches_is_reported(self):
        data = json.loads(json.dumps(MINIMAL))
        data["clauses"][1].pop("en_false")
        self.assertTrue(any("en_true/en_false" in p for p in validate(data)))

    def test_duplicate_clause_ids_are_reported(self):
        data = json.loads(json.dumps(MINIMAL))
        data["clauses"].append(dict(data["clauses"][0]))
        self.assertTrue(any("중복" in p for p in validate(data)))

    def test_a_bad_size_string_is_reported(self):
        data = json.loads(json.dumps(MINIMAL))
        data["image"]["api_sizes"].append("1024*1536")
        self.assertTrue(any("api_sizes" in p for p in validate(data)))

    def test_a_bad_explicit_role_target_is_reported(self):
        data = json.loads(json.dumps(MINIMAL))
        data["image"]["roles"]["sheet"]["target_sizes"] = {
            "landscape": "941x1672",
        }
        self.assertTrue(any("방향과 크기가 다르다" in p for p in validate(data)))

    def test_h3_profile_rejects_a_delivery_resolution_as_generation_frame(self):
        data = json.loads(json.dumps(MINIMAL))
        data["motion"] = {"runtime": "minimax-h3-local-768p", "frame_source": "frame"}
        data["frame"]["width"], data["frame"]["height"] = 1080, 1920
        data["delivery_frame"]["width"], data["delivery_frame"]["height"] = 1080, 1920
        problems = validate(data)
        self.assertTrue(any("768p frame" in p for p in problems))

    def test_h3_profile_rejects_non_native_fps(self):
        data = json.loads(json.dumps(MINIMAL))
        data["motion"] = {"runtime": "minimax-h3-local-768p", "frame_source": "frame"}
        data["frame"]["fps"] = 30
        data["delivery_frame"]["fps"] = 30
        self.assertTrue(any("fps 는 24" in p for p in validate(data)))

    def test_explicit_uniform_delivery_crop_and_scale_is_valid(self):
        data = json.loads(json.dumps(MINIMAL))
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
        self.assertEqual(validate(data), [])

    def test_a_declared_motion_stage_requires_a_runtime_contract(self):
        data = json.loads(json.dumps(MINIMAL))
        data["stages"] = {"motion": "06-motion"}
        self.assertTrue(any("motion.runtime" in p for p in validate(data)))

    def test_a_valid_contract_reports_nothing(self):
        self.assertEqual(validate(MINIMAL), [])


class ScaffoldTests(unittest.TestCase):
    def test_a_new_project_gets_a_contract_that_loads(self):
        root = Path(tempfile.mkdtemp())
        target = root / "01-premise" / "output" / "contract.json"
        scaffold(target, "NEW-PROJECT", "v1")
        contract = Contract.load(root)
        self.assertEqual(contract.data["contract_id"], "NEW-PROJECT")
        self.assertEqual({k: contract.data["stages"][k] for k in STAGE_ROLES},
                         STAGE_ROLES)
        self.assertEqual(contract.data["frame"]["applies_to"],
                         ["05-plate", "06-motion"])
        self.assertEqual(contract.data["delivery_frame"]["applies_to"], ["07-edit"])
        self.assertEqual(contract.data["motion"]["runtime"], "minimax-h3-local-768p")
        self.assertEqual(contract.image_plan("plate").target,
                         (contract.frame.width, contract.frame.height))
        self.assertEqual(contract.image_plan("plate").api_size, "1024x1536")
        self.assertEqual(contract.image_plan("sheet").target, (941, 1672))
        self.assertEqual(contract.image_plan("sheet").api_size, "1152x2048")
        self.assertEqual(contract.image_quality("sheet"), "high")
        self.assertEqual(contract.image_quality("sheet", draft=True), "high")


if __name__ == "__main__":
    unittest.main()
