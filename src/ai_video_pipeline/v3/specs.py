"""Static workflow identity and non-creative integrity contracts."""

from __future__ import annotations

PIPELINE_VERSION = "3.0"
STATE_SCHEMA = "llm-creative-pipeline-state.v1"
ARTIFACT_SCHEMA = "llm-stage-artifact.v1"
CRITIQUE_SCHEMA = "llm-stage-critique.v1"
RECEIPT_SCHEMA = "llm-stage-receipt.v1"
MAX_ATTEMPTS = 10

STAGE02_META_PROMPT_SCHEMA = "reference-board-meta-prompt.v2"
STAGE02_INPUT_SCHEMA = "stage02-reference-board-input.v2"
STAGE02_INPUTS_SCHEMA = "stage02-reference-board-inputs.v2"
STAGE02_WRITER_PROTOCOL = "full-structured-reference-board-writer.v2"
STAGE02_WRITER_RULES = """아래 두 가지를 받는다.

1. 시트 명세. 어떤 보드를 만들지 정한 설계 지시다.
2. 대상 정의. 이 시도가 앞 단계에서 확정한 대상의 사실이다.

대상 정의는 앞 단계가 확정한 사실이다. 명세보다 정의가 우선한다.

- 정의에 적힌 의상, 색, 머리, 얼굴 특징, 체형, 나이, 형태, 구조, 재질은 바꾸지 마라.
- 정의가 침묵한 항목만 보완하라. 보완한 요소끼리는 시대, 직업, 문화, 기능, 물리가 맞아야 한다.
- 최종 프롬프트 안에서 정의의 표현을 누락하거나 의미를 바꿔 요약하지 마라.
- 계약 조항은 최종 프롬프트에 반드시 반영하라.
- 시트 명세의 캔버스, 아홉 패널, 패널 내부의 고정 뷰와 항목 수를 줄이거나 합치지 마라.

최종 출력은 이미지 모델에 그대로 전달할 영어 프롬프트 본문 하나다.
설명, 머리말, 코드펜스, 항목 번호를 붙이지 마라.
"""
STAGE02_CANVAS_CONTRACT = {
    "purpose": "reference_board",
    "width": 1672,
    "height": 941,
    "orientation": "landscape",
    "aspect_ratio": "16:9",
    "quality": "high",
    "independent_of_video_frame": True,
}
STAGE02_SPEC_PATHS = {
    "character": "src/ai_video_pipeline/sheet_specs/character.md",
    "subject": "src/ai_video_pipeline/sheet_specs/subject.md",
    "setting": "src/ai_video_pipeline/sheet_specs/setting.md",
}
STAGE02_REQUIRED_PANEL_IDS = {
    "character": (
        "HERO_FULL_BODY",
        "DETAILED_ACCESSORIES",
        "FULL_BODY_TURNAROUND",
        "COSTUME_EQUIPMENT",
        "MATERIAL_REFERENCE",
        "CHARACTER_NOTES",
        "COLOR_PALETTE",
        "HEAD_STUDY",
        "EXPRESSION_STUDY",
    ),
    "subject": (
        "HERO_OBJECT",
        "DETAILED_FEATURES",
        "FULL_TURNAROUND",
        "COMPONENT_BREAKDOWN",
        "MATERIAL_REFERENCE",
        "SUBJECT_NOTES",
        "COLOR_PALETTE",
        "DETAIL_STUDY",
        "SCALE_STUDY",
    ),
    "setting": (
        "01_HERO_PANEL",
        "02_CONCEPT_SKETCH",
        "03_COLOR_MATERIAL_BOARD",
        "04_VIEW_REFERENCE",
        "05_STRUCTURE_DESIGN",
        "06_PROP_DESIGN",
        "07_NATURE_DESIGN",
        "08_MOOD_VARIATION",
        "09_WORLD_NOTES",
    ),
}

VARIATION_STRATEGIES = (
    "base_contract_execution",
    "positive_requirement_restatement",
    "constraint_priority_reordering",
    "identity_and_count_lock_emphasis",
    "spatial_composition_clarification",
    "physical_contact_and_topology_clarification",
    "camera_lighting_and_visibility_clarification",
    "temporal_state_and_action_boundary_clarification",
    "contradiction_removal_and_negative_space_simplification",
    "minimal_rebuild_around_failed_criteria",
)

