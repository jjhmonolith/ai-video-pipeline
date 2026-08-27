# LLM-authored creative pipeline v3

Pipeline v3 replaces deterministic creative compilers with nine stage-specific Codex skills. The sequence includes `05.5-motion-prompt`, which turns approved start plates into final C01 prompts without reopening image QA. The active production entry point is `video-pipeline-orchestrator`; Python is an integrity and state machine, not a writer.

```text
user direction
  -> orchestrator work order
  -> stage LLM author
  -> deterministic integrity
  -> fresh-context LLM critic
  -> varied repair loop (max 10)
  -> receipt / configured gate
  -> next stage
```

The canonical architecture and complete regression insights are owned by:

- `.agents/skills/video-pipeline-orchestrator/references/architecture.md`
- `.agents/skills/video-pipeline-orchestrator/references/insights.md`
- `.agents/skills/video-pipeline-orchestrator/references/artifact-contract.md`

Each stage owns its creative schema in `.agents/skills/video-stage*/references/authoring.md`. The executable integrity contract is `src/ai_video_pipeline/v3/integrity.py`; orchestration is `src/ai_video_pipeline/v3/orchestrator.py`.

The previous hybrid implementation is preserved read-only at `archive/pipeline-v2-hybrid-2026-08-27/`. Other v2 documents and non-v3 Python modules remain compatibility/reference material and are not creative authority for new runs.

See `operations.md` for commands and state behavior.
