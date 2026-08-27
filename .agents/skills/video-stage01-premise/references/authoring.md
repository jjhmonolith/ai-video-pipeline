# Stage 01 authoring contract

## Creative method

1. Preserve the user's instruction in `direction.verbatim`; write the production interpretation separately.
2. Identify medium, audience, platform intent, genre/tone, visible promise, narrative point of view, and success criteria.
3. Decide runtime from the brief. Use `fixed` only when exact duration is an actual contract; otherwise use a meaningful range or open policy.
4. Decide native generation frame and delivery frame separately. Set `orientation` to `landscape`, `portrait`, or `square` solely from width and height.
5. Define each initially known identity-critical subject in concrete visual terms without unrelated boilerplate.
6. State binding positive requirements, prohibited contradictions, allowed creative latitude, and safety or likeness boundaries.

## `content` shape

```json
{
  "direction": {
    "verbatim": "exact user direction",
    "interpretation": "production-specific reading",
    "audience_promise": "what the finished work delivers"
  },
  "research": [
    {"claim": "grounded production fact", "source": "source or supplied material", "use": "visible impact"}
  ],
  "runtime_contract": {
    "mode": "fixed | range | open",
    "target_seconds": 60,
    "min_seconds": 45,
    "max_seconds": 75,
    "reason": "creative/format reason"
  },
  "frame": {"width": 1344, "height": 768, "fps": 24, "orientation": "landscape"},
  "delivery_frame": {"width": 1920, "height": 1080, "fps": 24, "orientation": "landscape"},
  "subjects": [
    {
      "subject_id": "CHAR-01",
      "kind": "character",
      "purpose": "story/production purpose",
      "reference_required": true,
      "definition": {
        "identity": "stable identity",
        "appearance": "visible form/material/wardrobe",
        "invariants": ["must remain true"],
        "allowed_variation": ["may change"]
      }
    }
  ],
  "production_language": {
    "tone": "...",
    "visual_principles": ["..."],
    "sound_principles": ["..."]
  },
  "contract_clauses": [
    {"clause_id": "CL-01", "type": "required | prohibited | allowed", "text": "topic-specific rule", "reason": "..."}
  ],
  "success_criteria": ["observable finished-work criterion"]
}
```

For `fixed`, include only `target_seconds`; for `range`, include `min_seconds` and `max_seconds`; for `open`, explain the editorial stopping condition. Do not fill unused numeric fields with dummy values.

The Stage 01 critic must catch orientation contradictions, hardcoded legacy runtime, contaminating props or jargon, insufficient subject definitions, and clauses that accidentally turn contextual choices such as arm pose or camera movement into global law.
