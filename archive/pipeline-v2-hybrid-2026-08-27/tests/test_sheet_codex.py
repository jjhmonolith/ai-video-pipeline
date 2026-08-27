import hashlib
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from ai_video_pipeline.contract import Contract
from ai_video_pipeline.execution_mode import set_execution_mode
from ai_video_pipeline.sheets import (
    LOCAL_PROMPT_COMPILER,
    SHEET_AI_ATTEMPT_REVIEW_SCHEMA,
    SheetError,
    approve_references,
    compose_prompt,
    definition_content_sha256,
    finalize_codex_jobs,
    materialize_with_pixel_tolerance,
    prepare_codex_jobs,
    record_ai_sheet_review,
    run,
    structured_meta_prompt,
    structured_prompt_pack,
)


CONTRACT = {
    "contract_id": "CODEX-SHEET-TEST",
    "attempt": "v1",
    "stages": {"premise": "01-premise", "sheet": "02-sheet"},
    "frame": {
        "width": 8,
        "height": 12,
        "fps": 24,
        "applies_to": [],
        "upscale": {"allowed": False},
    },
    "delivery_frame": {
        "width": 8,
        "height": 12,
        "fps": 24,
        "applies_to": ["07-edit"],
        "transform": {"allowed": False, "operation": "none"},
    },
    "image": {
        "model": "gpt-image-2",
        "quality": "high",
        "api_sizes": ["16x9"],
        "roles": {"sheet": {"deliver_at": "max", "orientation": "landscape"}},
    },
    "sheet": {"kinds": {"character": {"panels": ["front"], "spec": "character"}}},
    "subjects": {
        "directory": "01-premise/output/subjects",
        "declared": {"hero": {"kind": "character"}},
    },
    "clauses": [
        {"id": "safe", "en": "NO LOGOS.", "applies_to": ["02-sheet"]}
    ],
}


class CodexSheetFixture(unittest.TestCase):
    def setUp(self):
        self.attempt = Path(tempfile.mkdtemp())
        contract_path = self.attempt / "01-premise" / "output" / "contract.json"
        contract_path.parent.mkdir(parents=True)
        contract_path.write_text(json.dumps(CONTRACT), encoding="utf-8")
        self.definition = {"name": "hero", "appearance": "round blue helper"}
        definition_path = self.attempt / "01-premise" / "output" / "subjects" / "hero.json"
        definition_path.parent.mkdir(parents=True)
        definition_path.write_text(json.dumps(self.definition), encoding="utf-8")
        self.prompt_path = self.attempt / "02-sheet" / "prompts" / "hero.json"
        self.prompt_path.parent.mkdir(parents=True)
        contract = Contract.load(self.attempt)
        context = structured_meta_prompt(self.attempt, contract, "hero")
        self.prompt_path.write_text(json.dumps(structured_prompt_pack(
            context,
            "One 16:9 character sheet. NO LOGOS.",
            "test-structured-writer",
        )), encoding="utf-8")

    def prepare(self, force=False):
        result = prepare_codex_jobs(self.attempt, force=force)
        manifest_path = Path(result["manifest"])
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return result, manifest_path, manifest


