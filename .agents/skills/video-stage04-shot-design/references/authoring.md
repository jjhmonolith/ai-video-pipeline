# Stage 04 authoring contract

## Directing method

For each approved scene:

1. Restate the scene's dramatic intent and POV in production terms.
2. Block entrances, exits, eyelines, positions, movement, interaction, and the state handed between events.
3. Define coverage logic: master/relationship/spatial proof/performance/emphasis/insert choices and why each is needed.
4. Group shots by setup, camera position, light continuity, and staging continuity.
5. Author shots that cover every Stage 03 event without mechanically forcing one event per shot.
6. Decide composition, frame size, angle, lens behavior if relevant, camera movement or lockoff, beginning and end framing, performance phases, reference dependencies, and exact temporal design.

## `content` shape

```json
{
  "scene_plans": [
    {
      "scene_id": "SC-01",
      "treatment": {
        "intent": "audience effect",
        "pov": "information/emotional alignment",
        "blocking": "spatial and performance blocking",
        "coverage_logic": "why this coverage proves the scene"
      },
      "setups": [
        {
          "setup_id": "SU-01",
          "camera_position": "physical relation to action",
          "lighting_continuity": "continuity plan",
          "shots": [
            {
              "shot_id": "SH-001",
              "event_ids": ["EV-001"],
              "purpose": "what this shot contributes",
              "composition": "single | two_shot | over_the_shoulder | insert | wide_group | other",
              "frame_size": "ECU | CU | MCU | MS | MLS | WS | EWS",
              "visible_cast_ids": ["CHAR-01", "CHAR-02"],
              "required_reference_subject_ids": ["CHAR-01", "CHAR-02", "NEW-PROP-01"],
              "start_state": "one coherent pre-action instant",
              "action_contract": "ordered visible action and allowed change",
              "end_state": "result after the action",
              "camera": {
                "movement": "locked | pan | tilt | dolly | truck | crane | handheld | orbit | other",
                "speed": "perceptual speed/easing",
                "framing": "opening framing and geometry",
                "end": "ending framing/settle",
                "angle": "height and horizontal/vertical angle",
                "lens_behavior": "perspective/depth behavior",
                "rationale": "scene-specific dramatic reason"
              },
              "performance": {
                "phases": [
                  {"phase": "anticipation", "action": "...", "readability": "..."},
                  {"phase": "execution", "action": "...", "readability": "..."},
                  {"phase": "settle", "action": "...", "readability": "..."}
                ]
              },
              "timing": {
                "edit_target_seconds": 4.5,
                "temporal_mode": "real_time | slow_motion | freeze | speed_ramp | orbit_time | time_lapse | discontinuous | other",
                "dramatic_reason": "why this duration and time treatment",
                "execution_method": "how generation/editing will realize it",
                "time_domains": {
                  "subject": "subject's experienced motion/time",
                  "world": "environmental time behavior",
                  "camera": "camera movement/time behavior"
                },
                "handles_seconds": 0.25
              },
              "included_in_timeline": true
            }
          ]
        }
      ]
    }
  ],
  "timeline_total_seconds": 60,
  "reference_gap_summary": ["NEW-PROP-01"]
}
```

Every source scene appears exactly once and every source event is covered by at least one shot. Shot IDs are unique. For a fixed Stage 01 runtime, the sum of `edit_target_seconds` for timeline shots must match that runtime; this arithmetic check does not choose the durations.

The critic assesses scene intention, coverage sufficiency, spatial clarity, two-person composition truth, technique rationale, timing and time-domain coherence, and whether Stage 05 can execute the plan without inventing missing visible states.
