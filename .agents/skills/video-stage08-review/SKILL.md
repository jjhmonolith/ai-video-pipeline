---
name: video-stage08-review
description: Perform Stage 08 evidence-backed review of the current master and every upstream receipt, including Stage 05.5 prompt refinement, while classifying defects, deciding internal release eligibility, and keeping external publishing authority separate. Use only when assigned `08-review` or recovery routes final-audit defects here.
---

# Video Stage 08 — Review

Read [references/authoring.md](references/authoring.md), all current upstream receipts and artifacts, the rendered master, the work order, and the shared [preserved insights](../video-pipeline-orchestrator/references/insights.md).

Act as final production QA with fresh eyes. Bind every conclusion to the current receipt hash and actual media evidence. Review contract fidelity, scenario/shot realization, reference consistency, motion, edit, sound, technical delivery, accepted defects, and safety or likeness boundaries.

For every defect, decide `fixed`, `rejected`, or `accepted` and state the authority and impact. Route a fix to the earliest owning stage through `$video-pipeline-recovery`; do not hide it in the report.

Separate internal `release_eligible` from external publishing permission. This pipeline sets `external_publish_authorized` to false unless a separate, explicit human release receipt actually exists. Fast-track never creates that receipt.
