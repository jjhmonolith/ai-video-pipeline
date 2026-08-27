import tempfile
import unittest
from pathlib import Path

from ai_video_pipeline.run_layout import (
    LEGACY_STAGES,
    SPLIT_STAGES,
    STAGE_IDS,
    STAGE_ROLES,
    Topic,
    check,
)


class SplitStageTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def _topic(self, name="demo"):
        topic = Topic(self.root / name).ensure()
        (topic.root / "TOPIC.md").write_text("# demo\n", encoding="utf-8")
        return topic

    def test_a_new_attempt_gets_sheet_and_plate_as_separate_stages(self):
        attempt = self._topic().attempt("v1").ensure()
        found = attempt.stages_on_disk()
        self.assertIn("02-sheet", found)
        self.assertIn("05-plate", found)
        self.assertNotIn("06-look", found)

    def test_sheets_are_made_right_after_the_definitions(self):
        # 정의와 그림은 같은 결정의 두 반쪽이다. 떨어뜨리면 서로 어긋난다
        ids = STAGE_IDS
        self.assertEqual(ids[0], "01-premise")
        self.assertEqual(ids[1], "02-sheet")
        self.assertLess(ids.index("02-sheet"), ids.index("03-scenario"))
        self.assertLess(ids.index("02-sheet"), ids.index("05-plate"))

    def test_a_new_attempt_has_one_stage_for_direction_and_definition(self):
        # 브리프와 리서치를 합쳤다. 무엇인지 정하는 자리가 하나다
        found = self._topic().attempt("v1").ensure().stages_on_disk()
        self.assertIn("01-premise", found)
        self.assertNotIn("01-brief", found)
        self.assertNotIn("02-research", found)

    def test_stage_numbers_order_the_pipeline(self):
        # Sorting directory names has to give pipeline order, because that is
        # what the graph relies on instead of a lookup table.
        self.assertEqual(STAGE_IDS, sorted(STAGE_IDS))
        self.assertEqual(STAGE_IDS[-1], "08-review")
        self.assertEqual(STAGE_IDS[0], "01-premise")

    def test_contract_roles_and_layout_use_the_same_stage_ids(self):
        self.assertEqual(list(STAGE_ROLES.values()), STAGE_IDS)

    def test_what_happens_is_decided_before_how_it_is_shot(self):
        # 시나리오와 샷 디자인은 다른 질문이다. 합치면 앵글이 이야기를 정한다
        ids = STAGE_IDS
        self.assertLess(ids.index("03-scenario"), ids.index("04-shot-design"))
        self.assertNotIn("03-concept", ids)
        self.assertNotIn("04-script", ids)

    def test_current_only_and_legacy_only_ids_do_not_overlap(self):
        # 두 목록이 겹치면 섞임 검사가 아무것도 못 잡는다
        self.assertFalse(SPLIT_STAGES & frozenset(LEGACY_STAGES))
        self.assertIn("01-premise", SPLIT_STAGES)
        self.assertIn("05-plate", SPLIT_STAGES)

    def test_an_attempt_made_before_the_split_still_passes(self):
        topic = self._topic()
        attempt = topic.attempt("old")
        for stage in ["01-brief", *LEGACY_STAGES]:
            attempt.stage(stage).ensure()
        (attempt.root / "ATTEMPT.md").write_text("# old\n", encoding="utf-8")

        self.assertEqual(check(topic.root)["problems"], [])

    def test_mixing_the_two_schemes_is_reported(self):
        topic = self._topic()
        attempt = topic.attempt("halfway")
        for stage in ("06-look", "03-scenario"):
            attempt.stage(stage).ensure()
        (attempt.root / "ATTEMPT.md").write_text("# halfway\n", encoding="utf-8")

        problems = check(topic.root)["problems"]
        self.assertTrue(any("섞였다" in p for p in problems), problems)

    def test_an_unknown_stage_name_is_still_refused(self):
        attempt = self._topic().attempt("v1")
        with self.assertRaises(ValueError):
            attempt.stage("06-look-and-feel")


if __name__ == "__main__":
    unittest.main()
