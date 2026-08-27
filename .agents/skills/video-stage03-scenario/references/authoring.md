# Stage 03 authoring contract

## Dramatic method

1. Define the sequence-level movement: what changes across several scenes and why the sequence exists.
2. For each scene, define location/time, intention, role in the whole, POV owner, dramatic question, entry state, and exit state.
3. Break the scene into causal dramatic events. Each event has an action, visible change, and result state; it is not yet a shot.
4. Estimate an honest editorial range for the scene and compare incident density with audience comprehension, performance, spatial setup, and emotional change.
5. Register new visible assets or interaction systems at the scene that first requires them.

## `content` shape

```json
{
  "sequences": [
    {
      "sequence_id": "SEQ-01",
      "intent": "sequence-level purpose and progression",
      "entry_state": "...",
      "exit_state": "...",
      "scenes": [
        {
          "scene_id": "SC-01",
          "slugline": "INT./EXT. LOCATION — TIME",
          "intent": "what the scene should make the audience experience",
          "role": "why it exists in the whole work",
          "pov_owner": "whose information/emotion organizes the scene",
          "dramatic_question": "question carried through the scene",
          "entry_state": "visible/narrative state at entry",
          "exit_state": "changed state at exit",
          "estimated_edit_range_seconds": [8, 14],
          "density_reasoning": "why this event load fits that range",
          "events": [
            {
              "event_id": "EV-001",
              "action": "dramatic action, not camera instruction",
              "actor_subject_id": "CHAR-01",
              "target_subject_id": "NEW-PROP-01",
              "visible_change": "what visibly changes",
              "result_state": "state handed to the next event"
            }
          ],
          "production_requirements": [
            {
              "requirement_id": "NEW-PROP-01",
              "name": "story-motivated prop",
              "asset_class": "prop | environment | wardrobe | interface | interaction_manual | other",
              "description": "visible identity/state/topology needed",
              "reference_policy": "new_sheet | interaction_manual | reference_image | prompt_only | none",
              "needed_by_event_ids": ["EV-001"]
            }
          ]
        }
      ]
    }
  ],
  "global_progression": "how sequence and scene exits accumulate",
  "reference_debt_summary": ["NEW-PROP-01"]
}
```

Use globally unique sequence, scene, event, and requirement IDs. If an event targets `NEW-*`, the same scene must declare that requirement. Do not include `camera`, `lens`, `shot_id`, `cut_id`, or `edit_target_seconds` fields.

The critic asks whether events form meaningful causal progression, whether the amount of incident can be understood in the estimated range, whether scene intent is clear enough for a director, and whether new assets are honestly preserved as reference debt.