STAGES = (
    {
        "id": "01-premise",
        "skill": "video-stage01-premise",
        "question": "What production are we making, under what creative contract?",
    },
    {
        "id": "02-sheet",
        "skill": "video-stage02-sheets",
        "question": "What is the approved visual identity and reference system?",
    },
    {
        "id": "03-scenario",
        "skill": "video-stage03-scenario",
        "question": "What happens in sequences, scenes, and dramatic events?",
    },
    {
        "id": "04-shot-design",
        "skill": "video-stage04-shot-design",
        "question": "How will the scenes be directed, covered, photographed, and timed?",
    },
    {
        "id": "05-plate",
        "skill": "video-stage05-plates",
        "question": "Which reference debts and start plates make production executable?",
    },
    {
        "id": "05.5-motion-prompt",
        "skill": "video-stage05b-motion-prompt",
        "question": "How should each approved start plate be directed into the strongest executable C01 motion prompt?",
    },
    {
        "id": "06-motion",
        "skill": "video-stage06-motion",
        "question": "Which reviewed motion take fulfills each shot contract?",
    },
    {
        "id": "07-edit",
        "skill": "video-stage07-edit",
        "question": "How are selected takes trimmed, retimed, and assembled?",
    },
    {
        "id": "08-review",
        "skill": "video-stage08-review",
        "question": "What passed, what remains defective, and is release eligible?",
    },
)

STAGE_BY_ID = {item["id"]: item for item in STAGES}
STAGE_INDEX = {item["id"]: index for index, item in enumerate(STAGES)}

# Stage 04 intentionally flows straight into Stage 05. This preserves the
# previously agreed rule that a successful shot design must not pause before
# reference fulfillment and start-plate generation.
DEFAULT_NORMAL_HUMAN_GATES = (
    "01-premise",
    "05-plate",
    "06-motion",
    "07-edit",
    "08-review",
)

CRITIC_CRITERIA = {
    "01-premise": (
        ("direction_fidelity", "The artifact preserves the user's direction without topic contamination."),
        ("research_sufficiency", "Research and creative choices are sufficient for visible production facts."),
        ("contract_coherence", "Runtime, frame, subjects, and clauses form one coherent production contract."),
    ),
    "02-sheet": (
        ("identity_coverage", "Every required subject has a usable and internally consistent visual reference."),
        ("structured_prompt_fidelity", "Each A01 image prompt is bound to the complete Stage 01 definition, current clauses, canonical kind specification, nine-panel plan, and recorded structured meta-prompt."),
        ("board_information_density", "Every board visibly realizes all nine canonical information panels and the fixed subview/item counts required by its kind specification; a sparse three-image sheet fails."),
        ("reference_canvas_independence", "Every reference board is a 16:9 landscape production sheet independent of the video's frame or delivery orientation."),
        ("visual_reference_quality", "Boards are readable production references without unrelated subject leakage."),
    ),
    "03-scenario": (
        ("dramatic_progression", "Sequences and scenes create meaningful progression rather than a list of actions."),
        ("event_density", "The amount of incident fits the estimated editorial range without mechanical timing rules."),
        ("reference_debt_honesty", "New story-motivated elements are retained and honestly registered as reference debt."),
    ),
    "04-shot-design": (
        ("directorial_intent", "Every setup and shot expresses scene intent, POV, blocking, and coverage logic."),
        ("camera_reasoning", "Camera, composition, and technique choices have a scene-specific dramatic rationale."),
        ("temporal_design", "Shot duration and special time treatment are authored for the event and execution method."),
        ("production_feasibility", "The plan can be executed without asking the generator to invent missing states or references."),
    ),
    "05-plate": (
        ("reference_barrier", "All references are reviewed before any dependent start plate."),
        ("reference_match", "Each start plate agrees with approved identity, topology, material, and geometry references."),
        ("start_state_truth", "Each plate depicts one coherent pre-action instant from the authored shot contract."),
    ),
    "05.5-motion-prompt": (
        ("plate_grounding", "The refinement visibly reads the approved plate and every reference bound to that plate."),
        ("upstream_fidelity", "The prompt realizes the Stage 03 event and Stage 04 shot intent without rewriting their authority."),
        ("motion_direction", "Action, performance, camera, shooting technique, time treatment, and ending are translated into executable visible behavior."),
        ("plate_authority_boundary", "The stage accepts the Stage 05 plate as final and improves the motion prompt without revalidating or regenerating imagery."),
        ("c01_prompt_quality", "The final C01 prompt is coherent, model-usable, and grounded in the actual starting pixels."),
    ),
    "06-motion": (
        ("motion_fidelity", "The selected take performs the authored action and temporal design once and in order."),
        ("continuity", "Identity, count, topology, camera, lighting, and environment remain coherent."),
        ("take_policy", "C01 uses the approved Stage 05.5 prompt verbatim, and C02 or later exists only because the immediately prior take failed review."),
    ),
    "07-edit": (
        ("editorial_intent", "Trim, retime, transition, and information-layer choices serve the authored dramatic plan."),
        ("temporal_fidelity", "Special time treatments preserve the Stage 04 subject, world, and camera time domains."),
        ("continuity", "The assembled cut has coherent screen direction, pacing, sound intent, and visual continuity."),
    ),
    "08-review": (
        ("evidence_complete", "The review cites current artifacts and receipts for every material conclusion."),
        ("defect_disposition", "Every remaining defect is fixed, rejected, or explicitly accepted by authorized policy."),
        ("release_boundary", "Internal completion is not misrepresented as permission to publish externally."),
    ),
}
