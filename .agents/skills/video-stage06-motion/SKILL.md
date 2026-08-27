---
name: video-stage06-motion
description: Generate and review Stage 06 motion by submitting the approved Stage 05.5 prompt verbatim for C01, then creating C02–C10 only after visible failure of the immediately prior take with a distinct evidence-driven prompt strategy. Use only when assigned `06-motion` or recovery routes motion, continuity, or temporal-execution defects here.
---

# Video Stage 06 — Motion

Read [references/authoring.md](references/authoring.md), all upstream receipts and current artifacts, the work order, and the shared [preserved insights](../video-pipeline-orchestrator/references/insights.md). Use only the currently configured video-generation runtime; discover its supported interface from current local code and settings rather than hardcoding host, port, model, or credentials in this skill.

For each timeline shot, read the approved Stage 05.5 refinement and submit its `final_c01_prompt` verbatim for C01 with the exact bound Stage 05 start plate. Do not silently rewrite, shorten, expand, or normalize C01. Inspect the actual video and record evidence. Create C02 only if C01 failed, and continue sequentially at most to C10 with distinct positive prompt changes grounded in the immediately prior video's visible failure.

Stage 06 does not revalidate or regenerate the start plate and does not re-author the base C01 prompt. Do not pre-generate three takes or invent an end image as a hidden requirement. Preserve identity, visible count, topology, environment, lighting, and camera intent while repairing failed video behavior. Independent shots may be generated in parallel by subagents, but each shot's candidates are serial and the primary agent owns selection and the Stage 06 artifact.
