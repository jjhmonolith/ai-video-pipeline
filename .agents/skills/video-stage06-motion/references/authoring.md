# Stage 06 authoring contract

## Per-shot method

1. Read the Stage 04 shot contract, Stage 05 selected start plate and references, and Stage 05.5 refinement.
2. Copy `final_c01_prompt` from Stage 05.5 into C01 byte-for-byte as text. Stage 05.5 owns the base prompt.
3. Generate C01 and inspect the actual clip at beginning, key transition, and end. Review action order, identity/count, topology, continuity, composition, camera path, technique, and timing.
4. Only after a visible C01 failure, author C02 from that evidence. Keep successful invariants and change the positive prompt or execution plan using a distinct strategy. Continue the same way for later candidates.
5. Stop on the first pass. In explicit fast-track only, C10 may be retained with recorded non-safety quality defects.

## `content` shape

```json
{
  "shots": [
    {
      "shot_id": "SH-001",
      "start_plate": "05-plate/qa/attempts/A01/media/plates/SH-001/A01.png",
      "selected_candidate": "C01",
      "candidates": [
        {
          "candidate_id": "C01",
          "variation_strategy": "base_contract_execution",
          "prompt": "exact motion prompt",
          "video_path": "06-motion/qa/attempts/A01/media/SH-001/C01.mp4",
          "runtime_settings": {"provider": "current configured runtime", "parameters": {}},
          "review": {
            "decision": "pass",
            "evidence": "visible action, continuity, camera, and time-domain evidence"
          }
        }
      ]
    }
  ],
  "cross_shot_review": {
    "decision": "pass",
    "evidence": "identity, screen direction, lighting, movement, and temporal continuity"
  }
}
```

Candidate IDs are contiguous from C01. C01's prompt must exactly equal the Stage 05.5 `final_c01_prompt`. Every candidate after C01 requires the immediately prior review to be `fail`, and every retry strategy is distinct. The selected candidate is the final generated candidate and must be `pass` or an authorized C10 `accepted_defect`.

The critic watches the media rather than trusting prompts. It checks that the authored event occurs once in order, the start plate remains the true starting state, time treatment is legible, and no continuity or unrelated-subject contamination appears.