class CodexPreparationTests(CodexSheetFixture):
    @patch("ai_video_pipeline.sheets._client")
    def test_codex_compose_only_uses_local_structured_compiler_without_api(self, client_factory):
        result = run(self.attempt, generator="codex", compose_only=True)

        client_factory.assert_not_called()
        self.assertFalse(result["api_called"])
        self.assertEqual(result["compiler"], LOCAL_PROMPT_COMPILER)
        self.assertEqual(result["composed"], 1)
        pack = json.loads(self.prompt_path.read_text(encoding="utf-8"))
        self.assertEqual(pack["schema_version"], "sheet-prompt-pack.v2")
        self.assertEqual(pack["authoring_pipeline"], "structured-meta-prompt.v1")
        self.assertEqual(pack["written_by"], LOCAL_PROMPT_COMPILER)
        self.assertIn('"appearance": "round blue helper"', pack["prompt"])
        self.assertIn("Use exactly these panels in this order: front", pack["prompt"])
        self.assertIn("NO LOGOS.", pack["prompt"])

    @patch("ai_video_pipeline.sheets._client")
    def test_official_composer_uses_the_full_structured_meta_prompt(self, client_factory):
        client = client_factory.return_value
        client.responses.create.return_value = SimpleNamespace(
            output_text="One 16:9 character sheet. NO LOGOS."
        )
        contract = Contract.load(self.attempt)

        pack = compose_prompt(self.attempt, contract, "hero", model="writer-test")

        sent = client.responses.create.call_args.kwargs["input"]
        self.assertIn("=== 계약 시트 정책 ===", sent)
        self.assertIn("=== 시트 명세 ===", sent)
        self.assertIn("=== 대상 정의 ===", sent)
        self.assertIn('"appearance": "round blue helper"', sent)
        self.assertEqual(pack["schema_version"], "sheet-prompt-pack.v2")
        self.assertEqual(pack["authoring_pipeline"], "structured-meta-prompt.v1")
        self.assertEqual(pack["meta_prompt_sha256"],
                         structured_meta_prompt(self.attempt, contract, "hero")["meta_prompt_sha256"])

    def test_prepare_writes_an_api_free_work_order(self):
        result, _, manifest = self.prepare()
        self.assertFalse(result["api_called"])
        self.assertEqual(result["jobs"], 1)
        self.assertEqual(manifest["generator"]["mode"], "codex")
        self.assertFalse(manifest["generator"]["api_key_required"])
        pack = json.loads(self.prompt_path.read_text(encoding="utf-8"))
        self.assertEqual(pack["schema_version"], "sheet-prompt-pack.v2")
        self.assertEqual(pack["authoring_pipeline"], "structured-meta-prompt.v1")
        self.assertEqual(len(pack["meta_prompt_sha256"]), 16)
        self.assertEqual(manifest["jobs"][0]["prompt_path"],
                         "02-sheet/prompts/hero.json")
        self.assertIn("native 16x9-pixel landscape PNG at HIGH quality",
                      manifest["jobs"][0]["imagegen_prompt"])
        self.assertEqual(len(manifest["jobs"][0]["imagegen_prompt_sha256"]), 16)
        self.assertEqual(manifest["jobs"][0]["retry_harness"]["max_attempts"], 10)
        self.assertTrue(manifest["jobs"][0]["retry_harness"]["vary_every_retry"])

    def test_fast_track_is_bound_to_sheet_manifest_and_shared_harness(self):
        set_execution_mode(self.attempt, "fast_track", by="user", reason="autonomous run")
        _, _, manifest = self.prepare()
        harness = manifest["jobs"][0]["retry_harness"]
        self.assertEqual(manifest["execution_mode"]["mode"], "fast_track")
        self.assertEqual(harness["execution_mode"], "fast_track")
        self.assertNotIn("required_human_final_approval",
                         harness["terminal_failure_classes"])

    def test_sheet_retry_uses_a_distinct_prompt_variation_until_pass(self):
        _, manifest_path, manifest = self.prepare()
        job = manifest["jobs"][0]

        def record(decision: str, feedback: str = "") -> dict:
            log_path = self.attempt / job["retry_harness"]["review_log_path"]
            number = 1
            if log_path.exists():
                number += len(json.loads(log_path.read_text(encoding="utf-8"))["attempts"])
            candidate = self.attempt / str(
                job["retry_harness"]["attempt_path_pattern"]).format(attempt=number)
            candidate.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (16, 9), "green").save(candidate)
            criteria = []
            for index, criterion in enumerate(job["retry_harness"]["acceptance_criteria"]):
                status = "pass" if decision == "pass" or index else "fail"
                criteria.append({"criterion": criterion, "status": status,
                                 "evidence": [f"attempt {number}"]})
            review_path = candidate.with_suffix(".review.json")
            review_path.write_text(json.dumps({
                "schema_version": SHEET_AI_ATTEMPT_REVIEW_SCHEMA,
                "element": job["element"], "decision": decision,
                "criteria": criteria, "feedback": feedback,
                "reviewer": "fixture-ai",
                "reviewed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            }), encoding="utf-8")
            return record_ai_sheet_review(self.attempt, manifest_path, review_path)

        retry = record("fail", "make the panel topology consistent")
        self.assertEqual(retry["next_attempt"], 2)
        self.assertNotEqual(retry["imagegen_prompt"], job["imagegen_prompt"])
        self.assertIn("positive_requirement_restatement", retry["imagegen_prompt"])
        selected = record("pass")
        self.assertEqual(selected["selected_attempt"], 2)
        self.assertTrue((self.attempt / job["candidate_path"]).exists())

    def test_existing_adopted_output_is_not_overwritten_by_default(self):
        output = self.attempt / "02-sheet" / "output" / "sheets" / "hero.png"
        output.parent.mkdir(parents=True)
        Image.new("RGB", (16, 9), "blue").save(output)
        result, _, manifest = self.prepare()
        self.assertEqual(result["jobs"], 0)
        self.assertEqual(manifest["skipped"][0]["reason"], "output-exists")
        self.assertTrue(output.exists())

    def test_stale_prompt_pack_is_rejected_before_generation(self):
        data = json.loads(self.prompt_path.read_text(encoding="utf-8"))
        data["definition_content_sha256"] = "obsolete"
        self.prompt_path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(SheetError):
            prepare_codex_jobs(self.attempt)

    def test_self_authored_pack_without_structured_meta_provenance_is_rejected(self):
        data = json.loads(self.prompt_path.read_text(encoding="utf-8"))
        data.pop("schema_version")
        data.pop("authoring_pipeline")
        self.prompt_path.write_text(json.dumps(data), encoding="utf-8")

        with self.assertRaises(SheetError) as caught:
            prepare_codex_jobs(self.attempt)

        self.assertIn("구조화 메타 프롬프트 provenance", str(caught.exception))

    def test_meta_prompt_hash_tampering_is_rejected_before_generation(self):
        data = json.loads(self.prompt_path.read_text(encoding="utf-8"))
        data["meta_prompt_sha256"] = "self-authored"
        self.prompt_path.write_text(json.dumps(data), encoding="utf-8")

        with self.assertRaises(SheetError) as caught:
            prepare_codex_jobs(self.attempt)

        self.assertIn("meta_prompt_sha256", str(caught.exception))

    def test_governance_only_definition_changes_do_not_stale_the_visual_prompt(self):
        definition_path = self.attempt / "01-premise/output/subjects/hero.json"
        changed = json.loads(definition_path.read_text(encoding="utf-8"))
        changed["decisions"] = {"appearance": {"class": "creative_choice"}}
        changed["provenance"] = {"approved_by": "reviewer"}
        definition_path.write_text(json.dumps(changed), encoding="utf-8")
        result, _, _ = self.prepare()
        self.assertEqual(result["jobs"], 1)

    def test_visual_definition_changes_still_stale_the_prompt(self):
        definition_path = self.attempt / "01-premise/output/subjects/hero.json"
        changed = json.loads(definition_path.read_text(encoding="utf-8"))
        changed["appearance"] = "different silhouette"
        definition_path.write_text(json.dumps(changed), encoding="utf-8")
        with self.assertRaises(SheetError):
            self.prepare()

    def test_clause_scoped_to_another_kind_cannot_leak_into_the_prompt(self):
        contract_path = self.attempt / "01-premise/output/contract.json"
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        contract["clauses"].append({
            "id": "setting-only",
            "en": "NO IDENTIFIABLE HOST ON THE SETTING BOARD.",
            "applies_to": ["02-sheet"],
            "subject_kinds": ["setting"],
        })
        contract_path.write_text(json.dumps(contract), encoding="utf-8")
        current = Contract.load(self.attempt)
        context = structured_meta_prompt(self.attempt, current, "hero")
        prompt = structured_prompt_pack(
            context,
            "One 16:9 character sheet. NO LOGOS. "
            "NO IDENTIFIABLE HOST ON THE SETTING BOARD.",
            "test-structured-writer",
        )
        self.prompt_path.write_text(json.dumps(prompt), encoding="utf-8")

        with self.assertRaises(SheetError) as caught:
            self.prepare()
        self.assertIn("프롬프트에 누출", str(caught.exception))


class CodexFinalizationTests(CodexSheetFixture):
    def test_an_empty_skipped_manifest_cannot_rewrite_the_receipt(self):
        output = self.attempt / "02-sheet" / "output" / "sheets" / "hero.png"
        output.parent.mkdir(parents=True)
        Image.new("RGB", (16, 9), "blue").save(output)
        _, manifest_path, manifest = self.prepare()
        self.assertEqual(manifest["jobs"], [])

        with self.assertRaises(SheetError):
            finalize_codex_jobs(self.attempt, manifest_path, surface="desktop")
        self.assertFalse((self.attempt / "02-sheet" / "receipt.json").exists())

    def test_finalize_accepts_contract_sized_candidate_and_writes_receipt(self):
        _, manifest_path, manifest = self.prepare()
        candidate = self.attempt / manifest["jobs"][0]["candidate_path"]
        candidate.parent.mkdir(parents=True)
        Image.new("RGB", (16, 9), "green").save(candidate)

        result = finalize_codex_jobs(self.attempt, manifest_path, surface="cli")

        output = self.attempt / result["outputs"][0]
        with Image.open(output) as image:
            self.assertEqual(image.size, (16, 9))
        receipt = json.loads(Path(result["receipt"]).read_text(encoding="utf-8"))
        record = receipt["sheets"][0]
        self.assertEqual(receipt["schema_version"], "sheet-receipt.v2")
        self.assertEqual(record["generator"]["mode"], "codex")
        self.assertEqual(record["generator"]["surface"], "cli")
        self.assertEqual(record["generator"]["token_detail"], "not-exposed")
        self.assertEqual(record["source_dimensions"], [16, 9])
        self.assertEqual(record["fit"], "exact")
        self.assertEqual(record["imagegen_prompt_sha256"],
                         manifest["jobs"][0]["imagegen_prompt_sha256"])
        self.assertNotIn("usage", record)

    def test_ai_semantic_preflight_makes_sheets_reference_ready_without_user_approval(self):
        _, manifest_path, manifest = self.prepare()
        candidate = self.attempt / manifest["jobs"][0]["candidate_path"]
        candidate.parent.mkdir(parents=True)
        Image.new("RGB", (16, 9), "green").save(candidate)
        finalize_codex_jobs(self.attempt, manifest_path, surface="desktop")
        review_path = self.attempt / "02-sheet/qa/semantic-review.json"
        review = json.loads(review_path.read_text(encoding="utf-8"))
        for subject in review["reviews"]:
            for check in subject["checks"]:
                if check["status"] == "human_review_required":
                    check.update({
                        "status": "passed", "reviewer": "codex-ai-sheet-preflight",
                        "evidence": ["visual identity and board structure checked"],
                    })
        review_path.write_text(json.dumps(review), encoding="utf-8")

        result = approve_references(
            self.attempt, "codex-ai-sheet-preflight", review_mode="ai_preflight")

        self.assertTrue(result["reference_ready"])
        self.assertEqual(result["review_mode"], "ai_preflight")
        approved = json.loads(review_path.read_text(encoding="utf-8"))
        self.assertFalse(approved["human_approval_required"])

    def test_finalize_rejects_an_undersized_candidate_instead_of_upscaling(self):
        _, manifest_path, manifest = self.prepare()
        candidate = self.attempt / manifest["jobs"][0]["candidate_path"]
        candidate.parent.mkdir(parents=True)
        Image.new("RGB", (8, 8), "green").save(candidate)

        with self.assertRaises(SheetError) as caught:
            finalize_codex_jobs(self.attempt, manifest_path, surface="desktop")

        self.assertIn("허용오차를 넘는다", str(caught.exception))
        self.assertTrue(candidate.exists())
        self.assertFalse(
            (self.attempt / "02-sheet/output/sheets/hero.png").exists())

    def test_small_provider_pixel_variance_is_normalized(self):
        source = Image.new("RGB", (995, 500), "green")

        image, fit = materialize_with_pixel_tolerance(source, (1000, 500))

        self.assertEqual(image.size, (1000, 500))
        self.assertEqual(fit, "tolerance-upscale-and-crop")

    def test_pixel_variance_beyond_one_percent_is_rejected(self):
        source = Image.new("RGB", (989, 500), "green")

        with self.assertRaises(SheetError) as caught:
            materialize_with_pixel_tolerance(source, (1000, 500))

        self.assertIn("allowed_deficit=10x5", str(caught.exception))

    def test_tampering_with_the_imagegen_render_request_stops_finalization(self):
        _, manifest_path, manifest = self.prepare()
        candidate = self.attempt / manifest["jobs"][0]["candidate_path"]
        candidate.parent.mkdir(parents=True)
        Image.new("RGB", (16, 9), "green").save(candidate)
        manifest["jobs"][0]["imagegen_prompt"] = "smaller preview"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        with self.assertRaises(SheetError) as caught:
            finalize_codex_jobs(self.attempt, manifest_path, surface="cli")
        self.assertIn("계약 크기/high 요청문", str(caught.exception))

    def test_force_archives_the_former_output_before_replacement(self):
        output = self.attempt / "02-sheet" / "output" / "sheets" / "hero.png"
        output.parent.mkdir(parents=True)
        Image.new("RGB", (16, 9), "red").save(output)
        old_digest = hashlib.sha256(output.read_bytes()).hexdigest()
        _, manifest_path, manifest = self.prepare(force=True)
        candidate = self.attempt / manifest["jobs"][0]["candidate_path"]
        candidate.parent.mkdir(parents=True)
        Image.new("RGB", (16, 9), "green").save(candidate)

        finalize_codex_jobs(self.attempt, manifest_path, surface="desktop")

        rejected = list((self.attempt / "02-sheet" / "rejected").glob("**/hero.png"))
        self.assertEqual(len(rejected), 1)
        self.assertEqual(hashlib.sha256(rejected[0].read_bytes()).hexdigest(), old_digest)
        self.assertNotEqual(hashlib.sha256(output.read_bytes()).hexdigest(), old_digest)

    def test_contract_drift_stops_finalization(self):
        _, manifest_path, manifest = self.prepare()
        candidate = self.attempt / manifest["jobs"][0]["candidate_path"]
        candidate.parent.mkdir(parents=True)
        Image.new("RGB", (16, 9), "green").save(candidate)
        contract_path = self.attempt / "01-premise" / "output" / "contract.json"
        changed = json.loads(contract_path.read_text(encoding="utf-8"))
        changed["duration_seconds"] = 90
        contract_path.write_text(json.dumps(changed), encoding="utf-8")
        self.assertNotEqual(Contract.load(self.attempt).digest,
                            manifest["contract"]["sha256"])

        with self.assertRaises(SheetError):
            finalize_codex_jobs(self.attempt, manifest_path, surface="cli")

    def test_a_manifest_cannot_write_outside_its_attempt(self):
        _, manifest_path, manifest = self.prepare()
        manifest["jobs"][0]["candidate_path"] = "../../outside.png"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        with self.assertRaises(SheetError):
            finalize_codex_jobs(self.attempt, manifest_path, surface="cli")


if __name__ == "__main__":
    unittest.main()
