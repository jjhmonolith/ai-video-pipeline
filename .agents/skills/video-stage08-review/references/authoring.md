# Stage 08 authoring contract

## Review method

1. Hash and list every current upstream receipt, including `05.5-motion-prompt`. Do not cite stale or historical artifacts as the current production.
2. Inspect the master at beginning, every transition, representative action peaks, special-time passages, and ending; listen to the audio when present.
3. Compare the result with the Stage 01 promise and frame/runtime contract, Stage 03 progression, Stage 04 shots/time, Stage 05 references and plates, Stage 05.5 final C01 prompts, Stage 06 selected takes, and Stage 07 plan.
4. Record every material defect and disposition. A passed final review has no undisclosed material defect.
5. Decide internal release eligibility. Keep external publishing false absent an actual separate human authorization receipt.

## `content` shape

```json
{
  "stage_receipts": [
    {"stage_id": "01-premise", "path": "01-premise/receipt.json", "sha256": "..."}
  ],
  "master_video": "07-edit/output/master.mp4",
  "review_dimensions": [
    {"dimension": "contract_fidelity", "decision": "pass", "evidence": "..."},
    {"dimension": "visual_and_motion_quality", "decision": "pass", "evidence": "..."},
    {"dimension": "editorial_and_sound_quality", "decision": "pass", "evidence": "..."}
  ],
  "defects": [
    {
      "defect_id": "D-001",
      "class": "quality | safety | authority | contract",
      "evidence": "...",
      "owner_stage": "06-motion",
      "disposition": "fixed | rejected | accepted",
      "authority": "receipt or explicit reviewer"
    }
  ],
  "release_decision": {
    "release_eligible": true,
    "reason": "internal master decision",
    "external_publish_authorized": false,
    "human_release_receipt": null
  }
}
```

Include exactly one receipt entry for every upstream stage, including Stage 05.5, with its current file SHA-256. The critic confirms all evidence is current, every remaining defect is honestly disposed, and internal completion is not described as authority to upload or publish.
