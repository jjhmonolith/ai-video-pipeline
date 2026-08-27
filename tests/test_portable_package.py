from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PortablePackageTests(unittest.TestCase):
    def test_bundle_is_secret_free_complete_and_manifest_verified(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary) / "output"
            package = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "package_v3_portable.py"),
                    "--root",
                    str(ROOT),
                    "--output-dir",
                    str(output_dir),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            result = json.loads(package.stdout)
            bundle = Path(result["bundle"])
            self.assertTrue(bundle.is_file())

            with zipfile.ZipFile(bundle) as archive:
                names = set(archive.namelist())
                self.assertIn(
                    "ai-video-pipeline-v3/.agents/skills/video-stage05b-motion-prompt/SKILL.md",
                    names,
                )
                self.assertIn("ai-video-pipeline-v3/dashboard/package-lock.json", names)
                self.assertIn(
                    "ai-video-pipeline-v3/src/ai_video_pipeline/dashboard_static/index.html",
                    names,
                )
                self.assertIn("ai-video-pipeline-v3/tests/test_v3_dashboard.py", names)
                self.assertIn("ai-video-pipeline-v3/PORTABLE_MANIFEST.json", names)
                forbidden_parts = {".git", ".secrets", ".venv", "archive", "node_modules", "runs"}
                for name in names:
                    self.assertTrue(forbidden_parts.isdisjoint(Path(name).parts), name)
                    self.assertFalse(
                        any(part.endswith(".egg-info") for part in Path(name).parts),
                        name,
                    )
                self.assertNotIn(
                    "ai-video-pipeline-v3/scripts/run_stage6_fast_track.py",
                    names,
                )
                self.assertNotIn(
                    "ai-video-pipeline-v3/scripts/wait_and_stitch_stage6_local.py",
                    names,
                )

                extracted = Path(temporary) / "extracted"
                archive.extractall(extracted)

            root = extracted / "ai-video-pipeline-v3"
            verified = subprocess.run(
                [
                    sys.executable,
                    str(root / "scripts" / "verify_v3_portable.py"),
                    "--root",
                    str(root),
                    "--manifest",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            report = json.loads(verified.stdout)
            self.assertTrue(report["ok"], report)


if __name__ == "__main__":
    unittest.main()
