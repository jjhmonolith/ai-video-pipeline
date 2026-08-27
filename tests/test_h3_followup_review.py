import tempfile
import unittest
import re
import shutil
import subprocess
from pathlib import Path

from ai_video_pipeline.h3_followup_review import _blind_group, _html
from ai_video_pipeline.h3_followup_review_server import _response_path


class H3FollowupReviewTests(unittest.TestCase):
    def test_blind_mapping_is_deterministic_and_opaque(self):
        records = [{"record_id": f"condition-{index}"} for index in range(5)]
        first, first_key = _blind_group(records, "group-a")
        second, second_key = _blind_group(list(reversed(records)), "group-a")

        self.assertEqual(first, second)
        self.assertEqual(first_key, second_key)
        self.assertEqual(set(first_key), set("ABCDE"))
        self.assertEqual(set(first_key.values()), {item["record_id"] for item in records})

    def test_html_contains_persistent_human_review_controls_without_factor_names(self):
        html = _html("page-a", "Blind", [{
            "group_id": "g1",
            "title": "평가 그룹",
            "criteria": "동작을 평가",
            "issues": ["관통", "변형"],
            "candidates": [
                {"candidate": "A", "video": "blind-clips/g1/A.mp4"},
                {"candidate": "B", "video": "blind-clips/g1/B.mp4"},
            ],
        }])

        self.assertIn("후보별 피드백", html)
        self.assertIn("그룹 최종 판정", html)
        self.assertIn("승자 없음", html)
        self.assertIn("/api/save-review", html)
        self.assertIn("localStorage", html)
        self.assertIn("JSON 다운로드", html)
        self.assertIn("review_complete", html)
        self.assertIn("human-review-response.json", html)
        self.assertIn("timeupdate", html)
        self.assertNotIn("first_only", html)
        self.assertNotIn("paired", html)
        self.assertNotIn("identity_plus_affordance", html)

        if shutil.which("node"):
            script = re.search(r"<script>(.*)</script>", html, re.DOTALL).group(1)
            checked = subprocess.run(
                ["node", "--check"], input=script, text=True, capture_output=True)
            self.assertEqual(checked.returncode, 0, checked.stderr)

    def test_response_path_accepts_only_known_topic_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            accepted = _response_path(root, "luxury-penthouse-tour")
            self.assertTrue(str(accepted).endswith("comparison/human-review-response.json"))
            with self.assertRaises(ValueError):
                _response_path(root, "../../outside")


if __name__ == "__main__":
    unittest.main()
