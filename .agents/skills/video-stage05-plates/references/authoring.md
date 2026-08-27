# Stage 05 authoring contract

## Phase 5A — reference fulfillment

Create one `references` record for every reused Stage 02 board and every newly generated reference sheet or interaction manual. Bind each record to a Stage 01 subject ID or Stage 03 `NEW-*` requirement ID.

For a reused board, record `origin: stage02`, its existing selected image, requested size, and a current visual review. For a new asset, record `origin: stage05`, a structured generation specification, and the complete sequential attempt chain. Interaction manuals should visually prove topology, contact points, pre-contact/contact/post-contact states, and occlusion risks needed by the shots; panel design remains LLM-authored for the actual interaction.

When all unique references pass, write `global_reference_preflight` with the exact complete set of `reference_ids`, cross-reference consistency evidence, and `decision: pass`. Record `references_completed_at`. Do not begin a plate before this point.

## Phase 5B — start plates

For each Stage 04 timeline shot:

1. Resolve every `required_reference_subject_id` to an approved reference record.
2. Compose the image prompt from the shot's start state, composition, visible cast, environment, lens/framing behavior, lighting continuity, and bound references.
3. Depict a single coherent instant immediately before the authored action. Do not combine before/action/after and do not create an end plate.
4. Generate A01, inspect the image against all bound references and the shot contract, and retry only after failure.

## `content` shape

```json
{
  "references": [
    {
      "reference_id": "REF-CHAR-01",
      "subject_or_requirement_id": "CHAR-01",
      "origin": "stage02",
      "purpose": "identity reference",
      "requested": [1672, 941],
      "selected_image": "02-sheet/qa/attempts/A01/media/BOARD-CHAR-01/A01.png",
      "review": {"decision": "pass", "evidence": "current visible review"}
    },
    {
      "reference_id": "REF-NEW-PROP-01",
      "subject_or_requirement_id": "NEW-PROP-01",
      "origin": "stage05",
      "purpose": "interaction topology and states",
      "structured_meta_prompt": {
        "definition": "...",
        "reference_policy": "interaction manual",
        "panel_plan": ["..."],
        "image_prompt": "A01 prompt"
      },
      "requested": [1672, 941],
      "selected_image": "05-plate/qa/attempts/A01/media/references/REF-NEW-PROP-01/A01.png",
      "selected_attempt": 1,
      "attempts": [
        {
          "attempt": 1,
          "variation_strategy": "base_contract_execution",
          "prompt": "exact reference prompt",
          "candidate_path": "05-plate/qa/attempts/A01/media/references/REF-NEW-PROP-01/A01.png",
          "decision": "pass",
          "review": {"decision": "pass", "evidence": "visible reference evidence"}
        }
      ],
      "review": {"decision": "pass", "evidence": "selected reference is production-usable"}
    }
  ],
  "global_reference_preflight": {
    "reference_ids": ["REF-CHAR-01", "REF-NEW-PROP-01"],
    "decision": "pass",
    "evidence": "identity, material, geometry, topology, and state consistency"
  },
  "references_completed_at": "2026-08-27T12:00:00+09:00",
  "plates_started_at": "2026-08-27T12:00:01+09:00",
  "plates": [
    {
      "shot_id": "SH-001",
      "role": "start",
      "end_plate": null,
      "reference_ids": ["REF-CHAR-01", "REF-NEW-PROP-01"],
      "requested": [1344, 768],
      "selected_image": "05-plate/qa/attempts/A01/media/plates/SH-001/A01.png",
      "selected_attempt": 1,
      "attempts": [
        {
          "attempt": 1,
          "variation_strategy": "base_contract_execution",
          "prompt": "exact start-plate prompt",
          "candidate_path": "05-plate/qa/attempts/A01/media/plates/SH-001/A01.png",
          "decision": "pass",
          "review": {"decision": "pass", "evidence": "shot and reference comparison"}
        }
      ]
    }
  ]
}
```

All timestamps are real ISO 8601 observations. The critic must inspect reference images before plates, then inspect each plate with every bound reference. Small pixel variance is a warning inside tolerance; content, orientation, identity, count, topology, and start-state errors remain failures.

A selected plate is Stage 05's final image decision. Do not pass a knowingly material plate defect downstream for prompt compensation. After Stage 05 passes, Stage 05.5 may describe `ready_with_adaptation` to improve how motion begins from the approved pixels, but it cannot reject or regenerate the plate.
