# Stage 05.5 authoring contract

## Purpose and authority

Stage 05 already decided whether a start plate is usable and performed every image retry. Do not repeat that judgment. Accept the selected plate and solve the downstream directing problem: how the approved still should become a coherent moving shot.

Preserve these ownership boundaries:

- Stage 03 owns the scene, event, dramatic function, and story state change.
- Stage 04 owns shot purpose, composition, performance contract, camera intent, shooting rationale, duration, and subject/world/camera time domains.
- Stage 05 owns reference approval, plate quality, plate selection, and image regeneration.
- Stage 05.5 owns the final C01 prompt grounded in the selected plate's actual visible state.
- Stage 06 owns video generation, take review, and C02–C10 prompt changes made from visible video-failure evidence.

Do not invent a new major event or change the scene outcome. You may add executable micro-actions, gaze shifts, weight transfer, hand preparation, environmental reactions, transition mechanics, or spatial staging that make the existing event readable from the actual plate.

## Per-shot method

1. Read the Stage 03 scene and events bound by the Stage 04 shot. Restate the shot's dramatic function and intended state change.
2. Inspect the selected start plate together with every reference listed on that plate. Record only what is visibly grounded: pose, gaze, hand occupancy, contact, left/right and depth relations, foreground occlusion, open movement paths, and camera/composition implications.
3. Choose `ready` when the intended execution can begin directly. Choose `ready_with_adaptation` when the same shot intent needs a different opening transition, micro-blocking, camera path, or technique because of the actual starting pose or composition. Neither value questions the plate's approval.
4. Design the visible execution: opening transition, ordered subject actions, performance progression, world response, camera movement or stillness, shooting-technique behavior, temporal treatment, and ending state.
5. Translate film terminology into generator-observable behavior. A technique name alone is insufficient: describe what the camera, subjects, foreground, background, and time domains visibly do.
6. Write one positive, coherent `final_c01_prompt`. It must begin from the observed plate, execute the authored event once, preserve bound identities and spatial invariants, and avoid commentary about the production process.

When the camera is locked, state what remains fixed and what moves within the frame. When it moves, describe path, direction, speed or acceleration, framing behavior, occlusion behavior, and ending. For slow motion, freeze time, orbit/bullet time, speed ramps, time lapse, or discontinuous time, preserve Stage 04's separate subject, world, and camera time domains instead of forcing naive real time.

## `content` shape

```json
{
  "shots": [
    {
      "shot_id": "SH-001",
      "scenario_context": {
        "scene_id": "SC-01",
        "event_ids": ["EV-001"],
        "dramatic_function": "what this shot makes the audience understand or feel",
        "entry_to_exit_change": "the story-state change completed by this shot"
      },
      "shot_intent": "Stage 04 purpose and directing intent preserved in plain language",
      "start_plate": "05-plate/qa/attempts/A01/media/plates/SH-001/A01.png",
      "start_plate_sha256": "sha256 of the inspected selected plate",
      "reference_bindings": [
        {
          "reference_id": "REF-CHAR-01",
          "path": "02-sheet/qa/attempts/A01/media/BOARD-CHAR-01/A01.png",
          "sha256": "sha256 of the inspected reference image"
        }
      ],
      "plate_observation": {
        "visible_start_state": "pose, gaze, expression, and immediately visible readiness",
        "spatial_relations": "left/right, depth, foreground/background, eyelines, and open paths",
        "contact_and_occupancy": "hands, held objects, contact points, and occlusion",
        "composition_and_motion_affordances": "what the framing allows the subjects and camera to do"
      },
      "realization_status": "ready_with_adaptation",
      "adaptation_reason": "why the actual plate calls for this execution; say no adaptation when ready",
      "motion_realization": {
        "opening_transition": "the first visible change from the exact still",
        "ordered_action_phases": [
          {"phase": "initiation", "action": "observable action", "visible_result": "observable state change"}
        ],
        "performance_direction": "gaze, expression, rhythm, weight, and gesture progression",
        "world_response": "environmental or object response, including an explicit stable-world choice",
        "camera_execution": "locked behavior or executable movement path and ending",
        "shooting_technique_translation": "the visible mechanics of the selected filmmaking technique",
        "temporal_execution": "subject/world/camera timing and any special time treatment",
        "ending_state": "the final readable visual state"
      },
      "continuity_constraints": [
        "identity, count, topology, lighting, environment, and story-specific invariants to preserve"
      ],
      "generator_translation": "how the current configured image-to-video runtime should receive the plan",
      "final_c01_prompt": "exact positive prompt Stage 06 must submit for C01",
      "refinement_rationale": "why this prompt is stronger for the actual plate than an abstract pre-plate prompt"
    }
  ]
}
```

`reference_bindings` must repeat the exact Stage 05 plate reference order and bind the actual file hashes. `event_ids` must match the Stage 04 shot contract exactly. Allowed `realization_status` values are only `ready` and `ready_with_adaptation`.

The critic must inspect the actual plate and references. It evaluates visual grounding, Stage 03–04 fidelity, directing quality, executable camera/technique/time language, and the Stage 05 authority boundary. It must not ask this stage to regenerate or reject an image.

