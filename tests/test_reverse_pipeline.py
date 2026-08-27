from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from ai_video_pipeline.reverse.pipeline import analyze_video, compile_documents, parse_scene_timestamps, validate_run


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg required")
class ReversePipelineTests(unittest.TestCase):
    def make_video(self, root: Path) -> Path:
        destination = root / "sample.mp4"
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=red:s=320x180:d=1:r=24",
            "-f", "lavfi", "-i", "color=c=blue:s=320x180:d=1.5:r=24",
            "-f", "lavfi", "-i", "color=c=green:s=320x180:d=1:r=24",
            "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]",
            "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(destination),
        ], check=True)
        return destination

    def test_parse_scene_timestamps(self):
        text = "pts_time:1.25 other pts_time:3 pts_time:1.25"
        self.assertEqual(parse_scene_timestamps(text), [1.25, 3.0])

    def test_end_to_end(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            video = self.make_video(root)
            run = root / "run"
            measurements = analyze_video(video, run, threshold=0.2)
            self.assertEqual(measurements["shot_count"], 3)
            semantic = {
                "schema_version": "1.0",
                "global": {
                    "logline": "Three visual beats progress from hook to demonstration to close.",
                    "viewer_promise": "A clear three-step visual progression.",
                    "tone": "graphic and minimal",
                    "narrative_structure": "hook → demonstration → close",
                    "scene_groups": [{"name": "Progression", "shot_ids": ["S001", "S002", "S003"]}],
                },
                "shots": [
                    {
                        "shot_id": f"S{index:03d}",
                        "observation": label,
                        "narrative_function": function,
                        "actions": ["static color field"],
                        "framing": "full frame graphic",
                        "camera_movement": "locked",
                        "generation_prompt": f"Generate a static {label} full-frame card.",
                        "must_not_show": ["people", "camera shake"],
                    }
                    for index, (label, function) in enumerate([
                        ("red field", "hook"), ("blue field", "demonstration"), ("green field", "close")
                    ], start=1)
                ],
            }
            (run / "semantic.json").write_text(json.dumps(semantic), encoding="utf-8")
            paths = compile_documents(run)
            for path in paths.values():
                self.assertTrue(path.is_file())
                self.assertGreater(path.stat().st_size, 0)
            result = validate_run(run, require_semantic=True)
            self.assertTrue(result["ok"], result)
            contracts = json.loads((run / "shot-contracts.json").read_text())
            self.assertEqual(len(contracts["shots"]), 3)
            self.assertAlmostEqual(sum(item["duration_sec"] for item in contracts["shots"]), 3.5, places=1)


if __name__ == "__main__":
    unittest.main()
