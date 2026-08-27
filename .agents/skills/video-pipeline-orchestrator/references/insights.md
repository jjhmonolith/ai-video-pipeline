# Preserved production insights

These are regression rules learned from the automobile-review v1, Penthouse Minchae, and Penthouse v2 work. Apply the underlying principle to every new subject; do not copy topic-specific nouns into unrelated productions.

## Contract authority and contamination

- Orientation comes only from the current Stage 01 frame contract. Never inject `Vertical production plate` into a landscape job or a landscape clause into a portrait job.
- Topic vocabulary comes from the current direction, approved definitions, scenario, and shot design. Reject leaked boilerplate such as `tool bag`, `zipper`, or `visible tools` in an automobile production unless the current story genuinely introduced those objects.
- Do not turn a past prompt fragment into a universal rule. There is no global prohibition on spreading arms, no global command to move the camera, and no global command to lock it. Performance and camera behavior require scene-specific intent.
- A two-person frame cannot be semantically labeled `single`. Choose and describe a real two-person composition such as a two-shot or an over-the-shoulder/shoulder composition. If only one person is meant to be visible, bind only that person as visible cast.

## Stage 02 sheets

- Preserve the structured meta-prompt workflow. Python binds the exact Stage 01 definition, current clauses, canonical kind specification, sheet canvas, and required panel IDs in `input_contract`; the LLM authors `sheet_policy`, the complete `panel_plan`, and the final `image_prompt` without replacing them with an improvised flat prompt.
- Reference-sheet canvas and delivery canvas are different contracts. Stage 02 always uses the canonical `1672x941` 16:9 landscape production board, including for portrait or square video; never derive sheet orientation from the Stage 01 video frame.
- Preserve the complete canonical kind layout. Character, subject, and setting boards each carry nine information panels plus their specified internal view/item counts. A simplified board with roughly three hero images is not the original sheet format and must fail review.
- Generate one board candidate first. Review it against identity, count, panels, orientation, readability, and subject relevance. Only a failure creates the next varied candidate.
- Provider images may differ from requested pixels by a small amount. Accept per-axis variance within `max(1 px, min(16 px, 1% of target))` as a warning when orientation and visible quality are correct. Never enlarge a substantially smaller source and call it native.

## Scenario and shot design

- Runtime is a Stage 01 creative contract, not a hardcoded 45-second total and not a Stage 03 sum of mechanical beats.
- Stage 03 begins with sequence and scene intention: location/time, point of view, dramatic question, entry state, events, visible changes, and exit state. It must not prematurely decide lenses, camera motion, shot IDs, or exact shot seconds.
- Event density must fit the scene's plausible editorial range. A long list of incidents in too little time is not repaired by arbitrarily shrinking every beat.
- Stage 03 may invent story-motivated props, environments, wardrobe states, interfaces, or interaction systems that Stage 01–02 did not anticipate. Preserve the richer story and register each new visible dependency as `NEW-*` reference debt for Stage 05. Do not impoverish the scenario to the early board inventory.
- Stage 04 models actual production: scene treatment -> blocking -> coverage logic -> setups -> shots. It decides what the audience should perceive before choosing technique.
- Stage 04 owns exact shot time because duration depends on performance, information, camera travel, transition handles, and temporal technique. Special techniques may give subject, world, and camera different clocks; describe all three rather than forcing naive real-time duration.
- Choose camera movement or stillness for dramatic function, not variety quotas. Give every choice a rationale connected to point of view, revelation, spatial clarity, emphasis, or emotion.

## References and plates

- A passed Stage 04 flows directly into Stage 05. Do not stop immediately before Stage 05 asking for another approval.
- Stage 05A fulfills every reference debt and any interaction/manual need first. Review all reused and newly generated references in one global preflight.
- Only after the entire reference set passes may Stage 05B generate dependent start plates.
- Validate every plate with the same bound reference images as well as its shot contract. A prompt-only comparison is insufficient.
- Production creates one coherent pre-action start instant, not an end plate and not a collage of multiple times.
- Generate one plate, review it, and regenerate only after failure. Independent plate or reference jobs may run in parallel through subagents, but each job remains sequential internally and the primary agent performs global preflight and finalization.

## Motion and later stages

- Stage 05 is the sole plate-quality and regeneration harness. Once it selects a plate, Stage 05.5 must accept it and improve motion execution rather than duplicate image QA.
- Stage 05.5 inspects the actual plate and all bound references, then translates Stage 03–04 intent into an executable C01 prompt: opening transition, ordered action, performance, camera path or stillness, shooting-technique mechanics, subject/world/camera time, and ending state.
- Stage 05.5 may choose only `ready` or `ready_with_adaptation`. It creates no image or video, adds no human gate, and may not return a plate for regeneration.
- Stage 06 submits the approved Stage 05.5 prompt verbatim for C01. Its creative prompt authorship begins only after an actual video fails, using that visible evidence for C02–C10.
- Generate C01 first. C02 exists only if C01's recorded review failed; continue sequentially through at most C10. Never render C01–C03 up front from the same prompt.
- Every retry must materially vary the positive prompt or execution plan in response to the failed evidence while preserving approved identity and intent.
- Stage 07 treats Stage 04 timing as authored intent, not arbitrary metadata. If it retimes a clip, it states why and how subject/world/camera time remain legible.
- Stage 08 binds current receipt hashes. It separates `form_ok`, semantic/visual pass, human approval, release eligibility, and external publishing authority.

## Recovery behavior

- All generative stages use the same author -> deterministic integrity -> fresh-context critic -> varied retry harness.
- Ordinary defects do not stop the system while attempts remain. Route failures to the owning stage, preserve evidence, and continue.
- Fast-track is explicit and attempt-scoped. It removes internal approval pauses, not safety or external-authority boundaries.
