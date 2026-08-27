from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ai_video_pipeline.execution_mode import (
    FAST_TRACK_MODE,
    NORMAL_MODE,
    ExecutionModeError,
    load_execution_mode,
    mode_path,
    set_execution_mode,
)


class ExecutionModeTests(unittest.TestCase):
    def setUp(self):
        self.attempt = Path(tempfile.mkdtemp()) / "attempt"
        self.attempt.mkdir()

    def test_missing_record_is_normal_without_writing_implicit_state(self):
        result = load_execution_mode(self.attempt)
        self.assertEqual(result["mode"], NORMAL_MODE)
        self.assertTrue(result["intermediate_human_approval_required"])
        self.assertFalse(mode_path(self.attempt).exists())

    def test_fast_track_requires_and_records_explicit_user_instruction(self):
        result = set_execution_mode(
            self.attempt, FAST_TRACK_MODE, by="user",
            reason="explicit autonomous end-to-end request",
        )
        loaded = load_execution_mode(self.attempt)
        self.assertEqual(loaded["mode"], FAST_TRACK_MODE)
        self.assertEqual(loaded["source"], "explicit_user_instruction")
        self.assertFalse(loaded["intermediate_human_approval_required"])
        self.assertTrue(loaded["ai_may_apply_internal_review_packets"])
        self.assertFalse(loaded["external_side_effects_authorized"])
        self.assertEqual(result["set_at"], loaded["set_at"])

    def test_handwritten_fast_track_without_opt_in_receipt_is_rejected(self):
        path = mode_path(self.attempt)
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({
            "schema_version": "execution-mode.v1",
            "mode": FAST_TRACK_MODE,
            "attempt": str(self.attempt.resolve()),
            "source": "inferred",
        }), encoding="utf-8")
        with self.assertRaises(ExecutionModeError):
            load_execution_mode(self.attempt)

    def test_explicit_reset_to_normal_restores_human_checkpoints(self):
        set_execution_mode(self.attempt, FAST_TRACK_MODE, by="user", reason="fast")
        reset = set_execution_mode(self.attempt, NORMAL_MODE, by="user", reason="review")
        self.assertEqual(reset["mode"], NORMAL_MODE)
        self.assertTrue(reset["intermediate_human_approval_required"])


if __name__ == "__main__":
    unittest.main()
