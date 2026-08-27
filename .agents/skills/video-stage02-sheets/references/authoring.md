# Stage 02 authoring contract

## Canonical board contract

Stage 02 reference boards do not inherit the video's aspect ratio. Every board uses:

```json
{
  "purpose": "reference_board",
  "width": 1672,
  "height": 941,
  "orientation": "landscape",
  "aspect_ratio": "16:9",
  "quality": "high",
  "independent_of_video_frame": true
}
```

Read exactly one complete kind specification for each work-order input:

- `character`: [canonical character board specification](../../../../src/ai_video_pipeline/sheet_specs/character.md)
- `subject`: [canonical object/subject board specification](../../../../src/ai_video_pipeline/sheet_specs/subject.md)
- `setting`: [canonical environment board specification](../../../../src/ai_video_pipeline/sheet_specs/setting.md)

These specifications restore the original dense production sheet. Each has nine canonical information panels. Several panels contain fixed internal counts such as three accessory close-ups, five turnaround views, four material studies, six head/detail views, eight palette swatches, six environment angles, or six mood variations. A board with roughly three large images is incomplete even if those images are attractive.

## Board method

For each required Stage 01 subject:

1. Copy the matching `stage_inputs.boards[]` object from the work order into `input_contract` exactly. It contains the complete writer rules and canonical kind specification as well as their hashes. Never reconstruct, summarize, shorten, or edit it.
2. Read `source_definition` as authoritative. The kind specification fills only facts the definition leaves open; it cannot replace appearance, construction, wardrobe, material, color, scale, or identity facts already decided in Stage 01.
3. Apply every `contract_clauses` item exactly. Do not leak clauses or topic nouns from another production.
4. Author a `sheet_policy` that states purpose, neutral/reference background, consistency, layout logic, labeling policy, and what the board must prove.
5. Author one `panel_plan` record for every `required_panel_ids` entry, in the declared order. Each record gives its production purpose and non-empty `must_show` requirements derived from the complete kind specification. Do not collapse or merge panels.
6. Compose the exact English `image_prompt` from the complete input contract, sheet policy, nine-panel plan, and fixed subview/item counts. The prompt must request the finished board itself without explanation or code fences.
7. Record deterministic hashes after the prose and panel plan are complete. Python may calculate hashes but must not write or rewrite the creative fields.
8. Generate A01 at `1672x941` landscape and high quality, regardless of the video frame.
9. Inspect the actual pixels for all nine panels, their required subviews/items, identity, orientation, readability, and contamination. Retry only after a visible failure, using the work-order variation sequence and failure evidence.

Use the canonical specification's section headings and numbering, keep descriptive text short, and never replace a required visual panel with prose. Do not accept a board because its prompt was correct; inspect the rendered image.

## `content` shape

```json
{
  "boards": [
    {
      "board_id": "BOARD-CHAR-01",
      "subject_id": "CHAR-01",
      "structured_meta_prompt": {
        "schema_version": "reference-board-meta-prompt.v2",
        "input_contract": {
          "schema_version": "stage02-reference-board-input.v2",
          "writer_protocol": "full-structured-reference-board-writer.v2",
          "writer_rules": "complete writer rules supplied by the work order",
          "writer_rules_sha256": "computed",
          "subject_id": "CHAR-01",
          "subject_kind": "character",
          "source_definition": {"identity": "exact Stage 01 definition"},
          "source_definition_sha256": "computed",
          "contract_clauses": [],
          "contract_clauses_sha256": "computed",
          "canvas_contract": {
            "purpose": "reference_board",
            "width": 1672,
            "height": 941,
            "orientation": "landscape",
            "aspect_ratio": "16:9",
            "quality": "high",
            "independent_of_video_frame": true
          },
          "spec_path": "src/ai_video_pipeline/sheet_specs/character.md",
          "sheet_specification": "complete canonical character specification supplied by the work order",
          "spec_sha256": "computed",
          "required_panel_ids": [
            "HERO_FULL_BODY",
            "DETAILED_ACCESSORIES",
            "FULL_BODY_TURNAROUND",
            "COSTUME_EQUIPMENT",
            "MATERIAL_REFERENCE",
            "CHARACTER_NOTES",
            "COLOR_PALETTE",
            "HEAD_STUDY",
            "EXPRESSION_STUDY"
          ],
          "input_contract_sha256": "computed"
        },
        "sheet_policy": {
          "purpose": "...",
          "background": "...",
          "consistency": "...",
          "layout_logic": "...",
          "labeling_policy": "...",
          "proof_goal": "..."
        },
        "panel_plan": [
          {"panel_id": "HERO_FULL_BODY", "purpose": "...", "must_show": ["..."]},
          {"panel_id": "DETAILED_ACCESSORIES", "purpose": "...", "must_show": ["exactly three close-ups"]}
        ],
        "meta_prompt_sha256": "computed from input_contract + sheet_policy + panel_plan",
        "image_prompt": "exact positive prompt sent for A01",
        "image_prompt_sha256": "computed"
      },
      "requested": [1672, 941],
      "selected_image": "02-sheet/qa/attempts/A01/media/BOARD-CHAR-01/A01.png",
      "selected_attempt": 1,
      "attempts": [
        {
          "attempt": 1,
          "variation_strategy": "base_contract_execution",
          "prompt": "exact positive prompt sent for A01",
          "candidate_path": "02-sheet/qa/attempts/A01/media/BOARD-CHAR-01/A01.png",
          "decision": "pass",
          "review": {"decision": "pass", "evidence": "visible identity/panel/count/orientation evidence"}
        }
      ]
    }
  ],
  "cross_board_review": {
    "decision": "pass",
    "evidence": "identity and production-language consistency across selected boards"
  }
}
```

The abbreviated two-panel excerpt above only shows field shape. The actual `panel_plan` must contain all nine IDs from the work-order input contract.

For retries, keep the original input contract, sheet policy, and complete panel plan. A01 uses `image_prompt` verbatim. A02–A10 may revise only the attempt prompt in response to visible failure evidence while preserving the full board contract. `selected_image` equals the final selected attempt's `candidate_path`.

The critic looks for full subject coverage, exact structured-prompt provenance, all nine visible canonical panels, the kind specification's fixed subview/item counts, coherent identity, readable production reference value, fixed landscape reference-board orientation, and absence of unrelated fixed phrases such as old tools, clothing, or platform jargon.
