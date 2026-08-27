# Artifact and critique contract

## Stage artifact envelope

Write valid UTF-8 JSON at the exact `artifact_path` from the active work order.

```json
{
  "schema_version": "llm-stage-artifact.v1",
  "pipeline_version": "3.0",
  "stage_id": "<exact work-order stage>",
  "attempt_id": "<exact work-order attempt_id>",
  "authored_by": "<model/agent identity>",
  "authored_at": "<ISO 8601 timestamp>",
  "input_receipts": [],
  "creative_decisions": [
    {"decision": "...", "reason": "...", "evidence": "..."}
  ],
  "content": {}
}
```

Copy `input_receipts` byte-for-byte as JSON values from the work order. The stage-specific authoring reference defines `content`. Store actual creative language in the artifact: do not leave instructions, placeholders, `TBD`, or unexpanded templates.

## Media attempt chain

An image asset generated in Stage 02 or Stage 05 records a sequential chain:

```json
{
  "requested": [1672, 941],
  "selected_image": "02-sheet/qa/attempts/A01/media/SUBJ/A01.png",
  "selected_attempt": 1,
  "attempts": [
    {
      "attempt": 1,
      "variation_strategy": "base_contract_execution",
      "prompt": "the exact submitted image prompt",
      "candidate_path": "02-sheet/qa/attempts/A01/media/SUBJ/A01.png",
      "decision": "pass",
      "review": {"decision": "pass", "evidence": "visible, criterion-specific evidence"}
    }
  ]
}
```

Every retry follows a failed immediately preceding attempt, uses a distinct strategy and prompt, and preserves its own file. The selected attempt is the final attempt. `accepted_defect` is valid only for attempt 10 in explicit fast-track mode and must carry the remaining evidence.

## Fresh-context critique

After deterministic submission passes, write this JSON to the exact `critique_path`:

```json
{
  "schema_version": "llm-stage-critique.v1",
  "stage_id": "<stage>",
  "artifact_sha256": "<hash returned by submit>",
  "reviewer": "fresh-context LLM critic",
  "reviewed_at": "<ISO 8601 timestamp>",
  "summary": "concise evidence-backed conclusion",
  "decision": "pass",
  "criteria": [
    {"criterion_id": "<exact work-order id>", "status": "pass", "evidence": "concrete evidence"}
  ],
  "failure_classes": [],
  "accepted_defects": []
}
```

Use every criterion exactly once and in work-order order. A pass requires all criteria to pass. A fail needs at least one failed criterion and one or more failure classes from `quality`, `safety`, `authority`, or `contract`. A critic evaluates the candidate; it does not rewrite it in place.

For image and video artifacts, inspect the actual media at useful detail. Do not infer visual correctness from prompts or filenames. Cite visible count, identity, topology, spatial relation, text contamination, composition, start state, action order, continuity, or pixel issue as applicable.

Stage 05.5 is a prompt artifact whose claims still require visual inspection of the actual selected plate and bound references. Its recorded hashes prove which files were inspected; they do not replace visual evidence. Stage 06 C01 must reproduce the Stage 05.5 `final_c01_prompt` verbatim, while later prompts require failed-video evidence.
