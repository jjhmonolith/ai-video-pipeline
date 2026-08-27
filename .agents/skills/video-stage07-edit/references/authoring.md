# Stage 07 authoring contract

## Editorial method

1. Map every Stage 04 timeline shot to the selected Stage 06 video.
2. Choose in/out points and edit seconds from performance readability, information flow, rhythm, transition handles, and temporal design.
3. Choose playback rate or a time-remapping curve only with an explicit editorial reason.
4. Specify transition, sound, music, ambience, dialogue, and information-layer intent as applicable.
5. Execute the plan with local deterministic media tooling, preserving source clips and commands/receipts.
6. Inspect the rendered master for order, pacing, continuity, special-time legibility, audio behavior, frame contract, and corruption.

## `content` shape

```json
{
  "timeline": [
    {
      "shot_id": "SH-001",
      "source_video": "06-motion/qa/attempts/A01/media/SH-001/C01.mp4",
      "source_in_seconds": 0.2,
      "source_out_seconds": 4.9,
      "edit_seconds": 4.5,
      "playback_rate": 1.0,
      "editorial_reason": "dramatic/information/rhythm reason",
      "temporal_fidelity": {
        "subject": "preserved or intentionally changed behavior",
        "world": "...",
        "camera": "..."
      },
      "transition": {"type": "cut", "reason": "..."},
      "sound_intent": "...",
      "information_layers": []
    }
  ],
  "sound_plan": {"dialogue": "...", "effects": "...", "ambience": "...", "music": "..."},
  "render": {"frame": {"width": 1920, "height": 1080, "fps": 24}, "codec": "..."},
  "output_video": "07-edit/output/master.mp4",
  "master_review": {"decision": "pass", "evidence": "actual rendered-master evidence"}
}
```

Timeline shot order must match Stage 04. Every source file and final output must exist. `edit_seconds` and `playback_rate` are positive. For fixed runtime, the timeline sum matches Stage 01 within the integrity tolerance.

The critic evaluates whether edit choices serve intent, temporal domains remain coherent, and the real master has sound, visual, pacing, and continuity quality—not merely whether an ffmpeg command succeeded.
