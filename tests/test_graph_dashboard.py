import json
import tempfile
import unittest
from pathlib import Path

from ai_video_pipeline.graph_dashboard import render, scan_topic
from ai_video_pipeline.run_layout import Topic

SHEET_TOOL = '''
from pathlib import Path
RUN_DIR = Path(".")
SHEETS = RUN_DIR / "02-sheet" / "output" / "sheets"
def main():
    SHEETS.mkdir(parents=True, exist_ok=True)
'''

# Reads the sheets from the stage before it, so the hand-off is a real edge.
# Writes through a loop variable, which is how the real runners write and which
# leaves the output directory itself with no resolvable producer.
PLATE_TOOL = '''
from pathlib import Path
RUN_DIR = Path(".")
CARDS = RUN_DIR / "04-shot-design" / "output" / "shot-cards.json"
SHEETS = RUN_DIR / "02-sheet" / "output" / "sheets"
PLATES = RUN_DIR / "05-plate" / "output" / "plates"
def main():
    CARDS.read_text()
    refs = list(SHEETS.glob("*.png"))
    for name in ["C01.png"]:
        (PLATES / name).write_bytes(b"")
'''

# The v1 defect: the sheets are generated and never attached.
BLIND_PLATE_TOOL = '''
from pathlib import Path
RUN_DIR = Path(".")
CARDS = RUN_DIR / "04-shot-design" / "output" / "shot-cards.json"
PLATES = RUN_DIR / "05-plate" / "output" / "plates"
def main():
    CARDS.read_text()
    for name in ["C01.png"]:
        (PLATES / name).write_bytes(b"")
'''


class GraphFixture(unittest.TestCase):
    def build(self, plate_tool: str) -> dict:
        root = Path(tempfile.mkdtemp())
        topic = Topic(root / "demo").ensure()
        (topic.root / "TOPIC.md").write_text("# demo\n", encoding="utf-8")

        spec = topic.claims.parent / "spec"
        spec.mkdir(parents=True, exist_ok=True)
        (spec / "vehicle.json").write_text('{"power_ps": 830}', encoding="utf-8")

        attempt = topic.attempt("v1").ensure()
        (attempt.root / "ATTEMPT.md").write_text("# v1\n", encoding="utf-8")
        (attempt.tools / "make_sheets.py").write_text(SHEET_TOOL, encoding="utf-8")
        (attempt.tools / "make_plates.py").write_text(plate_tool, encoding="utf-8")

        cards = attempt.stage("04-shot-design").output / "shot-cards.json"
        cards.write_text(json.dumps({"cards": [{"shot": "C01", "seconds": 4}]}), encoding="utf-8")

        sheets = attempt.stage("02-sheet").output / "sheets"
        sheets.mkdir(parents=True, exist_ok=True)
        (sheets / "SHEET-HOST.png").write_bytes(b"\x89PNG fake")

        research = attempt.stage("01-premise").output
        (research / "vehicle-spec-snapshot.json").write_text('{"power_ps": 830}', encoding="utf-8")

        notes = attempt.stage("01-premise").notes
        notes.write_text("# 01-premise\n\n## input\n`topic/spec/vehicle.json`\n", encoding="utf-8")

        self.root = topic.root
        return scan_topic(topic.root)

    def artifact(self, report, path):
        arts = report["attempts"][0]["artifacts"]
        return next(a for a in arts if a["id"] == path)

    def stage(self, report, stage_id):
        return next(s for s in report["attempts"][0]["stages"] if s["id"] == stage_id)


