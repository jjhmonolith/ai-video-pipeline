# Pipeline v2 Hybrid Snapshot

- Snapshot date: 2026-08-27
- Status: read-only historical baseline
- Replaced by: LLM-authored creative pipeline v3

This directory preserves the complete active implementation immediately before
the v3 rebuild: Python sources, tests, contracts, documentation, examples,
project skills, `README.md`, and `pyproject.toml`.

The former root `build/`, `dist/`, and generated
`src/ai_video_pipeline.egg-info/` were moved into `build-artifacts/` after the
source snapshot so stale v0.1 package metadata cannot appear to be the active
v3 package. The original generated egg-info is also present inside the copied
`src/` tree as part of the exact source snapshot.

The snapshot deliberately excludes `runs/`, render media, `.venv`, caches, and
secrets. Production attempts remain at their original paths and are not changed
by the v3 rebuild.

Before the rebuild, recursive comparisons reported no differences between the
source and snapshot trees after excluding Python bytecode caches. The copied
root files had these SHA-256 values:

- `README.md`: `bca4551fc84bb9d5911f2270eacf7b62a013db2b49df4b942fb293d19bcd3c55`
- `pyproject.toml`: `1f42868cef126d73a28fe09b0c2ce304bede9adb447fc8328d77bf5c8100dbf4`

Restore by copying the desired files from this directory back to the repository
root. Do not combine v2 prompt authorship rules with v3 stage artifacts without
an explicit migration and revalidation.
