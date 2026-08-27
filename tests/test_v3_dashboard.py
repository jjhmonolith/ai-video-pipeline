from __future__ import annotations

import io
import json
import os
import signal
import sys
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from ai_video_pipeline.v3 import cli as v3_cli
from ai_video_pipeline.v3.dashboard_model import build_snapshot
from ai_video_pipeline.v3.dashboard_server import (
    DASHBOARD_SESSION_SCHEMA,
    _session_path,
    _write_json_atomic,
    create_server,
    launch_dashboard,
)
from ai_video_pipeline.v3.orchestrator import initialize, work_order
from ai_video_pipeline.v3.specs import STAGES


class DashboardFixture:
    def __init__(self, root: Path):
        self.attempt = root / "runs" / "dashboard-fixture"
        state = initialize(self.attempt, "한 사람이 열쇠를 건네는 짧은 장면")
        self.paths = {
            "board_old": "02-sheet/qa/attempts/A01/media/CHAR-01-old.png",
            "board": "02-sheet/qa/attempts/A02/media/CHAR-01.png",
            "plate": "05-plate/qa/attempts/A01/media/SH-001.png",
            "video_old": "06-motion/qa/attempts/A01/media/SH-001-C01.mp4",
            "video": "06-motion/qa/attempts/A01/media/SH-001-C02.mp4",
            "master": "07-edit/output/master.mp4",
        }
        for relative in self.paths.values():
            path = self.attempt / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(("media:" + relative).encode("utf-8"))

        contents = self._contents()
        prior_receipts: list[dict] = []
        for spec in STAGES:
            stage_id = spec["id"]
            artifact = {
                "schema_version": "llm-stage-artifact.v1",
                "pipeline_version": "3.0",
                "stage_id": stage_id,
                "attempt_id": self.attempt.name,
                "input_receipts": list(prior_receipts),
                "creative_decisions": [],
                "content": contents[stage_id],
            }
            output = self.attempt / stage_id / "output" / "stage-artifact.json"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(artifact, ensure_ascii=False), encoding="utf-8")
            receipt = self.attempt / stage_id / "receipt.json"
            receipt.write_text(json.dumps({
                "stage_id": stage_id,
                "resolution": "critic_pass",
                "artifact_path": output.relative_to(self.attempt).as_posix(),
            }), encoding="utf-8")
            prior_receipts.append({
                "stage_id": stage_id,
                "path": receipt.relative_to(self.attempt).as_posix(),
                "sha256": f"fixture-{stage_id}",
            })
            state["stages"][stage_id]["status"] = "passed"
            state["stages"][stage_id]["artifact"] = output.relative_to(self.attempt).as_posix()
            state["stages"][stage_id]["receipt"] = receipt.relative_to(self.attempt).as_posix()

        self._stage_retry_history(state, contents["02-sheet"])
        state["current_stage"] = "08-review"
        state["status"] = "complete"
        state["active_work"] = None
        (self.attempt / "pipeline-state.json").write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        orphan = self.attempt / "05-plate" / "qa" / "unbound-note.txt"
        orphan.parent.mkdir(parents=True, exist_ok=True)
        orphan.write_text("not bound by an artifact", encoding="utf-8")

    def _stage_retry_history(self, state: dict, selected_content: dict) -> None:
        records = []
        for number, decision in ((1, "fail"), (2, "pass")):
            base = Path("02-sheet/qa/attempts") / f"A{number:02d}"
            artifact_path = base / "artifact.json"
            validation_path = base / "integrity.json"
            critique_path = base / "critique.json"
            content = selected_content if number == 2 else {
                "boards": [{
                    "board_id": "BOARD-CHAR-01",
                    "subject_id": "CHAR-01",
                    "structured_meta_prompt": {"render_prompt": "실패한 이전 시트 프롬프트"},
                    "selected_image": self.paths["board_old"],
                    "selected_attempt": 1,
                    "attempts": [{
                        "attempt": 1,
                        "prompt": "실패한 이전 시트 프롬프트",
                        "candidate_path": self.paths["board_old"],
                        "decision": "fail",
                    }],
                }],
            }
            artifact = {
                "schema_version": "llm-stage-artifact.v1",
                "pipeline_version": "3.0",
                "stage_id": "02-sheet",
                "attempt_id": self.attempt.name,
                "input_receipts": [],
                "creative_decisions": [],
                "content": content,
            }
            target = self.attempt / artifact_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(artifact, ensure_ascii=False), encoding="utf-8")
            (self.attempt / validation_path).write_text(
                json.dumps({"form_ok": True, "problems": []}), encoding="utf-8"
            )
            (self.attempt / critique_path).write_text(json.dumps({
                "decision": decision,
                "summary": "구도가 잘못됨" if decision == "fail" else "시트 통과",
            }, ensure_ascii=False), encoding="utf-8")
            records.append({
                "attempt": number,
                "variation_strategy": "base" if number == 1 else "composition_reframe",
                "artifact_path": artifact_path.as_posix(),
                "validation_path": validation_path.as_posix(),
                "form_ok": True,
                "critic": {"decision": decision, "path": critique_path.as_posix()},
            })
        state["stages"]["02-sheet"]["attempts"] = records

    def _contents(self) -> dict[str, dict]:
        return {
            "01-premise": {
                "direction": {"interpretation": "열쇠 전달"},
                "runtime_contract": {"target_seconds": 5},
                "frame": {"width": 1920, "height": 1080},
                "subjects": [{"subject_id": "CHAR-01", "kind": "person", "purpose": "host"}],
            },
            "02-sheet": {
                "boards": [{
                    "board_id": "BOARD-CHAR-01",
                    "subject_id": "CHAR-01",
                    "structured_meta_prompt": {
                        "render_prompt": "9칸 캐릭터 레퍼런스 시트",
                        "panel_plan": [{"panel_id": "P01", "purpose": "정면 전신"}],
                    },
                    "selected_image": self.paths["board"],
                    "selected_attempt": 2,
                    "attempts": [
                        {"attempt": 1, "prompt": "실패한 시트", "candidate_path": self.paths["board_old"], "decision": "fail"},
                        {"attempt": 2, "prompt": "개선한 시트", "candidate_path": self.paths["board"], "decision": "pass"},
                    ],
                }],
                "cross_board_review": {"decision": "pass"},
            },
            "03-scenario": {
                "sequences": [{
                    "sequence_id": "SEQ-01", "intent": "신뢰 형성",
                    "scenes": [{
                        "scene_id": "SC-01", "slugline": "INT. ROOM — DAY",
                        "events": [{"event_id": "EV-001", "action": "열쇠를 건넨다", "actor_subject_id": "CHAR-01"}],
                        "production_requirements": [{"requirement_id": "KEY-01", "name": "열쇠"}],
                    }],
                }],
            },
            "04-shot-design": {
                "scene_plans": [{
                    "scene_id": "SC-01", "treatment": {"intent": "신뢰를 보인다"},
                    "setups": [{
                        "setup_id": "SU-01", "camera_position": "탁자 건너편",
                        "shots": [{
                            "shot_id": "SH-001", "event_ids": ["EV-001"],
                            "composition": "medium two-shot",
                            "required_reference_subject_ids": ["CHAR-01", "KEY-01"],
                            "timing": {"edit_target_seconds": 5},
                        }],
                    }],
                }],
            },
            "05-plate": {
                "references": [{
                    "reference_id": "REF-CHAR-01", "subject_or_requirement_id": "CHAR-01",
                    "origin": "stage02", "selected_image": self.paths["board"],
                    "review": {"decision": "pass"},
                }],
                "global_reference_preflight": {"decision": "pass"},
                "plates": [{
                    "shot_id": "SH-001", "reference_ids": ["REF-CHAR-01"],
                    "selected_image": self.paths["plate"], "selected_attempt": 2,
                    "attempts": [
                        {"attempt": 1, "prompt": "실패한 판", "candidate_path": self.paths["plate"], "decision": "fail"},
                        {"attempt": 2, "prompt": "개선한 판", "candidate_path": self.paths["plate"], "decision": "pass"},
                    ],
                }],
            },
            "05.5-motion-prompt": {
                "shots": [{
                    "shot_id": "SH-001", "start_plate": self.paths["plate"],
                    "final_c01_prompt": "승인 판에서 열쇠를 건네고 카메라는 관계를 유지한다.",
                    "reference_bindings": [{"reference_id": "REF-CHAR-01", "path": self.paths["board"]}],
                }],
            },
            "06-motion": {
                "shots": [{
                    "shot_id": "SH-001", "selected_candidate": "C02",
                    "candidates": [
                        {"candidate_id": "C01", "prompt": "첫 영상 프롬프트", "video_path": self.paths["video_old"], "review": {"decision": "fail"}},
                        {"candidate_id": "C02", "prompt": "개선 영상 프롬프트", "video_path": self.paths["video"], "review": {"decision": "pass"}},
                    ],
                }],
                "cross_shot_review": {"decision": "pass"},
            },
            "07-edit": {
                "timeline": [{"shot_id": "SH-001", "source_video": self.paths["video"], "edit_seconds": 5}],
                "output_video": self.paths["master"],
                "master_review": {"decision": "pass"},
            },
            "08-review": {
                "master_video": self.paths["master"],
                "stage_receipts": [{"stage_id": item["id"]} for item in STAGES[:-1]],
                "review_dimensions": [{"dimension": "continuity", "decision": "pass"}],
                "defects": [],
                "release_decision": {"release_eligible": True, "external_publish_authorized": False},
            },
        }


class DashboardModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.fixture = DashboardFixture(Path(self.temp.name))
        self.snapshot = build_snapshot(self.fixture.attempt)
        self.nodes = {node["id"]: node for node in self.snapshot["nodes"]}

    def tearDown(self) -> None:
        self.temp.cleanup()

    def assert_edge(self, source: str, target: str, label: str) -> None:
        self.assertTrue(any(
            edge["source"] == source and edge["target"] == target and edge["label"] == label
            for edge in self.snapshot["edges"]
        ), f"missing edge {source} -> {target} ({label})")

    def test_projects_all_stages_and_direct_lineage(self) -> None:
        self.assertEqual([stage["id"] for stage in self.snapshot["stages"]], [item["id"] for item in STAGES])
        self.assert_edge("01-premise:subject:CHAR-01", "02-sheet:board:BOARD-CHAR-01", "subject definition")
        self.assert_edge("03-scenario:event:EV-001", "04-shot-design:shot:SH-001", "event binding")
        self.assert_edge("04-shot-design:shot:SH-001", "05-plate:plate:SH-001", "shot contract")
        self.assert_edge("05-plate:plate:SH-001", "05.5-motion-prompt:shot:SH-001", "approved start plate")
        self.assert_edge("05.5-motion-prompt:shot:SH-001", "06-motion:shot:SH-001", "final motion prompt")
        self.assert_edge("06-motion:shot:SH-001:C02", "07-edit:segment:001:SH-001", "selected motion take")
        self.assert_edge("07-edit:master", "08-review:final-review", "master video")

    def test_keeps_failed_prompts_media_and_reports_unreferenced_files(self) -> None:
        failed = self.nodes["02-sheet:attempt:A01"]
        self.assertEqual(failed["status"], "failed")
        self.assertTrue(any("실패한 이전 시트" in item["text"] for item in failed["prompts"]))
        board = self.nodes["02-sheet:board:BOARD-CHAR-01"]
        self.assertEqual(len(board["attempts"]), 2)
        self.assertTrue(any(not item["selected"] and item["candidate"]["exists"] for item in board["attempts"]))
        self.assertGreaterEqual(self.snapshot["stats"]["unreferenced_files"], 1)
        self.assertIn("05-plate:unreferenced:05-plate/qa/unbound-note.txt", self.nodes)

    def test_fresh_in_progress_attempt_is_visible_before_any_stage_is_sealed(self) -> None:
        fresh = Path(self.temp.name) / "runs" / "fresh-attempt"
        initialize(fresh, "아직 제작을 시작하지 않은 시도")
        work_order(fresh)
        snapshot = build_snapshot(fresh)
        nodes = {node["id"]: node for node in snapshot["nodes"]}
        self.assertEqual(snapshot["attempt"]["current_stage"], "01-premise")
        self.assertEqual(len(snapshot["stages"]), 9)
        self.assertEqual(nodes["01-premise:work:A01"]["status"], "running")


class DashboardServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        root = Path(self.temp.name)
        self.fixture = DashboardFixture(root)
        static = root / "static"
        static.mkdir()
        (static / "index.html").write_text("<main>dashboard</main>", encoding="utf-8")
        self.server = create_server(self.fixture.attempt, port=0, static_root=static)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def test_snapshot_range_streaming_and_read_only_boundary(self) -> None:
        with urllib.request.urlopen(f"{self.url}/api/snapshot") as response:
            snapshot = json.loads(response.read())
            self.assertEqual(snapshot["schema_version"], "v3-dashboard-snapshot.v1")
            first_etag = response.headers["ETag"]
            self.assertTrue(first_etag)

        unchanged = urllib.request.Request(
            f"{self.url}/api/snapshot", headers={"If-None-Match": first_etag}
        )
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(unchanged)
        self.assertEqual(caught.exception.code, 304)
        caught.exception.close()

        state_path = self.fixture.attempt / "pipeline-state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["updated_at"] = "2099-01-01T00:00:00+09:00"
        state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        with urllib.request.urlopen(unchanged) as response:
            self.assertEqual(response.status, 200)
            self.assertNotEqual(response.headers["ETag"], first_etag)

        request = urllib.request.Request(
            f"{self.url}/media/{self.fixture.paths['video']}", headers={"Range": "bytes=0-4"}
        )
        with urllib.request.urlopen(request) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(len(response.read()), 5)

        unicode_relative = "05-plate/qa/한글 판.png"
        unicode_path = self.fixture.attempt / unicode_relative
        unicode_path.parent.mkdir(parents=True, exist_ok=True)
        unicode_path.write_bytes(b"image")
        encoded = urllib.parse.quote(unicode_relative, safe="/")
        with urllib.request.urlopen(f"{self.url}/media/{encoded}") as response:
            self.assertEqual(response.read(), b"image")
            self.assertIn("filename*=UTF-8''", response.headers["Content-Disposition"])

        request = urllib.request.Request(f"{self.url}/api/snapshot", data=b"{}", method="POST")
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request)
        self.assertEqual(caught.exception.code, 405)
        caught.exception.close()

        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(f"{self.url}/media/..%2Fpipeline-state.json")
        self.assertEqual(caught.exception.code, 404)
        caught.exception.close()

        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(f"{self.url}/..%2Fprivate.txt")
        self.assertEqual(caught.exception.code, 404)
        caught.exception.close()

    def test_launcher_reuses_a_live_attempt_dashboard(self) -> None:
        session = {
            "schema_version": DASHBOARD_SESSION_SCHEMA,
            "status": "serving",
            "url": self.url,
            "attempt": str(self.fixture.attempt.resolve()),
            "pid": os.getpid(),
        }
        _write_json_atomic(_session_path(self.fixture.attempt), session)
        with mock.patch("ai_video_pipeline.v3.dashboard_server.subprocess.Popen") as popen, \
             mock.patch("ai_video_pipeline.v3.dashboard_server.webbrowser.open") as browser_open:
            result = launch_dashboard(self.fixture.attempt)
        self.assertEqual(result["status"], "already_running")
        self.assertEqual(result["url"], self.url)
        popen.assert_not_called()
        browser_open.assert_called_once_with(self.url)

    @unittest.skipIf(os.name == "nt", "POSIX detached-process smoke test")
    def test_launcher_spawns_one_detached_read_only_server(self) -> None:
        fresh = Path(self.temp.name) / "runs" / "detached-dashboard"
        initialize(fresh, "분리 실행 대시보드")
        result = launch_dashboard(fresh, open_browser=False)
        pid = int(result["pid"])
        try:
            self.assertEqual(result["status"], "serving")
            with urllib.request.urlopen(f"{result['url']}api/snapshot") as response:
                self.assertEqual(response.status, 200)
            reused = launch_dashboard(fresh, open_browser=False)
            self.assertEqual(reused["status"], "already_running")
            self.assertEqual(reused["pid"], pid)
        finally:
            os.kill(pid, signal.SIGTERM)
            for _ in range(40):
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.025)


class DashboardCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.attempt = Path(self.temp.name) / "runs" / "auto-dashboard"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_init_opens_dashboard_by_default_and_reports_it(self) -> None:
        argv = [
            "ai-video-pipeline", "init", str(self.attempt),
            "--direction", "자동 대시보드가 열리는 제작",
        ]
        dashboard = {"status": "serving", "url": "http://127.0.0.1:43210/", "pid": 123}
        output = io.StringIO()
        with mock.patch.object(sys, "argv", argv), \
             mock.patch.object(v3_cli, "launch_dashboard", return_value=dashboard) as launch, \
             redirect_stdout(output):
            code = v3_cli.main()
        self.assertEqual(code, 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["dashboard"], dashboard)
        launch.assert_called_once_with(self.attempt)
        state = json.loads((self.attempt / "pipeline-state.json").read_text(encoding="utf-8"))
        self.assertNotIn("dashboard", state)

    def test_headless_init_can_explicitly_disable_dashboard(self) -> None:
        argv = [
            "ai-video-pipeline", "init", str(self.attempt),
            "--direction", "헤드리스 테스트", "--no-dashboard",
        ]
        output = io.StringIO()
        with mock.patch.object(sys, "argv", argv), \
             mock.patch.object(v3_cli, "launch_dashboard") as launch, \
             redirect_stdout(output):
            code = v3_cli.main()
        self.assertEqual(code, 0)
        self.assertNotIn("dashboard", json.loads(output.getvalue()))
        launch.assert_not_called()

    def test_detached_dashboard_command_reuses_background_launcher(self) -> None:
        initialize(self.attempt, "분리 명령 테스트")
        argv = [
            "ai-video-pipeline", "dashboard", str(self.attempt), "--detach", "--no-open",
        ]
        dashboard = {"status": "already_running", "url": "http://127.0.0.1:43210/", "pid": 123}
        output = io.StringIO()
        with mock.patch.object(sys, "argv", argv), \
             mock.patch.object(v3_cli, "launch_dashboard", return_value=dashboard) as launch, \
             redirect_stdout(output):
            code = v3_cli.main()
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue()), dashboard)
        launch.assert_called_once_with(self.attempt, open_browser=False)


if __name__ == "__main__":
    unittest.main()
