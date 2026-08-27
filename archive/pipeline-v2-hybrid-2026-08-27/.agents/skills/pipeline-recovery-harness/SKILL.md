---
name: pipeline-recovery-harness
description: Run this project's premise, prompt, sheet, scenario, shot-design, manual, and plate generation as a continuous validate-repair-regenerate workflow with up to ten varied attempts per artifact. Use when executing or repairing the production pipeline; stop only for a true authority, safety, or irreconcilable-contract boundary.
---

# Pipeline Recovery Harness

Keep the pipeline moving through recoverable generation and validation failures.
Use the runner-owned `adaptive-generation-harness.v1` metadata and the
stage-specific skills; never replace a compiler-authored artifact with an ad-hoc
prompt or silently weaken a contract.

## Execution mode

At the start of every attempt, read its mode before doing stage work:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m ai_video_pipeline.execution_mode \
  ATTEMPT show
```

No record means `normal`. Normal is always the default and preserves every
declared intermediate human gate. Never infer fast-track mode from urgency,
phrases such as "continue", or a previous attempt. Set it only when the user
explicitly requests fast-track/autonomous end-to-end operation:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m ai_video_pipeline.execution_mode \
  ATTEMPT set fast_track --by user --reason "exact explicit request summary"
```

In `fast_track`, do not ask for any intermediate pipeline approval. The AI
completes and applies internal review packets, records its evidence and reviewer
identity, and immediately continues to the next stage. After the tenth varied
attempt, it may mark only non-safety quality criteria as `accepted_defect`, keep
the tenth artifact, and continue. Fast-track does not authorize publishing,
messages, purchases, new credentials, destructive actions, or bypassing safety
and permission boundaries.

## Shared loop

For every generated definition, prompt, design, sheet, manual, or plate:

1. Generate one attempt from the current official source contract.
2. Run the artifact's form and semantic checks immediately and record concrete
   failed criteria and evidence.
3. On pass, stop retrying that artifact and continue automatically to the next
   artifact or stage. Do not pause for a progress summary or confirmation.
4. On a recoverable failure, preserve the source contract, feed only the failed
   criteria and evidence into the next attempt, and apply that attempt's declared
   variation strategy. Generate one new attempt and repeat.
5. Use at most ten total attempts per artifact across fresh manifests and
   upstream repair round trips. Attempt numbers and evidence must not reset just
   because a manifest was re-prepared.
6. After attempt 10, retain the tenth artifact and full ledger. In normal mode,
   report the unresolved production defect at the next genuine human gate. In
   fast-track, record non-safety failures as accepted defects and continue to
   the next safe job or stage without pausing.

The ten ordered strategies are: base execution, positive restatement,
constraint-priority reordering, identity/count locking, spatial composition,
physical contact/topology, camera/light/visibility, temporal state boundary,
contradiction removal, and minimal rebuild around failed criteria. Never reuse
an earlier strategy for a later attempt.

## Automatic repair routing

- Stage 01 definition failure: rerun `premise propose` with the validator
  findings. Preserve direction and evidence facts.
- Stage 02 prompt failure: rerun the deterministic structured composer. Repair
  the bound meta-prompt or source definition; never handwrite a replacement
  image prompt.
- Stage 02 image failure: use `sheet-imagegen` and its recorded AI-attempt
  command. A stale pack or manifest is repaired/re-prepared automatically.
- Stage 03 scenario failure: feed `scenario.check` findings into the next text
  generation. Preserve sequence→scene→event ownership and scene-level pacing;
  never repair it by inventing shot boundaries or exact shot seconds. Existing
  Stage-02 reference failure returns to Stage 02. A valid new story element is
  recorded as reference debt for Stage 04/5A instead of being deleted.
- Stage 04 design failure: route each finding to its owning source. Repair
  scenario structure in Stage 03; regenerate the LLM directorial treatment,
  setup/shot coverage, creative timing or temporal execution plan in Stage 04;
  repair only frame-grid, prompt assembly and receipt structure in the
  deterministic compiler. Route existing canonical references to Stage 02 and
  new story-owned reference debt to Stage 5A. Then recompile and recheck. Never
  ask the user to approve an intermediate recompile.
- Stage 05 reference, manual, or plate failure: use `plate-imagegen`. Complete
  5A reference-debt/manual generation and the full global reference wave before
  any 5B start image, then retry each image sequentially with its declared strategy.
- Stage 06 motion failure: C01 is the only initial take. Append exactly one
  differently varied retry after each review failure, up to C10. C-numbers are
  takes of one shot, never alternate angles or an upfront best-of-N batch.
- Minor provider pixel variance within the runner tolerance is normalized and
  recorded. Larger pixel failure is an image retry, not a user pause.

Contract or receipt drift is normally recoverable: discard the stale work order,
run the official upstream compiler, prepare a fresh manifest, and continue while
preserving the cross-manifest attempt count.

## Real stop conditions

Stop only when continuing would require one of these:

- user-authored direction that does not exist;
- a new permission, external side effect, or safety authorization;
- a required human approval while the attempt is in normal mode;
- a contract whose requirements are mutually impossible and cannot be repaired
  from existing authoritative inputs.

An unavailable provider or tool is retried only within the same ten-attempt
budget. Ordinary semantic failure, stale hashes, missing generated derivatives,
pixel mismatch, an invalid prompt pack, or an upstream artifact owned by this
pipeline are not reasons to stop and ask for confirmation.

In fast-track, an internal G1-G10 judgment packet or start-plate promotion is
not a stop condition: resolve it as `ai_fast_track`, preserve the original gate
IDs and evidence, apply the result, and continue. G10 does not grant external
release authority; preparing a release artifact is internal, publishing it is
an external side effect and remains disabled.

## Handoff behavior

Move from one successful stage to the next in the same task. Commentary may
report compact progress, but it must not become an approval request. At the end,
report passes, retained tenth attempts, repaired upstream artifacts, accepted
defects, and—only in normal mode—the single next genuine human gate, if one
exists.
