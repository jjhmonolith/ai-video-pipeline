"""Shared bounded retry policy for authored prompts, designs, and images.

The harness does not turn contract drift, missing authority, or a mode-required
human decision into something an agent may guess. It does keep ordinary generation
and semantic-review failures moving: one artifact at a time, with a recorded
repair focus and a different prompt strategy on every retry.
"""

from __future__ import annotations

import hashlib
from typing import Iterable


HARNESS_SCHEMA = "adaptive-generation-harness.v1"
MAX_GENERATION_ATTEMPTS = 10
VARIATION_STRATEGIES = (
    "base_contract_execution",
    "positive_requirement_restatement",
    "constraint_priority_reordering",
    "identity_and_count_lock_emphasis",
    "spatial_composition_clarification",
    "physical_contact_and_topology_clarification",
    "camera_lighting_and_visibility_clarification",
    "temporal_state_and_action_boundary_clarification",
    "contradiction_removal_and_negative-space_simplification",
    "minimal_scene_rebuild_around_failed_criteria",
)

# These conditions need new authority or a changed source of truth. Repeating a
# model call cannot solve them and would only burn the retry budget.
TERMINAL_FAILURE_CLASSES = {
    "permission_or_safety_boundary",
    "required_human_final_approval",
    "missing_user_authored_direction",
    "irreconcilable_contract",
}


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def variation_strategy(attempt: int) -> str:
    if not 1 <= attempt <= MAX_GENERATION_ATTEMPTS:
        raise ValueError(
            f"attempt must be between 1 and {MAX_GENERATION_ATTEMPTS}: {attempt}")
    return VARIATION_STRATEGIES[attempt - 1]


def retry_prompt(base_prompt: str, attempt: int, correction: str,
                 *, failed_criteria: Iterable[str] = (),
                 prior_attempt_sha256: str | None = None,
                 allowed_revisions: Iterable[str] = ()) -> str:
    """Preserve the source prompt and append a distinct, auditable repair layer."""
    if attempt == 1:
        return base_prompt
    strategy = variation_strategy(attempt)
    criteria = [str(item).strip() for item in failed_criteria if str(item).strip()]
    revisions = [str(item).strip() for item in allowed_revisions if str(item).strip()]
    criteria_text = "\n".join(f"- {item}" for item in criteria) or "- use the review feedback below"
    prior = prior_attempt_sha256 or "not-recorded"
    revision_contract = (
        "You may revise only these artifact-owned creative decisions while keeping all upstream "
        "facts and authority unchanged: " + "; ".join(revisions) + "."
        if revisions else
        "Do not invent new subjects, facts, actions, parts, text, camera moves, or approvals."
    )
    return (
        f"{base_prompt.rstrip()}\n\n"
        f"ADAPTIVE RETRY {attempt}/{MAX_GENERATION_ATTEMPTS} — BINDING\n"
        "Preserve the complete source contract and every instruction above. "
        f"{revision_contract}\n"
        f"Variation strategy: {strategy}.\n"
        f"Previous attempt SHA-256: {prior}.\n"
        "Failed criteria to repair:\n"
        f"{criteria_text}\n"
        "Concrete review feedback:\n"
        f"{correction.strip()}"
    )


def harness_contract(artifact_type: str, base_prompt_sha256: str,
                     acceptance_criteria: Iterable[str],
                     *, exhaustion_policy: str = "return_attempt_10_for_review",
                     execution_mode: str = "normal") -> dict:
    if execution_mode not in {"normal", "fast_track"}:
        raise ValueError("execution_mode must be normal or fast_track")
    terminal = set(TERMINAL_FAILURE_CLASSES)
    if execution_mode == "fast_track":
        terminal.discard("required_human_final_approval")
    return {
        "schema_version": HARNESS_SCHEMA,
        "artifact_type": artifact_type,
        "strategy": "sequential_validate_repair_regenerate",
        "initial_generation_count": 1,
        "max_attempts": MAX_GENERATION_ATTEMPTS,
        "stop_on_pass": True,
        "vary_every_retry": True,
        "variation_strategies": list(VARIATION_STRATEGIES),
        "base_prompt_sha256": base_prompt_sha256,
        "acceptance_criteria": list(acceptance_criteria),
        "recoverable_failure_policy": (
            "feed failed criteria and concrete evidence into the next distinct variation; "
            "continue without asking for confirmation; regenerate an upstream owned asset or "
            "prepare a fresh manifest when source hashes drift"
        ),
        "execution_mode": execution_mode,
        "approval_policy": (
            "ai_applies_internal_review_and_continues"
            if execution_mode == "fast_track" else "pause_at_required_human_gate"
        ),
        "terminal_failure_classes": sorted(terminal),
        "exhaustion_policy": exhaustion_policy,
    }


def attempt_record(attempt: int, effective_prompt: str, decision: str,
                   feedback: str = "", failed_criteria: Iterable[str] = ()) -> dict:
    if decision not in {"pass", "fail"}:
        raise ValueError("decision must be pass or fail")
    return {
        "attempt": attempt,
        "variation_strategy": variation_strategy(attempt),
        "effective_prompt_sha256": text_sha256(effective_prompt),
        "decision": decision,
        "failed_criteria": [str(item) for item in failed_criteria],
        "feedback": feedback,
    }
