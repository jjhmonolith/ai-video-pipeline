---
name: video-pipeline-recovery
description: Recover a failed v3 production artifact by routing evidence to its owning LLM stage, preserving upstream authority, applying the next distinct retry strategy, and continuing through at most ten attempts. Use for deterministic validation failures, semantic or visual critic failures, stale inputs, and interrupted attempts.
---

# Video Pipeline Recovery

Read [references/routing.md](references/routing.md), then read the active work order and the owning stage skill. Recovery does not invent creative output itself; it gives the owning stage a bounded, evidence-backed repair target.

## Recover

1. Load `pipeline-state.json` and identify `current_stage`, latest attempt, last feedback, and exact upstream receipts.
2. Classify each failure as `integrity`, `quality`, `safety`, `authority`, or `contract`. Keep the validator's original code and the critic's visible evidence.
3. If the failure was caused by stale or changed upstream input, do not patch the downstream artifact. Invalidate only the dependent path and return to the earliest owning stage.
4. Otherwise request the next work order. Confirm its attempt number is contiguous and its variation strategy differs from every earlier retry for that artifact.
5. Send the evidence and strategy to the owning stage skill. Preserve successful details and source authority; change the positive construction that caused the failure.
6. Run deterministic validation and fresh-context criticism again. Continue while attempts remain.

Do not convert a visible-quality judgment into a brittle keyword rule. Do not weaken orientation, identity, reference, timing, or external-authority contracts merely to make a validator pass.

At attempt 10, follow the orchestrator mode. Normal returns to a human gate. Explicit fast-track may retain only recorded non-safety quality defects. Stop on safety, authority, or irreconcilable contract failure.