class ArtifactStateTests(GraphFixture):
    def test_a_sheet_nothing_downstream_reads_is_flagged(self):
        report = self.build(BLIND_PLATE_TOOL)
        sheets = self.artifact(report, "02-sheet/output/sheets")
        self.assertEqual(sheets["downstream"], [])
        # Whether the sheet reads as untouched or as touched only by the script
        # that made it depends on how the write resolves. Either way it is not
        # wired in, and that is the thing the graph has to say.
        self.assertIn(sheets["state"], {"unread", "self-only"})
        self.assertNotEqual(sheets["state"], "ok")

    def test_attaching_the_sheet_clears_the_flag(self):
        report = self.build(PLATE_TOOL)
        sheets = self.artifact(report, "02-sheet/output/sheets")
        self.assertEqual(sheets["state"], "ok")
        self.assertIn("make_plates.py", sheets["downstream"])

    def test_the_producer_is_inferred_when_the_write_is_in_a_loop(self):
        report = self.build(PLATE_TOOL)
        plates = self.artifact(report, "05-plate/output/plates")
        self.assertEqual(plates["producers"], ["make_plates.py"])
        self.assertTrue(plates["producer_inferred"])

    def test_prompt_packs_are_not_judged_as_unread_assets(self):
        report = self.build(PLATE_TOOL)
        states = {a["state"] for a in report["attempts"][0]["artifacts"] if a["klass"] != "asset"}
        self.assertLessEqual(states, {"record"})


class StageStateTests(GraphFixture):
    def test_a_stage_that_hands_nothing_on_is_a_dead_branch(self):
        report = self.build(PLATE_TOOL)
        research = self.stage(report, "01-premise")
        self.assertTrue(research["dead_branch"])

    def test_a_snapshot_identical_to_the_topic_file_is_named(self):
        report = self.build(PLATE_TOOL)
        research = self.stage(report, "01-premise")
        copied = [f for f in research["files"]["output"] if f.get("copy_of")]
        self.assertEqual([f["copy_of"] for f in copied], ["topic/spec/vehicle.json"])

    def test_the_last_stage_is_not_called_a_dead_branch(self):
        report = self.build(PLATE_TOOL)
        self.assertFalse(self.stage(report, "08-review")["dead_branch"])

    def test_a_stage_that_hands_something_on_is_not_flagged(self):
        report = self.build(PLATE_TOOL)
        self.assertFalse(self.stage(report, "04-shot-design")["dead_branch"])


class EdgeTests(GraphFixture):
    def edges(self, report):
        return {(e["from"], e["to"]): e for e in report["attempts"][0]["edges"]}

    def test_code_edges_are_marked_as_verified(self):
        edges = self.edges(self.build(PLATE_TOOL))
        self.assertEqual(edges[("02-sheet", "05-plate")]["origin"], "code")
        self.assertEqual(edges[("04-shot-design", "05-plate")]["origin"], "code")

    def test_a_notes_claim_alone_is_marked_as_a_claim(self):
        edges = self.edges(self.build(PLATE_TOOL))
        self.assertEqual(edges[("topic", "01-premise")]["origin"], "docs")

    def test_the_missing_hand_off_leaves_no_edge_at_all(self):
        edges = self.edges(self.build(BLIND_PLATE_TOOL))
        self.assertNotIn(("02-sheet", "05-plate"), edges)


class RenderTests(GraphFixture):
    def test_the_page_is_one_self_contained_file_with_the_data_inlined(self):
        report = self.build(PLATE_TOOL)
        out = render(report, self.root / "PIPELINE.html")
        page = out.read_text(encoding="utf-8")

        self.assertIn('<meta charset="utf-8">', page)
        self.assertIn("02-sheet", page)
        self.assertNotIn("<script src=", page)
        self.assertNotIn("__DATA__", page)

    def test_media_is_linked_by_relative_path_not_embedded(self):
        report = self.build(PLATE_TOOL)
        rel = self.artifact(report, "02-sheet/output/sheets")["files"][0]["rel"]
        self.assertEqual(rel, "attempts/v1/02-sheet/output/sheets/SHEET-HOST.png")
        self.assertFalse(Path(rel).is_absolute())


if __name__ == "__main__":
    unittest.main()
