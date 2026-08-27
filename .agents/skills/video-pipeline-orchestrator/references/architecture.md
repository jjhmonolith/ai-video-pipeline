# Pipeline v3 architecture

## Division of responsibility

The production system has three distinct actors:

1. A stage-author LLM reads upstream receipts and makes the creative decisions owned by the current stage.
2. Deterministic Python checks only structure and integrity: required fields, types, IDs, hashes, file existence, pixel tolerance, time arithmetic, receipt freshness, retry order, state transitions, and authority boundaries.
3. A fresh-context LLM critic evaluates meaning and visible quality against the work order's exact rubric. It must cite evidence and must not silently repair the artifact it reviews.

Python must never select a plot, prop, composition, camera move, acting beat, image wording, shot duration, transition, or aesthetic. A validator may say that a rationale or duration is missing; it may not supply one.

## Stage ownership

| Stage | LLM-owned decision | Primary output |
|---|---|---|
| 01 Premise | direction interpretation, production contract, runtime policy, subjects, clauses | creative production contract |
| 02 Sheets | structured meta-prompts, panel design, image prompts, reviewed identity references | reference boards |
| 03 Scenario | sequence, scene, event, dramatic intent, incident density, reference debt | scenario design |
| 04 Shot design | blocking, coverage, setup, shot, composition, camera, performance, exact editorial time | shootable plan |
| 05 Plates | new reference sheets/manuals, global reference approval, start-state prompts and plates | approved references and start plates |
| 05.5 Motion prompt | plate-aware scenario, action, performance, camera, technique, and time translation | approved final C01 prompts |
| 06 Motion | verbatim C01 execution, then video-evidence-driven retry prompts and one reviewed take at a time | selected motion takes |
| 07 Edit | trims, retiming, order, transitions, sound and information-layer intent | assembled master |
| 08 Review | evidence-backed defects and release eligibility | review and release decision |

## Continuous control loop

```text
work order
  -> stage author writes one candidate
  -> deterministic integrity check
       fail -> next varied author attempt
       pass -> fresh-context critic
                   fail -> next varied author attempt
                   pass -> configured gate or receipt
  -> next stage
```

Each stage candidate lives in `<stage>/qa/attempts/A01..A10/`. A sealed artifact is copied to `<stage>/output/stage-artifact.json`, and its immutable inputs and outcome are recorded in `<stage>/receipt.json`.

The orchestrator is the only component that advances state. Stage skills write artifacts and media; critics write critiques. Image subagents may produce independent media candidates but do not update shared pipeline state or seal receipts.

## Retry policy

Use at most ten attempts for every generated design, prompt, sheet, reference, plate, motion take, edit plan, and review artifact. Attempt 1 executes the base contract. Every later attempt must respond to the immediately preceding evidence with a distinct strategy. Stop generating after a pass; never pre-generate three similar options.

The ordered strategies are stored in `src/ai_video_pipeline/v3/specs.py`. Apply the strategy to the positive construction of the artifact. Keep the upstream contract and successful invariant details stable while changing the failing decision or prompt structure.

At attempt 10:

- normal mode returns to a human gate;
- fast-track may retain attempt 10 only when the remaining issues are classified solely as non-safety quality defects and are explicitly recorded;
- safety, authority, or irreconcilable contract defects never auto-pass.

## Gate topology

Normal mode gates after Stage 01, Stage 05, Stage 06, Stage 07, and Stage 08. Stage 04 never waits before Stage 05: references and plates are the reviewable Stage 05 result. Stage 05.5 has no human gate; once Stage 05 is sealed it refines C01 prompts and flows directly into Stage 06. Fast-track skips internal human gates only when explicitly selected for the attempt.

## Plate-to-motion ownership

Stage 05 is the only owner of start-plate acceptance and image regeneration. Stage 05.5 assumes those selected pixels are production-usable and may return only `ready` or `ready_with_adaptation`; it improves execution rather than reopening image QA. Stage 06 must use the Stage 05.5 prompt verbatim for C01. Only an observed failed video take authorizes Stage 06 to write a changed C02–C10 prompt.

All publishing and other external side effects remain unauthorized by pipeline mode. Stage 08 can declare an internal master release-eligible but cannot manufacture external publishing authority.

## Temporal ownership

Stage 01 owns the runtime contract: fixed, range, or open. It is not globally fixed to 45 seconds. Stage 03 estimates scene editorial ranges only to test whether incident density is plausible. Stage 04 owns every shot's exact edit target and its subject/world/camera time domains, including slow motion, speed ramps, freeze time, bullet time, 3D orbital observation, time lapse, or discontinuous time. Stage 07 may trim and retime only with an editorial rationale that preserves the Stage 04 intent and satisfies a fixed runtime when one exists.
