# Stage 4 interaction-manual design and Seedance 2.5 script review

Date: 2026-08-26  
Status: promoted into the stage-04 compiler; stage-05 rendering remains to be implemented

## Decision

The production conditioning package is:

1. every relevant approved canonical stage-02 sheet;
2. one approved stage-05 start plate;
3. an approved clean interaction-manual board when stage 04 says the action is not self-explanatory;
4. the stage-04 H3 prompt with explicit asset-role binding;
5. no H3 last frame in production.

A supplemental board never replaces a canonical stage-02 sheet. It explains
how already-defined things interact; it cannot redesign them.

## New stage-04 substep

For every shot, stage 04 now performs the following sequence before stage 05:

1. Decide whether canonical sheets plus one start plate can explain the action.
2. Record `required` or `not_required`, reasons, and mandatory human review.
3. If required, select `mechanical_interaction`, `assembly_sequence`,
   `articulated_mechanism`, or a mixed set of separately specified manuals.
4. Bind the canonical subject ids and the stage-03 interaction contract.
5. Define at least six panels, at least three truthful views, and at least
   three observable states.
6. Write the clean-board image-generation prompt.
7. Write a deterministic annotated-QA overlay specification.
8. Block rendering if part ids, dimensions, fit, axis, fixed/moving parts, or
   result state are unresolved.
9. Block H3 until the clean and annotated boards pass AI and human review.

### Automatic proposal triggers

`mechanical_interaction` is proposed for explicit interaction contracts or
non-obvious tool/fastener actions such as gripping, loosening, tightening,
wrapping, disassembly, and reassembly.

`articulated_mechanism` is proposed when a valve, architectural panel, hinge,
rail, lever, gear, lock, or similarly non-obvious assembly visibly opens,
closes, rotates, slides, locks, or changes configuration. Familiar actions such
as an ordinary zipper or door do not trigger a manual by themselves.

`assembly_sequence` is proposed for wrapping, insertion, alignment, mating,
assembly, and disassembly where ordered interface states matter but inventing a
professional tool-capacity contract would be wrong.

Walking, gaze, ordinary gestures, and other actions that are already legible
from the canonical sheets and start plate default to `not_required`. The human
stage-04 gate may override either proposal.

## Interaction-manual assets

Stage 05 creates two assets from one approved underlying render:

- `clean_board`: sent to H3; no labels, arrows, numbers, dimension text, logos,
  or watermarks;
- `annotated_qa_board`: never sent to H3; deterministic overlays show part ids,
  axes, contact points, force or torque, fixed/moving parts, dimensions, and
  forbidden geometry.

The mechanical six-panel minimum is:

1. structure overview and relative scale;
2. view directly along the target axis;
3. orthographic action-plane view;
4. engaged contact close view;
5. mid-actuation view with handle/limb sweep;
6. matched resolved state.

The articulated-mechanism minimum is:

1. full assembly overview;
2. hinge/axis/rail/track view;
3. exact start state;
4. early state;
5. mid state;
6. matched resolved state.

The assembly-sequence minimum is:

1. participating parts and mating interfaces;
2. orthographic interface/axis view;
3. correctly aligned start;
4. first engagement;
5. ordered mid-assembly state;
6. matched resolved assembly.

All panels must preserve identity, topology, dimensions, material, and part
count. Mechanical truth overrides a visually flattering hero angle.

## Video script reviewed

Source: [You're Prompting SEEDANCE 2.5 Like a BEGINNER (and How to Level Up)](https://www.youtube.com/watch?v=gXheMclvn3c).
The review used the page's English auto-generated transcript, so model and
product names mistranscribed by captions were interpreted from the video title.

The creator progresses through four levels:

- one reference image plus a natural-language request;
- an accurate multi-angle product sheet plus shot-specific product images;
- a formula such as subject, action, background, camera, and style;
- a fully structured workflow that builds the assets, concept, and prompt
  together and binds each asset to the prompt.

The script reports that a single-sided product image caused asymmetric controls
to be invented on both sides. Adding an accurate product sheet and specific
shot/angle images improved shot control and product consistency. Adding more
characters, settings, and actions without proportionally more constraints
created random shots and damaged product details. The complete workflow then
adds structured prompts, linked assets, and optional storyboards, previs,
video references, and post-production.

These are creator demonstrations on Seedance 2.5, not controlled evidence for
MiniMax H3. We therefore use them as design hypotheses only and keep our H3
blind tests as the deciding evidence.

## Items adopted into this pipeline

### Stage 2

- Keep accurate multi-angle canonical sheets, including asymmetric and
  side-specific details.
- Every relevant canonical sheet must reach both stage 05 and H3. Selective
  crops and supplemental manuals are additive, never substitutes.
- A sheet that does not reveal the functional side, interface, or articulation
  is incomplete even when its hero image looks correct.

### Stage 3

- `subject + action + background + camera + style` is not sufficient once a
  shot contains multiple actors, parts, or actions.
- Complex beats need explicit sub-beats and interaction contracts: exact tool
  part, target part, fixed/moving parts, fit, axis, force/result, and forbidden
  geometry.
- Interaction contracts distinguish professional tool contact, ordered
  assembly, and articulated mechanisms so the pipeline does not demand wrench
  capacity for a tape-wrap or invent a tool for a sliding panel.
- Stage 3 describes what happens and supplies physical facts; it still does not
  choose the final camera.

### Stage 4

- Bind each asset to a declared role in the prompt rather than merely attaching
  images.
- Keep camera, action timeline, allowed changes, invariants, geometry locks,
  screen direction, and final observable state as separate prompt sections.
- Add the interaction-manual necessity decision, panel specification, image
  prompt, QA overlay plan, and approval gate implemented in this change.
- A longer multi-cut generation may use storyboard-like references, but it
  remains an experiment until the planned H3 internal-cut comparison is run.

### Stage 5

- Render required interaction manuals first from the canonical stage-02 sheets.
- Approve the clean and annotated versions.
- Then render the start plate from the same canonical sheets plus the approved
  clean manual.
- Never repair a missing physical relationship by improvising a standalone
  single-view affordance image.

### Stage 6 and 7

- H3 receives the approved first frame, all relevant canonical stage-02 sheets,
  approved clean manuals, and the role-bound prompt.
- H3 native audio remains discarded. Music, effects, dialogue, readable text,
  and titles belong to post-production.

## Items not adopted

- The video's 720p/1080p comparison does not change the H3 runtime, which is
  fixed to its local 768p profile. Delivery upscaling remains a separate edit
  contract.
- The video's long-generation claim concerns another model. It supports trying
  the already-designed H3 internal-cut experiment but does not justify making
  multi-cut generation the production default.
- Prompt length is not treated as quality by itself. A prompt is complete when
  it binds assets and resolves observable decisions; unresolved geometry is a
  blocker, not a reason to add more adjectives.

## Current regression interpretation

The legacy plumber scenario correctly triggers interaction manuals for the
pipe-wrench/connection work, PTFE wrapping/reassembly, tightening, and valve
actuation. Those prompts remain blocked because its stage-03 output has no
interaction contracts. This is the desired diagnosis: stage 05 must not render
another plausible but mechanically false board.

The penthouse walking shot does not require a supplemental manual. The moving
privacy/sheers mechanism does, because start, intermediate, and resolved states
plus fixed/moving architecture must be consistent.
