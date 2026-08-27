"""02-sheet: turn each definition into a reference board, several views at once.

A definition written in `01-premise` says what a thing is in words. This says
the same thing in pictures, and the two are halves of one decision rather than
a plan and its execution. That is why the stage sits here and not next to
production: separate them and the words drift from the drawing, which is how a
run once shipped sheets that no later stage ever opened.

The board is made in two passes, and the split is the point.

A design spec written for a director is not an image prompt. It reasons about
gaps and holds a fixed layout in mind. The structured prompt-pack compiler binds
that spec, the element definition, the contract policy and every applicable
clause into one recorded image prompt. The API composer may still improve prose,
but Codex interactive work has a deterministic local compiler so preparing an
ImageGen job never depends on an API key.

Both passes are kept. `prompts/` holds the English that was actually sent, so a
board can be regenerated or argued with without re-running the reasoning, and a
board that came out wrong can be traced to the prompt rather than guessed at.

One spec per kind, because the kinds do not pin the same way. A character is
pinned by a face seen from around it. A subject is pinned by a form seen from
around it. A setting has no around: it is pinned by the same place at several
distances, since what has to hold is the geometry and the light. Any kind may
have several elements, and each gets its own board.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from .contract import Contract, ContractError, load as load_contract
from .research import DEFAULT_MODEL, _client
from .lifecycle import read_direction_impact, read_premise_state
from .generation_harness import (
    HARNESS_SCHEMA,
    MAX_GENERATION_ATTEMPTS,
    VARIATION_STRATEGIES,
    attempt_record,
    harness_contract,
    retry_prompt,
)
from .execution_mode import load_execution_mode

STAGE_ROLE = "sheet"
STAGE_FALLBACK = "02-sheet"
SPEC_DIR = Path(__file__).resolve().parent / "sheet_specs"
RECEIPT_SCHEMA = "sheet-receipt.v2"
GENERATOR_API = "api"
GENERATOR_CODEX = "codex"
CODEX_SURFACES = {"desktop", "cli", "ide", "cloud", "unknown"}
PROMPT_PACK_SCHEMA = "sheet-prompt-pack.v2"
PROMPT_AUTHORING_PIPELINE = "structured-meta-prompt.v1"
LOCAL_PROMPT_COMPILER = "structured-local-compiler.v1"
SHEET_AI_ATTEMPT_REVIEW_SCHEMA = "sheet-image-ai-attempt-review.v1"
PIXEL_TOLERANCE_RATIO = 0.01
PIXEL_TOLERANCE_MAX_PIXELS = 16

WRITER_RULES = """
아래 두 가지를 받는다.

1. 시트 명세. 어떤 보드를 만들지 정한 설계 지시다.
2. 대상 정의. 이 시도가 앞 단계에서 확정한 대상의 사실이다.

대상 정의는 앞 단계가 확정한 사실이다. **명세보다 정의가 우선한다.**

- 정의에 적힌 의상, 색, 머리, 얼굴 특징, 체형, 나이는 한 글자도 바꾸지 마라.
  다른 옷을 입히거나 색을 바꾸는 것은 명백한 위반이다.
- 정의가 침묵한 항목만 보완하라. 소품과 장비를 더하는 것은 되지만, 정의에
  적힌 것을 대체하는 것은 안 된다.
- 보완한 것끼리는 시대·직업·기능이 서로 맞아야 한다.

최종 프롬프트 안에서 정의의 표현을 그대로 옮겨 적어라. 요약하거나 바꿔 말하지 마라.

아래 금지 조항은 계약에서 온 것이며 최종 프롬프트에 반드시 그대로 포함하라.

최종 출력은 이미지 모델에 그대로 전달할 영어 프롬프트 본문 하나다.
설명, 머리말, 코드펜스, 항목 번호를 붙이지 마라.
"""


class SheetError(RuntimeError):
    """The board could not be composed or rendered."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def definition_sha256(definition: dict) -> str:
    """Canonical digest of the complete definition record, including governance."""
    return hashlib.sha256(
        json.dumps(definition, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]


DEFINITION_BOOKKEEPING = {
    "provenance", "evidence", "decisions", "evidence_context_legacy",
}


def definition_content(definition: dict) -> dict:
    """Only fields that can change the visual reference or its topology."""
    return {key: value for key, value in definition.items()
            if key not in DEFINITION_BOOKKEEPING}


def definition_content_sha256(definition: dict) -> str:
    return hashlib.sha256(
        json.dumps(definition_content(definition), ensure_ascii=False,
                   sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]


def prompt_sha256(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]


def data_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]


def codex_render_instruction(plan, quality: str) -> str:
    """Exact provider instruction appended only for interactive Codex ImageGen."""
    width, height = plan.target
    orientation = "landscape" if width > height else "portrait" if height > width else "square"
    return (
        "OUTPUT REQUIREMENTS — BINDING\n"
        f"Generate one native {width}x{height}-pixel {orientation} PNG at {quality.upper()} quality. "
        "Render at that native resolution; do not return a smaller preview and do not upscale a "
        "lower-resolution image. Preserve the requested composition and all board details."
    )


def codex_generation_prompt(prompt: str, plan, quality: str) -> tuple[str, str]:
    instruction = codex_render_instruction(plan, quality)
    return f"{prompt.rstrip()}\n\n{instruction}", instruction


def pixel_tolerance(target: tuple[int, int]) -> tuple[int, int]:
    """Small provider raster variance accepted per axis.

    The ratio prevents meaningful low-resolution inputs from passing, while
    the pixel cap keeps large future rasters from gaining a broad loophole.
    Tiny test/thumbnail rasters remain exact because one pixel would already
    exceed one percent.
    """
    return tuple(
        min(PIXEL_TOLERANCE_MAX_PIXELS, int(dimension * PIXEL_TOLERANCE_RATIO))
        for dimension in target
    )


def source_within_pixel_tolerance(source: tuple[int, int],
                                  target: tuple[int, int]) -> bool:
    allowed_width, allowed_height = pixel_tolerance(target)
    return (
        max(0, target[0] - source[0]) <= allowed_width
        and max(0, target[1] - source[1]) <= allowed_height
    )


def materialize_with_pixel_tolerance(image: Image.Image,
                                     target: tuple[int, int]) -> tuple[Image.Image, str]:
    """Normalize exact, oversized, or trivially undersized provider rasters."""
    source_width, source_height = image.size
    target_width, target_height = target
    if not source_within_pixel_tolerance(image.size, target):
        allowed = pixel_tolerance(target)
        raise SheetError(
            "원본 해상도가 계약 허용오차를 넘는다: "
            f"source={source_width}x{source_height} requested={target_width}x{target_height} "
            f"allowed_deficit={allowed[0]}x{allowed[1]}"
        )
    if image.size == target:
        return image, "exact"

    small_upscale = source_width < target_width or source_height < target_height
    source_aspect = source_width / source_height
    target_aspect = target_width / target_height
    if source_aspect > target_aspect:
        crop_width = round(source_height * target_aspect)
        left = (source_width - crop_width) // 2
        image = image.crop((left, 0, left + crop_width, source_height))
    elif source_aspect < target_aspect:
        crop_height = round(source_width / target_aspect)
        top = (source_height - crop_height) // 2
        image = image.crop((0, top, source_width, top + crop_height))
    cropped = image.size != (source_width, source_height)
    image = image.resize(target, Image.Resampling.LANCZOS)
    if small_upscale and cropped:
        return image, "tolerance-upscale-and-crop"
    if small_upscale:
        return image, "tolerance-upscale"
    return image, "crop-and-downscale"


def spec_text(kind: str, policy: dict) -> str:
    """The design spec for this kind, from the package unless the attempt overrides it."""
    name = policy.get("spec", kind)
    path = SPEC_DIR / f"{name}.md"
    if not path.exists():
        raise SheetError(f"{kind}: 시트 명세가 없다 {path}")
    return path.read_text(encoding="utf-8")


def stage_name(contract: Contract) -> str:
    return contract.stage_for(STAGE_ROLE, STAGE_FALLBACK)


def stage_dir(attempt: Path, contract: Contract) -> Path:
    return attempt / stage_name(contract)


def read_element(attempt: Path, contract: Contract, element: str) -> dict:
    where = contract.get("subjects", {}).get(
        "directory", f'{contract.stage_for("premise", "01-premise")}/output/subjects')
    path = attempt / where / f"{element}.json"
    if not path.exists():
        raise SheetError(f"{element}: 정의가 없다 {path}. 01-premise 를 먼저 돌린다")
    return json.loads(path.read_text(encoding="utf-8"))


def structured_meta_prompt(attempt: Path, contract: Contract, element: str) -> dict:
    """Build the only authorized input contract for a stage-02 prompt writer."""
    definition = read_element(attempt, contract, element)
    declared = contract.elements().get(element)
    if not declared:
        raise SheetError(f"{element}: 계약이 선언하지 않은 요소다")
    kind = declared.get("kind", "subject")
    policy = contract.sheet_policy(kind)
    specification = spec_text(kind, policy)
    body = definition_content(definition)
    bound = contract.clauses_for(stage_name(contract), subject_kind=kind, element=element)
    clauses = " ".join(item["text"] for item in bound)
    question = "\n\n".join([
        WRITER_RULES,
        "=== 계약 시트 정책 ===",
        json.dumps(policy, ensure_ascii=False, indent=2),
        "=== 시트 명세 ===",
        specification,
        "=== 대상 정의 ===",
        json.dumps(body, ensure_ascii=False, indent=2),
        "=== 반드시 포함할 금지 조항 ===",
        clauses or "(없음)",
    ])
    return {
        "element": element,
        "kind": kind,
        "spec": policy.get("spec", kind),
        "sheet_policy": policy,
        "sheet_specification": specification,
        "definition_content": body,
        "bound_clauses": bound,
        "definition": definition,
        "definition_sha256": definition_sha256(definition),
        "definition_content_sha256": definition_content_sha256(definition),
        "writer_rules_sha256": prompt_sha256(WRITER_RULES),
        "sheet_policy_sha256": data_sha256(policy),
        "sheet_spec_sha256": prompt_sha256(specification),
        "contract_clauses_sha256": data_sha256(bound),
        "meta_prompt": question,
        "meta_prompt_sha256": prompt_sha256(question),
        "execution_mode": load_execution_mode(attempt),
    }


LOCAL_KIND_RULES = {
    "character": (
        "This is a casting and identity board, never a scene. Show exactly one recurring "
        "character identity on a clean near-white or warm-ivory studio background. Preserve "
        "the same apparent age, adult or youth proportions, face abstraction, hair, costume, "
        "colour placement and carried items in every panel. No location, furniture, second "
        "person or narrative scene. In DETAILED ACCESSORIES, show only body details, wardrobe "
        "and worn accessories explicitly declared for this character. Never introduce another "
        "named subject, machine, handle, valve, tool or interaction object merely to fill that "
        "panel."
    ),
    "subject": (
        "This is an object and transformation-system board, never a scene. Show one coherent "
        "subject identity on a clean near-white or warm-ivory studio background. Preserve "
        "silhouette, construction, parts, materials, colour placement and state continuity. "
        "No location, cast member or unrelated prop."
    ),
    "setting": (
        "This is an environment-system board. Every panel must depict the same continuous "
        "place and preserve its topology, visual language, materials, palette and circulation. "
        "Do not depict a named character or subject from another sheet. Anonymous featureless "
        "scale silhouettes are allowed only when the contract permits them. Keep every mounting "
        "bay, cradle, socket or interface intended for a subject owned by another sheet visibly "
        "empty; show only the fixed environment-side interface, never a substitute device. "
        "Apart from the "
        "required section headings, show no words, node names, captions, legends, numerals, "
        "dimensions or measurement labels anywhere, including CONCEPT SKETCH and WORLD NOTES. "
        "Communicate every route, scale and topology fact with unlabelled shapes and arrows only."
    ),
}


def compile_prompt_locally(context: dict, attempt: int = 1,
                           correction: str = "") -> str:
    """Compile a bound image prompt without a network or language-model call.

    The compiler deliberately does not invent missing visual facts. It passes the
    Stage-1 definition through verbatim, adds the contract-selected panel policy,
    and appends the exact scoped clauses. This keeps Codex ImageGen API-key-free
    while retaining the same provenance hashes as the optional prose composer.
    """
    kind = context["kind"]
    policy = context["sheet_policy"]
    panels = list(policy.get("panels") or [])
    definition = json.dumps(
        context["definition_content"], ensure_ascii=False, indent=2, sort_keys=True)
    clauses = "\n".join(
        f'- {item["text"]}' for item in context.get("bound_clauses") or [])
    panel_text = " | ".join(str(panel) for panel in panels)
    kind_rule = LOCAL_KIND_RULES.get(
        kind,
        "Show one coherent subject identity across every panel on a clean editorial board.")
    base = "\n\n".join([
        "Use case: infographic-diagram\nAsset type: premium production reference board",
        (
            "PRIMARY REQUEST\n"
            "Create ONE single finished 16:9 landscape reference board at high production "
            "quality. Use a precise editorial grid, thin panel dividers, consistent margins, "
            "clear silhouettes and restrained professional presentation. Fill the canvas. "
            "Do not add, omit, merge, duplicate or reorder panels."
        ),
        f"SUBJECT-KIND LOCK\n{kind_rule}",
        (
            "CONTRACT PANEL POLICY — OVERRIDES GENERIC BOARD EXAMPLES\n"
            f"Use exactly these panels in this order: {panel_text}.\n"
            f"Contract policy: {json.dumps(policy, ensure_ascii=False, sort_keys=True)}"
        ),
        (
            "LOCKED STAGE-1 VISUAL DEFINITION — AUTHORITATIVE AND VERBATIM\n"
            "Interpret the Korean prose literally. Do not replace, summarize or contradict "
            "any stated appearance, proportion, clothing, colour, part, material, zone, "
            "gesture or transformation state.\n"
            f"{definition}"
        ),
        (
            "CONSISTENCY AND PRESENTATION\n"
            "Every repeated view must preserve one identity and one design system. Use only "
            "short, correctly spelled contract panel headings. Keep all other scene text, "
            "notes and labels out of the artwork. Prefer crisp 2D or shallow 2.5D vector "
            "geometry, readable negative space and light neutral backdrops."
        ),
        f"MANDATORY CONTRACT CLAUSES — APPLY EXACTLY\n{clauses or '(none)'}",
        (
            "FINAL OUTPUT\nRender the board itself. Do not explain the design, do not output "
            "a written prompt, and do not add a watermark."
        ),
    ])
    return retry_prompt(base, attempt, correction)


def compose_prompt_local(attempt: Path, contract: Contract, element: str) -> dict:
    """Create the structured prompt pack used by interactive Codex ImageGen."""
    context = structured_meta_prompt(attempt, contract, element)
    bound = context.get("bound_clauses") or []
    correction = ""
    attempts = []
    for number in range(1, MAX_GENERATION_ATTEMPTS + 1):
        prompt = compile_prompt_locally(context, number, correction)
        missing_items = [item for item in bound if item["text"] not in prompt]
        missing = [item["id"] for item in missing_items]
        decision = "pass" if not missing else "fail"
        feedback = ("" if not missing_items else
                    "Append these exact missing contract clauses:\n" +
                    "\n".join(item["text"] for item in missing_items))
        attempts.append(attempt_record(number, prompt, decision, feedback, missing))
        if decision == "pass":
            return structured_prompt_pack(
                context, prompt, LOCAL_PROMPT_COMPILER,
                clauses_appended=[], clauses_still_missing=[],
                harness_attempts=attempts,
            )
        correction = feedback
    raise SheetError(
        f"{element}: 구조화 프롬프트가 {MAX_GENERATION_ATTEMPTS}회 복구 뒤에도 계약 조항을 누락했다")


def structured_prompt_pack(context: dict, prompt: str, written_by: str,
                           clauses_appended: list[str] | None = None,
                           clauses_still_missing: list[str] | None = None,
                           harness_attempts: list[dict] | None = None) -> dict:
    """Bind a writer response to every structured authoring input."""
    return {
        "schema_version": PROMPT_PACK_SCHEMA,
        "authoring_pipeline": PROMPT_AUTHORING_PIPELINE,
        "element": context["element"],
        "kind": context["kind"],
        "spec": context["spec"],
        "written_by": written_by,
        "written_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "definition_sha256": context["definition_sha256"],
        "definition_content_sha256": context["definition_content_sha256"],
        "writer_rules_sha256": context["writer_rules_sha256"],
        "sheet_policy_sha256": context["sheet_policy_sha256"],
        "sheet_spec_sha256": context["sheet_spec_sha256"],
        "contract_clauses_sha256": context["contract_clauses_sha256"],
        "meta_prompt_sha256": context["meta_prompt_sha256"],
        "generation_harness": {
            **harness_contract(
                "stage02_structured_prompt",
                context["meta_prompt_sha256"],
                (
                    "writer response is non-empty",
                    "all scoped contract clauses are present",
                    "no excluded subject-kind clause leaks into the prompt",
                    "structured meta-prompt provenance remains intact",
                ),
                exhaustion_policy="report_attempt_10_with_failed_prompt_criteria",
                execution_mode=(context.get("execution_mode") or {}).get("mode", "normal"),
            ),
            "attempts": harness_attempts or [],
        },
        "clauses_appended": clauses_appended or [],
        "clauses_still_missing": clauses_still_missing or [],
        "prompt_sha256": prompt_sha256(prompt),
        "prompt": prompt,
    }


def compose_prompt(attempt: Path, contract: Contract, element: str,
                   model: str = DEFAULT_MODEL) -> dict:
    """Pass one. A director's spec plus a definition becomes an English image prompt."""
    context = structured_meta_prompt(attempt, contract, element)
    kind = context["kind"]
    clauses = contract.clause_text(stage_name(contract), subject_kind=kind, element=element)

    bound = contract.clauses_for(stage_name(contract), subject_kind=kind, element=element)
    excluded = contract.excluded_clauses_for(
        stage_name(contract), subject_kind=kind, element=element)
    client = _client()
    correction = ""
    attempts = []
    for number in range(1, MAX_GENERATION_ATTEMPTS + 1):
        effective = retry_prompt(context["meta_prompt"], number, correction)
        response = client.responses.create(model=model, input=effective)
        prompt = (getattr(response, "output_text", "") or "").strip()
        missing = [c["id"] for c in bound if c["text"] not in prompt]
        if prompt and missing:
            prompt = prompt.rstrip() + " " + clauses
        missing_after = [c["id"] for c in bound if c["text"] not in prompt]
        leaked = [item["id"] for item in excluded
                  if any(text in prompt for text in contract.clause_text_variants(item))]
        failed = ([] if prompt else ["writer response is non-empty"])
        failed.extend(f"missing clause {item}" for item in missing_after)
        failed.extend(f"excluded clause leaked {item}" for item in leaked)
        decision = "pass" if not failed else "fail"
        correction = ("Return only the complete image prompt. Repair these validation findings:\n" +
                      "\n".join(f"- {item}" for item in failed))
        attempts.append(attempt_record(number, effective, decision,
                                       "" if decision == "pass" else correction, failed))
        if decision == "pass":
            return structured_prompt_pack(
                context, prompt, model,
                clauses_appended=missing,
                clauses_still_missing=missing_after,
                harness_attempts=attempts,
            )
    raise SheetError(
        f"{element}: 프롬프트가 {MAX_GENERATION_ATTEMPTS}회 변주 뒤에도 검증을 통과하지 못했다")


def render(attempt: Path, contract: Contract, entry: dict, force: bool = False,
           draft: bool = False) -> dict:
    """Pass two. The English prompt becomes the board, at the size the kind asks for."""
    element, kind = entry["element"], entry["kind"]
    plan = contract.sheet_plan(kind)
    quality = contract.image_quality("sheet", draft)
    out_dir = stage_dir(attempt, contract) / "output" / ("drafts" if draft else "sheets")
    target = out_dir / f"{element}.png"
    if target.exists() and target.stat().st_size > 0 and not force:
        # 건너뛸 때도 파일이 실제로 어떤지는 잰다. 한 줄짜리 existing 으로
        # 덮으면 그 파일에 대해 알던 크기와 품질이 기록에서 사라진다.
        with Image.open(target) as existing:
            delivered = list(existing.size)
        return {"element": element, "kind": kind, "status": "existing",
                "delivered": delivered, "draft": draft,
                "matches_contract": delivered == list(plan.target),
                "prompt_sha256": prompt_sha256(entry["prompt"]),
                "definition_sha256": entry["definition_sha256"],
                "definition_content_sha256": entry.get("definition_content_sha256"),
                "contract_sha256": contract.digest,
                "generator": {
                    "mode": "reuse",
                    "invocation": "existing-output",
                    "usage_accounting": "not-applicable",
                },
                "bytes": target.stat().st_size, "sha256": sha256(target)}

    client = _client()
    started = time.time()
    result = client.images.generate(
        model=contract.image_model, prompt=entry["prompt"],
        size=plan.api_size, quality=quality, n=1)
    payload = result.data[0].b64_json
    if not payload:
        raise SheetError(f"{element}: 이미지 payload 없음")

    # 과금은 장당이 아니라 토큰이다. 크기와 품질을 올릴 때 무엇을 지불하는지
    # 나중에 알 수 있으려면 그때 재서 남겨야 한다.
    usage = getattr(result, "usage", None)
    spend = {}
    if usage is not None:
        for field in ("input_tokens", "output_tokens", "total_tokens"):
            value = getattr(usage, field, None)
            if value is not None:
                spend[field] = value

    raw = base64.b64decode(payload)
    raw_dir = stage_dir(attempt, contract) / "qa" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"{element}.png").write_bytes(raw)

    image = Image.open(io.BytesIO(raw)).convert("RGB")
    source_dimensions = list(image.size)
    image, actual_fit = materialize_with_pixel_tolerance(image, tuple(plan.target))
    out_dir.mkdir(parents=True, exist_ok=True)
    image.save(target)

    return {
        "element": element, "kind": kind, "status": "generated",
        "model": contract.image_model, "api_size": plan.api_size,
        "requested": list(plan.target), "source_dimensions": source_dimensions,
        "delivered": list(plan.target), "fit": actual_fit,
        "pixel_tolerance": {
            "max_ratio": PIXEL_TOLERANCE_RATIO,
            "max_pixels_per_axis": PIXEL_TOLERANCE_MAX_PIXELS,
            "allowed_deficit": list(pixel_tolerance(tuple(plan.target))),
        },
        "quality": quality, "draft": draft,
        "prompt_sha256": prompt_sha256(entry["prompt"]),
        "definition_sha256": entry["definition_sha256"],
        "definition_content_sha256": entry.get("definition_content_sha256"),
        "contract_sha256": contract.digest,
        "generator": {
            "mode": GENERATOR_API,
            "invocation": "openai-python-client",
            "model": contract.image_model,
            "usage_accounting": "api",
        },
        "bytes": target.stat().st_size, "sha256": sha256(target),
        "usage": spend,
        "elapsed_seconds": round(time.time() - started, 1),
        "created_at_epoch": int(time.time()),
    }


def _wanted_elements(contract: Contract, kinds: list[str] | None,
                     only: list[str] | None) -> dict:
    wanted = contract.elements()
    if kinds:
        wanted = {n: r for n, r in wanted.items() if r.get("kind") in set(kinds)}
    if only:
        wanted = {n: r for n, r in wanted.items() if n in set(only)}
    if not wanted:
        raise SheetError("만들 요소가 없다. 계약의 subjects.declared 를 확인한다")
    return wanted


def _load_prompt_entry(attempt: Path, contract: Contract, element: str) -> tuple[dict, Path]:
    """Load and validate the exact prompt Codex is allowed to render.

    Codex mode intentionally never falls back to an API call. A missing prompt
    is a preparation error, not permission to compose or render through a
    different provider.
    """
    impact = read_direction_impact(attempt, contract)
    impacted = [record for record in impact.get("artifacts", [])
                if record.get("artifact_type") == "subject_definition"
                and Path(record.get("artifact", "")).stem == element
                and record.get("status") in {"revalidation_required", "regeneration_required"}]
    if impacted:
        raise SheetError(
            f"{element}: direction 변경 뒤 정의 재검토가 끝나지 않았다 "
            f"status={impacted[0]['status']}")

    path = stage_dir(attempt, contract) / "prompts" / f"{element}.json"
    if not path.exists():
        raise SheetError(
            f"{element}: Codex 모드는 기존 프롬프트 팩이 필요하다 {path}. "
            "임의 프롬프트를 만들지 말고 공식 stage-02 prompt composer를 먼저 실행한다")
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SheetError(f"{element}: 프롬프트 팩 JSON 오류 {error}") from error

    if (entry.get("schema_version") != PROMPT_PACK_SCHEMA
            or entry.get("authoring_pipeline") != PROMPT_AUTHORING_PIPELINE):
        raise SheetError(
            f"{element}: 구조화 메타 프롬프트 provenance가 없는 프롬프트 팩이다. "
            "임의 작성·직접 ImageGen 진행 금지; 공식 stage-02 prompt composer로 다시 작성한다"
        )

    declared = contract.elements().get(element) or {}
    kind = declared.get("kind", "subject")
    if entry.get("element") != element or entry.get("kind") != kind:
        raise SheetError(
            f"{element}: 프롬프트 팩 식별자가 계약과 다르다 "
            f"element={entry.get('element')!r} kind={entry.get('kind')!r}")
    prompt = entry.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise SheetError(f"{element}: 프롬프트 팩의 prompt가 비었다")
    context = structured_meta_prompt(attempt, contract, element)
    expected_provenance = {
        "spec": context["spec"],
        "writer_rules_sha256": context["writer_rules_sha256"],
        "sheet_policy_sha256": context["sheet_policy_sha256"],
        "sheet_spec_sha256": context["sheet_spec_sha256"],
        "contract_clauses_sha256": context["contract_clauses_sha256"],
        "meta_prompt_sha256": context["meta_prompt_sha256"],
        "prompt_sha256": prompt_sha256(prompt),
    }
    mismatched = [field for field, expected in expected_provenance.items()
                  if entry.get(field) != expected]
    if mismatched:
        raise SheetError(
            f"{element}: 구조화 메타 프롬프트 입력 또는 writer 응답 hash가 다르다 "
            f"fields={mismatched}. 공식 prompt composer부터 다시 실행한다"
        )

    definition = context["definition"]
    actual_definition = definition_sha256(definition)
    actual_content = definition_content_sha256(definition)
    recorded_content = entry.get("definition_content_sha256")
    if recorded_content:
        definition_matches = recorded_content == actual_content
    else:
        definition_matches = entry.get("definition_sha256") == actual_definition
    if not definition_matches:
        raise SheetError(
            f"{element}: 시각 정의가 프롬프트 작성 뒤 바뀌었다 "
            f"prompt_content={recorded_content or entry.get('definition_sha256')} "
            f"current_content={actual_content}")
    bound = contract.clauses_for(stage_name(contract), subject_kind=kind, element=element)
    missing = [c["id"] for c in bound
               if c["text"] not in prompt]
    if missing:
        raise SheetError(f"{element}: Codex에 보낼 프롬프트에 계약 조항 누락 {missing}")
    leaked = [clause["id"]
              for clause in contract.excluded_clauses_for(
                  stage_name(contract), subject_kind=kind, element=element)
              if any(text in prompt for text in contract.clause_text_variants(clause))]
    if leaked:
        raise SheetError(f"{element}: subject kind에 적용되지 않는 계약 조항이 프롬프트에 누출 {leaked}")
    entry["definition_record_sha256_current"] = actual_definition
    entry["definition_content_sha256"] = actual_content
    return entry, path


def prepare_codex_jobs(attempt: Path, kinds: list[str] | None = None,
                       only: list[str] | None = None, force: bool = False,
                       draft: bool = False) -> dict:
    """Write a provider-neutral work order for Codex built-in image generation.

    This function performs no network call and does not invoke an image model.
    A Codex desktop/CLI/IDE agent reads the manifest, calls `$imagegen`, saves
    each returned image at `candidate_path`, then calls
    :func:`finalize_codex_jobs`.
    """
    contract = load_contract(attempt)
    execution_mode = load_execution_mode(attempt)
    wanted = _wanted_elements(contract, kinds, only)
    stage = stage_dir(attempt, contract)
    created = datetime.now(timezone.utc).astimezone()
    manifest_id = f"{created.strftime('%Y%m%dT%H%M%S%f%z')}-{contract.digest[:8]}"
    manifest_dir = stage / "qa" / "codex" / "manifests"
    candidate_dir = stage / "qa" / "codex" / "candidates" / manifest_id
    jobs, skipped = [], []

    for element in sorted(wanted):
        entry, prompt_path = _load_prompt_entry(attempt, contract, element)
        kind = entry["kind"]
        plan = contract.sheet_plan(kind)
        quality = contract.image_quality("sheet", draft)
        imagegen_prompt, render_instruction = codex_generation_prompt(
            entry["prompt"], plan, quality)
        output_dir = stage / "output" / ("drafts" if draft else "sheets")
        target = output_dir / f"{element}.png"
        if target.exists() and target.stat().st_size > 0 and not force:
            skipped.append({
                "element": element,
                "reason": "output-exists",
                "output_path": str(target.relative_to(attempt)),
                "sha256": sha256(target),
            })
            continue

        candidate = candidate_dir / f"{element}.png"
        sheet_criteria = [
            "the board depicts the declared element and subject kind",
            "all contract panels are present, ordered and readable as visual reference views",
            "identity, topology, proportions, materials and part count remain consistent across panels",
            "no unrelated subject, contradictory state, malformed anatomy or impossible geometry compromises the reference",
        ]
        jobs.append({
            "element": element,
            "kind": kind,
            "status": "awaiting-imagegen",
            "prompt_path": str(prompt_path.relative_to(attempt)),
            "prompt_sha256": prompt_sha256(entry["prompt"]),
            "render_instruction": render_instruction,
            "imagegen_prompt": imagegen_prompt,
            "imagegen_prompt_sha256": prompt_sha256(imagegen_prompt),
            "definition_sha256": entry["definition_sha256"],
            "definition_content_sha256": entry["definition_content_sha256"],
            "definition_record_sha256_current": entry["definition_record_sha256_current"],
            "candidate_path": str(candidate.relative_to(attempt)),
            "retry_harness": {
                **harness_contract(
                    "stage02_sheet_image",
                    prompt_sha256(imagegen_prompt),
                    sheet_criteria,
                    exhaustion_policy="return_attempt_10_for_semantic_review",
                    execution_mode=execution_mode["mode"],
                ),
                "attempt_path_pattern": str(
                    (candidate_dir / element / "attempts" / "A{attempt:02d}.png")
                    .relative_to(attempt)),
                "review_log_path": str(
                    (candidate_dir / element / "ai-retry-review.json")
                    .relative_to(attempt)),
                "selected_candidate_path": str(candidate.relative_to(attempt)),
            },
            "output_path": str(target.relative_to(attempt)),
            "requested": list(plan.target),
            "fit": plan.fit,
            "quality": quality,
            "draft": draft,
            "overwrite": force,
            "existing_output_sha256": sha256(target) if target.exists() else None,
        })

    manifest = {
        "schema_version": "codex-sheet-jobs.v1",
        "manifest_id": manifest_id,
        "status": "prepared",
        "created_at": created.isoformat(timespec="seconds"),
        "attempt": str(attempt.resolve()),
        "stage": stage_name(contract),
        "contract": contract.receipt_block(stage_name(contract)),
        "upstream_state": read_premise_state(attempt, contract),
        "execution_mode": execution_mode,
        "generator": {
            "mode": GENERATOR_CODEX,
            "invocation": "interactive-imagegen-skill",
            "model": "gpt-image-2",
            "usage_accounting": "codex-general-usage",
            "api_key_required": False,
        },
        "jobs": jobs,
        "skipped": skipped,
        "instructions": [
            "각 job은 imagegen_prompt로 한 장을 만들고 즉시 retry_harness 기준으로 검증한다",
            "실패하면 원본 구조화 prompt를 유지하고 실패 기준을 반영한 다음 variation_strategy로 "
            "프롬프트를 변주해 한 장씩 다시 만든다",
            "통과하면 즉시 중단하고 selected_candidate_path로 복사한다. 최대 10회다",
            "10회 모두 실패하면 10회차를 semantic review 대상으로 남기고 다음 job을 계속한다",
            "정식 시트는 manifest의 requested 픽셀과 quality high인지 확인한다",
            "반환된 원본 이미지를 candidate_path에 PNG로 저장한다",
            "목표 대비 1%·축당 16픽셀 이내의 작은 오차는 finalize가 정규화한다. "
            "그보다 작은 원본은 candidate 증거를 남기고 실패한다",
            "모든 candidate가 준비되면 같은 manifest로 finalize를 실행한다",
            "API로 자동 대체하지 않는다",
        ],
    }
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / f"{manifest_id}.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "generator": GENERATOR_CODEX,
        "manifest": str(manifest_path),
        "jobs": len(jobs),
        "skipped": skipped,
        "api_called": False,
    }


def _normalise_prior_record(record: dict, prior_contract_sha256: str | None) -> dict:
    normal = dict(record)
    normal.setdefault("contract_sha256", prior_contract_sha256)
    if not isinstance(normal.get("generator"), dict):
        if normal.get("api_size") or normal.get("usage") is not None:
            normal["generator"] = {
                "mode": GENERATOR_API,
                "invocation": "legacy-openai-client",
                "model": normal.get("model"),
                "usage_accounting": "api",
                "normalised_from": "sheet-receipt.v1",
            }
        else:
            normal["generator"] = {
                "mode": "reuse",
                "invocation": "legacy-existing-output",
                "usage_accounting": "unknown",
                "normalised_from": "sheet-receipt.v1",
            }
    return normal


def _write_receipt(attempt: Path, contract: Contract, records: list[dict],
                   failures: list[dict]) -> Path:
    receipt = stage_dir(attempt, contract) / "receipt.json"
    prior_document = {}
    if receipt.exists():
        prior_document = json.loads(receipt.read_text(encoding="utf-8"))
    prior_contract = (prior_document.get("contract") or {}).get("sha256")
    prior = [_normalise_prior_record(r, prior_contract)
             for r in prior_document.get("sheets", [])]

    def slot(record: dict) -> tuple[str, bool]:
        return record["element"], bool(record.get("draft"))

    merged = {slot(record): record for record in prior}
    for record in records:
        key = slot(record)
        if record.get("status") == "existing" and key in merged:
            merged[key] = {**merged[key], **{k: v for k, v in record.items() if v is not None}}
        else:
            merged[key] = record

    modes = sorted({(record.get("generator") or {}).get("mode", "unknown")
                    for record in merged.values()})
    receipt.write_text(json.dumps({
        "schema_version": RECEIPT_SCHEMA,
        "receipt_id": f"{contract.data['contract_id']}-SHEETS",
        "contract": contract.receipt_block(stage_name(contract)),
        "specs_from": str(SPEC_DIR.name),
        "by_kind": contract.elements_by_kind(),
        "plans": {k: contract.sheet_plan(k).as_dict() for k in contract.elements_by_kind()},
        "generator_modes": modes,
        "sheets": list(merged.values()),
        "failed": failures,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return receipt


SEMANTIC_CHECKS = (
    "expected_panels_and_views", "identity_or_object_drift", "setting_topology_drift",
    "forbidden_or_extra_text", "named_element_contamination",
    "mood_variant_structure_drift", "duplicate_subject_conditioning_risk",
    "motion_affordance_readability", "mechanical_scale_and_axis_feasibility",
)


def _reference_role_candidates(kind: str, view: str) -> list[str]:
    """Roles a reviewer may approve for one crop; never approval itself."""
    if kind == "setting":
        roles = ["environment_geometry_reference"]
    else:
        roles = ["identity_reference"]
    if kind in {"subject", "setting"} and re.search(
            r"세부|특징|부품|연결|접촉|작동|재질|바닥|벽", view):
        roles.append("motion_affordance_reference")
    return roles


def audit_references(attempt: Path, contract: Contract | None = None) -> dict:
    """Publish selectable panel slots and an honest semantic-review queue.

    Pixel dimensions and hashes are machine facts. Identity, topology and whether a
    crop is safe conditioning input are visual judgments; absent an actual reviewer
    they remain `human_review_required`, never an automatic pass.
    """
    contract = contract or load_contract(attempt)
    stage = stage_dir(attempt, contract)
    manifests = []
    reviews = []
    graph_nodes = {n.get("where_subject_id") for n in
                   contract.spatial_graph.get("nodes", []) if isinstance(n, dict)}
    for element, rules in sorted(contract.elements().items()):
        kind = rules.get("kind", "subject")
        image_path = stage / "output" / "sheets" / f"{element}.png"
        dimensions = None
        if image_path.exists():
            try:
                with Image.open(image_path) as image:
                    dimensions = list(image.size)
            except Exception:  # corrupt media is handled by the pixel gate
                dimensions = None
        panels = []
        for index, view in enumerate(contract.sheet_policy(kind).get("panels") or [], 1):
            panels.append({
                "panel_id": f"{element}-P{index:02d}",
                "subject_id": element,
                "view_state": view,
                "intended_use": "selective_reference_after_review",
                "safe_for_identity_reference": None,
                "safe_for_motion_reference": None,
                "reference_role_candidates": _reference_role_candidates(kind, view),
                "binds_part_ids": [],
                "binds_interaction_site_ids": [],
                "mechanical_fit_evidence": {
                    "tool_capacity_part_id": None,
                    "target_extent_part_id": None,
                    "tool_capacity_mm": None,
                    "target_extent_mm": None,
                    "minimum_capacity_ratio": 1.15,
                    "actual_capacity_ratio": None,
                    "tool_action_plane_part_id": None,
                    "target_axis_part_id": None,
                    "axis_relation": None,
                    "target_angle_deg": None,
                    "max_error_deg": None,
                    "daylight_clearance_visible": None,
                    "opposed_contact_visible": None,
                    "mechanical_truth_over_tool_hero_view": None,
                },
                "contains_duplicate_subjects": None,
                "contains_text": None,
                "crop_coordinates": None,
                "reference_crop_path": None,
                "review_status": "human_review_required",
            })
        manifests.append({
            "subject_id": element,
            "kind": kind,
            "canonical_owner": rules.get("canonical_owner", element),
            "shared_elements": list(rules.get("shared_elements") or []),
            "allowed_exceptions": list(rules.get("allowed_sheet_exceptions") or []),
            "source": str(image_path.relative_to(attempt)),
            "source_dimensions": dimensions,
            "panels": panels,
        })
        checks = []
        for check_id in SEMANTIC_CHECKS:
            applicable = not (
                check_id == "setting_topology_drift" and kind != "setting"
                or check_id == "identity_or_object_drift" and kind == "setting"
                or check_id == "motion_affordance_readability" and kind == "character"
                or check_id == "mechanical_scale_and_axis_feasibility" and kind == "character"
            )
            checks.append({
                "check_id": check_id,
                "status": "human_review_required" if applicable else "not_applicable",
                "reviewer": None,
                "evidence": [],
            })
        if kind == "setting" and element not in graph_nodes:
            checks.append({"check_id": "declared_topology_support", "status": "failed",
                           "reviewer": "pipeline", "evidence": ["spatial graph node missing"]})
        reviews.append({"subject_id": element, "checks": checks,
                        "reference_ready": False,
                        "status": "human_review_required"})

    qa = stage / "qa"
    qa.mkdir(parents=True, exist_ok=True)
    manifest_path = qa / "panel-manifest.json"
    review_path = qa / "semantic-review.json"
    manifest_doc = {
        "schema_version": "sheet-panel-manifest.v1",
        "contract": contract.receipt_block(stage_name(contract)),
        "upstream_state": read_premise_state(attempt, contract),
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "policy": (
            "whole boards are never H3 conditioning inputs; only reviewed selective crops may be "
            "approved for identity, environment geometry or motion affordance roles; a mechanical "
            "motion crop cannot be approved until capacity, target extent, clearance and axis-angle "
            "evidence pass, and mechanical truth takes priority over a three-quarter hero view"
        ),
        "sheets": manifests,
    }
    review_doc = {
        "schema_version": "sheet-semantic-review.v1",
        "contract": contract.receipt_block(stage_name(contract)),
        "upstream_state": read_premise_state(attempt, contract),
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "pixel_generation_complete_is_not_semantic_pass": True,
        "reference_ready": bool(reviews) and all(r["reference_ready"] for r in reviews),
        "status": "human_review_required" if reviews else "missing",
        "reviews": reviews,
    }
    manifest_path.write_text(json.dumps(manifest_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    review_path.write_text(json.dumps(review_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"panel_manifest": str(manifest_path), "semantic_review": str(review_path),
            "reference_ready": review_doc["reference_ready"], "sheets": len(manifests)}


def approve_references(attempt: Path, reviewer: str,
                       allow_source_variance: list[str] | None = None,
                       review_mode: str = "human") -> dict:
    """Promote visually reviewed references without regenerating their pixels.

    A narrowly named source-variance waiver keeps the original file unchanged
    and records the measured dimensions. It is not an implicit global resize or
    a relaxation for any other subject.
    """
    if review_mode not in {"human", "ai_preflight"}:
        raise SheetError("reference review_mode은 human 또는 ai_preflight여야 한다")
    if not reviewer.strip():
        raise SheetError("reference 승인 reviewer가 필요하다")
    contract = load_contract(attempt)
    stage = stage_dir(attempt, contract)
    manifest_path = stage / "qa" / "panel-manifest.json"
    review_path = stage / "qa" / "semantic-review.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        review = json.loads(review_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SheetError(f"reference 승인 문서를 읽을 수 없다: {error}") from error

    waived = set(allow_source_variance or [])
    known = {item.get("subject_id") for item in manifest.get("sheets", [])}
    unknown = sorted(waived - known)
    if unknown:
        raise SheetError(f"선언되지 않은 source variance waiver: {unknown}")
    approved_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    dimensions: dict[str, tuple[list[int], list[int], str]] = {}
    for item in manifest.get("sheets", []):
        subject_id = str(item.get("subject_id"))
        path = attempt / str(item.get("source"))
        if not path.is_file():
            raise SheetError(f"승인할 canonical sheet가 없다: {subject_id} {path}")
        try:
            with Image.open(path) as image:
                actual = list(image.size)
                image.verify()
        except Exception as error:  # noqa: BLE001
            raise SheetError(f"canonical sheet 이미지 오류 {subject_id}: {error}") from error
        target = list(contract.sheet_plan(str(item.get("kind"))).target)
        fit = "exact"
        if actual != target:
            within_tolerance = source_within_pixel_tolerance(tuple(actual), tuple(target))
            if not within_tolerance or (review_mode == "human" and subject_id not in waived):
                raise SheetError(
                    f"{subject_id}: source={actual} target={target}; "
                    "명시된 허용차 승인 없이는 reference-ready가 될 수 없다")
            fit = f"{review_mode}-approved-source-variance-no-resize"
        dimensions[subject_id] = (actual, target, fit)

    for item in review.get("reviews", []):
        subject_id = str(item.get("subject_id"))
        failed = False
        for check in item.get("checks", []):
            if check.get("status") == "human_review_required":
                if review_mode == "ai_preflight":
                    raise SheetError(
                        f"{subject_id}: AI preflight가 {check.get('check_id')}를 판정하지 않았다")
                check["status"] = "passed"
                check["reviewer"] = reviewer
                check["evidence"] = ["explicit user approval recorded by the pipeline"]
            if (review_mode == "ai_preflight" and check.get("status") == "passed" and
                    (not str(check.get("reviewer") or "").strip() or
                     not list(check.get("evidence") or []))):
                raise SheetError(
                    f"{subject_id}: AI preflight {check.get('check_id')}에 reviewer/evidence가 없다")
            if check.get("status") == "failed":
                failed = True
        actual, target, fit = dimensions[subject_id]
        item.update({
            "reference_ready": not failed,
            "status": "approved" if not failed else "failed",
            "reviewer": reviewer,
            "reviewed_at": approved_at,
            "source_dimensions": actual,
            "contract_dimensions": target,
            "dimension_fit": fit,
            "source_variance_waiver": ({
                "approved": True,
                "reviewer": reviewer,
                "reason": (
                    "AI preflight accepted provider variance within the global pixel tolerance"
                    if review_mode == "ai_preflight" else
                    "user explicitly accepted the provider variance"
                ),
                "resize_performed": False,
            } if fit != "exact" else None),
        })
    review.update({
        "reference_ready": bool(review.get("reviews")) and
        all(item.get("reference_ready") for item in review.get("reviews", [])),
        "status": "approved",
        "reviewer": reviewer,
        "reviewed_at": approved_at,
        "review_mode": review_mode,
        "human_approval_required": review_mode == "human",
    })
    review_path.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"semantic_review": str(review_path),
            "reference_ready": review["reference_ready"],
            "reviewer": reviewer, "review_mode": review_mode,
            "source_variance_waivers": sorted(waived)}


def record_ai_sheet_review(attempt: Path, manifest_path: Path, review_path: Path) -> dict:
    """Record one sheet-image verdict and return the next varied work order."""
    attempt = attempt.resolve()
    contract = load_contract(attempt)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        review = json.loads(review_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SheetError(f"sheet AI review 입력을 읽을 수 없다: {error}") from error
    current_mode = load_execution_mode(attempt)
    recorded_mode = manifest.get("execution_mode") or {}
    if (manifest.get("schema_version") != "codex-sheet-jobs.v1" or
            manifest.get("status") != "prepared" or
            Path(str(manifest.get("attempt") or "")).resolve() != attempt or
            (manifest.get("contract") or {}).get("sha256") != contract.digest or
            recorded_mode.get("mode") != current_mode.get("mode") or
            recorded_mode.get("set_at") != current_mode.get("set_at")):
        raise SheetError("sheet AI review manifest의 상태·attempt·contract·execution mode 결속이 다르다")
    if review.get("schema_version") != SHEET_AI_ATTEMPT_REVIEW_SCHEMA:
        raise SheetError("지원하지 않는 sheet AI attempt review schema")
    element = str(review.get("element") or "")
    job = next((item for item in manifest.get("jobs") or []
                if item.get("element") == element), None)
    if not job:
        raise SheetError(f"manifest에 sheet job이 없다: {element}")
    harness = job.get("retry_harness") or {}
    if (harness.get("schema_version") != HARNESS_SCHEMA or
            int(harness.get("max_attempts", 0)) != MAX_GENERATION_ATTEMPTS or
            harness.get("vary_every_retry") is not True or
            harness.get("variation_strategies") != list(VARIATION_STRATEGIES)):
        raise SheetError(f"{element}: adaptive retry harness 계약이 다르다")
    log_path = (attempt / str(harness.get("review_log_path") or "")).resolve()
    try:
        log_path.relative_to(attempt)
    except ValueError as error:
        raise SheetError(f"{element}: review log가 attempt 밖을 가리킨다") from error
    if log_path.exists():
        log = json.loads(log_path.read_text(encoding="utf-8"))
    else:
        log = {
            "schema_version": HARNESS_SCHEMA,
            "element": element,
            "max_attempts": MAX_GENERATION_ATTEMPTS,
            "base_prompt_sha256": job.get("imagegen_prompt_sha256"),
            "attempts": [], "selected_attempt": None,
            "selection_reason": None, "selected_candidate_sha256": None,
        }
    attempts = log.get("attempts") or []
    if log.get("selected_attempt") is not None or len(attempts) >= MAX_GENERATION_ATTEMPTS:
        raise SheetError(f"{element}: sheet retry harness는 이미 종료됐다")
    number = len(attempts) + 1
    expected_criteria = list(harness.get("acceptance_criteria") or [])
    criteria = review.get("criteria") or []
    if [item.get("criterion") for item in criteria] != expected_criteria:
        raise SheetError(f"{element}: sheet AI review 기준이 manifest와 다르다")
    statuses = [item.get("status") for item in criteria]
    decision = review.get("decision")
    if (any(status not in {"pass", "fail"} for status in statuses) or
            decision not in {"pass", "fail"} or
            (decision == "pass") != bool(statuses and all(s == "pass" for s in statuses))):
        raise SheetError(f"{element}: sheet AI 종합 판정과 기준 판정이 유효하지 않다")
    feedback = str(review.get("feedback") or "").strip()
    if decision == "fail" and number < MAX_GENERATION_ATTEMPTS and not feedback:
        raise SheetError(f"{element}: 실패 판정에는 다음 변주용 feedback이 필요하다")
    if not str(review.get("reviewer") or "").strip() or not str(review.get("reviewed_at") or "").strip():
        raise SheetError(f"{element}: reviewer 또는 reviewed_at이 비어 있다")
    candidate_rel = str(harness.get("attempt_path_pattern") or "").format(attempt=number)
    candidate = (attempt / candidate_rel).resolve()
    try:
        candidate.relative_to(attempt)
    except ValueError as error:
        raise SheetError(f"{element}: attempt image가 attempt 밖을 가리킨다") from error
    if not candidate.is_file() or candidate.stat().st_size == 0:
        raise SheetError(f"{element}: 검수할 sheet attempt가 없다: {candidate}")
    correction = "" if number == 1 else str(attempts[-1].get("feedback") or "")
    previous_failed = ([] if number == 1 else
                       list(attempts[-1].get("failed_criteria") or []))
    previous_sha = None if number == 1 else attempts[-1].get("candidate_sha256")
    effective = retry_prompt(
        str(job["imagegen_prompt"]), number, correction,
        failed_criteria=previous_failed, prior_attempt_sha256=previous_sha)
    failed_criteria = [item.get("criterion") for item in criteria
                       if item.get("status") == "fail"]
    attempts.append({
        "attempt": number,
        "variation_strategy": VARIATION_STRATEGIES[number - 1],
        "candidate_path": candidate_rel,
        "candidate_sha256": sha256(candidate),
        "effective_prompt_sha256": prompt_sha256(effective),
        "failed_criteria": failed_criteria,
        "decision": decision, "criteria": criteria, "feedback": feedback,
        "reviewer": review.get("reviewer"), "reviewed_at": review.get("reviewed_at"),
    })
    log["attempts"] = attempts
    selected = decision == "pass" or number == MAX_GENERATION_ATTEMPTS
    selected_path = (attempt / str(job.get("candidate_path") or "")).resolve()
    if selected:
        selected_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(candidate, selected_path)
        log["selected_attempt"] = number
        log["selection_reason"] = "ai_pass" if decision == "pass" else "max_attempts_exhausted"
        log["selected_candidate_sha256"] = sha256(selected_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    if selected:
        return {"status": "selected_for_semantic_review", "element": element,
                "selected_attempt": number, "selection_reason": log["selection_reason"],
                "candidate_path": str(selected_path), "review_log": str(log_path)}
    next_number = number + 1
    return {
        "status": "retry_required", "element": element,
        "next_attempt": next_number,
        "variation_strategy": VARIATION_STRATEGIES[next_number - 1],
        "candidate_path": str((attempt / str(harness["attempt_path_pattern"])
                               .format(attempt=next_number)).resolve()),
        "imagegen_prompt": retry_prompt(
            str(job["imagegen_prompt"]), next_number, feedback,
            failed_criteria=failed_criteria, prior_attempt_sha256=sha256(candidate)),
        "review_log": str(log_path),
    }


def finalize_codex_jobs(attempt: Path, manifest_path: Path,
                        surface: str = "unknown") -> dict:
    """Validate Codex candidates, materialize outputs, and write a v2 receipt."""
    if surface not in CODEX_SURFACES:
        raise SheetError(f"Codex surface는 {sorted(CODEX_SURFACES)} 중 하나여야 한다")
    contract = load_contract(attempt)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SheetError(f"Codex manifest를 읽을 수 없다: {error}") from error
    if manifest.get("schema_version") != "codex-sheet-jobs.v1":
        raise SheetError(f"지원하지 않는 Codex manifest {manifest.get('schema_version')!r}")
    if manifest.get("status") != "prepared":
        raise SheetError(f"Codex manifest 상태가 prepared가 아니다: {manifest.get('status')!r}")
    attempt_root = attempt.resolve()
    if Path(str(manifest.get("attempt", ""))).resolve() != attempt_root:
        raise SheetError("Codex manifest가 다른 attempt를 가리킨다")
    if manifest.get("stage") != stage_name(contract):
        raise SheetError("Codex manifest의 단계가 현재 계약의 sheet 단계와 다르다")
    recorded_digest = (manifest.get("contract") or {}).get("sha256")
    if recorded_digest != contract.digest:
        raise SheetError(
            f"Codex manifest 작성 뒤 계약이 바뀌었다 manifest={recorded_digest} "
            f"current={contract.digest}. 새 manifest를 준비한다")
    current_mode = load_execution_mode(attempt)
    recorded_mode = manifest.get("execution_mode") or {}
    if (recorded_mode.get("mode") != current_mode.get("mode") or
            recorded_mode.get("set_at") != current_mode.get("set_at")):
        raise SheetError("Codex manifest 작성 뒤 execution mode가 바뀌었다. 새 manifest를 준비한다")

    jobs = manifest.get("jobs") or []
    if not jobs:
        raise SheetError("Codex manifest에 생성할 job이 없다. 기존 output을 변경하지 않는다")
    problems = []
    prepared = []
    for job in jobs:
        element = str(job.get("element", ""))
        try:
            entry, prompt_path = _load_prompt_entry(attempt, contract, element)
        except SheetError as error:
            problems.append(str(error))
            continue
        if prompt_sha256(entry["prompt"]) != job.get("prompt_sha256"):
            problems.append(f"{element}: manifest 작성 뒤 prompt가 바뀌었다")
            continue
        if (job.get("definition_content_sha256") != entry.get("definition_content_sha256") or
                job.get("definition_record_sha256_current") !=
                entry.get("definition_record_sha256_current")):
            problems.append(f"{element}: manifest 작성 뒤 정의 내용 또는 기록이 바뀌었다")
            continue
        kind = entry["kind"]
        plan = contract.sheet_plan(kind)
        quality = contract.image_quality("sheet", bool(job.get("draft")))
        imagegen_prompt, render_instruction = codex_generation_prompt(
            entry["prompt"], plan, quality)
        if job.get("requested") != list(plan.target) or job.get("quality") != quality:
            problems.append(f"{element}: manifest의 크기/품질이 현재 계약과 다르다")
            continue
        if (job.get("render_instruction") != render_instruction or
                job.get("imagegen_prompt") != imagegen_prompt or
                job.get("imagegen_prompt_sha256") != prompt_sha256(imagegen_prompt)):
            problems.append(f"{element}: imagegen 계약 크기/high 요청문이 manifest와 다르다")
            continue
        if str(prompt_path.relative_to(attempt)) != job.get("prompt_path"):
            problems.append(f"{element}: prompt 경로가 manifest와 다르다")
            continue
        candidate = (attempt / str(job.get("candidate_path", ""))).resolve()
        target = (attempt / str(job.get("output_path", ""))).resolve()
        try:
            candidate.relative_to(attempt_root)
            target.relative_to(attempt_root)
        except ValueError:
            problems.append(f"{element}: candidate/output 경로가 attempt 밖을 가리킨다")
            continue
        if not candidate.is_file() or candidate.stat().st_size == 0:
            problems.append(f"{element}: imagegen candidate가 없다 {candidate}")
            continue
        if target.exists() and not job.get("overwrite"):
            problems.append(f"{element}: 준비 뒤 output이 생겼다. 덮어쓰지 않는다 {target}")
            continue
        try:
            with Image.open(candidate) as image:
                source_size = list(image.size)
                image.verify()
        except Exception as error:  # noqa: BLE001 - corrupt media should name its decoder error
            problems.append(f"{element}: candidate 이미지 오류 {error}")
            continue
        if not source_within_pixel_tolerance(tuple(source_size), tuple(plan.target)):
            allowed = pixel_tolerance(tuple(plan.target))
            problems.append(
                f"{element}: imagegen 원본이 계약 허용오차를 넘는다 "
                f"source={source_size[0]}x{source_size[1]} "
                f"requested={plan.target[0]}x{plan.target[1]} "
                f"allowed_deficit={allowed[0]}x{allowed[1]}"
            )
            continue
        prepared.append((job, entry, candidate, target, source_size))
    if problems:
        raise SheetError("Codex finalize 중단:\n- " + "\n- ".join(problems))

    records = []
    manifest_id = str(manifest.get("manifest_id", "codex"))
    for job, entry, candidate, target, source_size in prepared:
        element, kind = entry["element"], entry["kind"]
        plan = contract.sheet_plan(kind)
        if target.exists():
            rejected = (stage_dir(attempt, contract) / "rejected" /
                        f"superseded-{manifest_id}" / target.name)
            rejected.parent.mkdir(parents=True, exist_ok=True)
            target.replace(rejected)

        with Image.open(candidate) as source:
            image = source.convert("RGB")
            image, actual_fit = materialize_with_pixel_tolerance(image, tuple(plan.target))
            target.parent.mkdir(parents=True, exist_ok=True)
            image.save(target)

        records.append({
            "element": element,
            "kind": kind,
            "status": "generated",
            "generator": {
                "mode": GENERATOR_CODEX,
                "invocation": "interactive-imagegen-skill",
                "surface": surface,
                "model": "gpt-image-2",
                "usage_accounting": "codex-general-usage",
                "token_detail": "not-exposed",
            },
            "model": "gpt-image-2",
            "requested": list(plan.target),
            "source_dimensions": source_size,
            "delivered": list(plan.target),
            "fit": actual_fit,
            "pixel_tolerance": {
                "max_ratio": PIXEL_TOLERANCE_RATIO,
                "max_pixels_per_axis": PIXEL_TOLERANCE_MAX_PIXELS,
                "allowed_deficit": list(pixel_tolerance(tuple(plan.target))),
            },
            "quality": job.get("quality"),
            "draft": bool(job.get("draft")),
            "prompt_sha256": job["prompt_sha256"],
            "imagegen_prompt_sha256": job["imagegen_prompt_sha256"],
            "definition_sha256": job["definition_sha256"],
            "definition_content_sha256": job.get("definition_content_sha256"),
            "definition_record_sha256_current": job.get("definition_record_sha256_current"),
            "contract_sha256": contract.digest,
            "candidate_path": str(candidate.relative_to(attempt_root)),
            "output_path": str(target.relative_to(attempt_root)),
            "source_bytes": candidate.stat().st_size,
            "source_sha256": sha256(candidate),
            "bytes": target.stat().st_size,
            "sha256": sha256(target),
            "created_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        })

    receipt = _write_receipt(attempt, contract, records, [])
    reference_audit = audit_references(attempt, contract)
    manifest["status"] = "finalized"
    manifest["finalized_at"] = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    manifest["surface"] = surface
    manifest["receipt"] = str(receipt.relative_to(attempt))
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "generator": GENERATOR_CODEX,
        "finalized": len(records),
        "receipt": str(receipt),
        "outputs": [record["output_path"] for record in records],
        "reference_audit": reference_audit,
    }


def run(attempt: Path, kinds: list[str] | None = None, only: list[str] | None = None,
        model: str = DEFAULT_MODEL, force: bool = False, draft: bool = False,
        generator: str = GENERATOR_API, compose_only: bool = False) -> dict:
    if generator == GENERATOR_CODEX:
        if compose_only:
            contract = load_contract(attempt)
            wanted = _wanted_elements(contract, kinds, only)
            pack_dir = stage_dir(attempt, contract) / "prompts"
            pack_dir.mkdir(parents=True, exist_ok=True)
            entries, failures = [], []
            for element in sorted(wanted):
                try:
                    entry = compose_prompt_local(attempt, contract, element)
                    (pack_dir / f"{element}.json").write_text(
                        json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
                    entries.append(entry)
                    print(f"{element}: 로컬 프롬프트 {len(entry['prompt'])}자", flush=True)
                except (SheetError, ContractError) as error:
                    failures.append({"element": element, "problem": str(error)})
                    print(f"{element}: 실패 {error}", flush=True)
            return {
                "composed": len(entries),
                "rendered": 0,
                "failed": failures,
                "prompt_packs": [
                    str((pack_dir / f"{entry['element']}.json").relative_to(attempt))
                    for entry in entries
                ],
                "authoring_pipeline": PROMPT_AUTHORING_PIPELINE,
                "compiler": LOCAL_PROMPT_COMPILER,
                "api_called": False,
            }
        return prepare_codex_jobs(attempt, kinds, only, force, draft)
    if generator != GENERATOR_API:
        raise SheetError(f"지원하지 않는 generator {generator!r}")

    contract = load_contract(attempt)
    wanted = _wanted_elements(contract, kinds, only)

    pack_dir = stage_dir(attempt, contract) / "prompts"
    pack_dir.mkdir(parents=True, exist_ok=True)
    entries, receipts, failures = [], [], []
    for element in sorted(wanted):
        # 한 요소가 실패해도 나머지의 기록까지 잃지 않는다. 명세 하나가 없어서
        # 이미 만든 시트 셋의 영수증이 통째로 날아간 적이 있다.
        try:
            entry = compose_prompt(attempt, contract, element, model)
            (pack_dir / f"{element}.json").write_text(
                json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
            entries.append(entry)
            print(f"{element}: 프롬프트 {len(entry['prompt'])}자"
                  + (f", 조항 보충 {entry['clauses_appended']}" if entry["clauses_appended"] else ""),
                  flush=True)
            if compose_only:
                continue
            receipts.append(render(attempt, contract, entry, force, draft))
            print(f"{element}: {receipts[-1]['status']} "
                  f"{receipts[-1].get('delivered', '')}", flush=True)
        except (SheetError, ContractError) as error:
            failures.append({"element": element, "problem": str(error)})
            print(f"{element}: 실패 {error}", flush=True)

    if compose_only:
        return {
            "composed": len(entries),
            "rendered": 0,
            "failed": failures,
            "prompt_packs": [
                str((pack_dir / f"{entry['element']}.json").relative_to(attempt))
                for entry in entries
            ],
            "authoring_pipeline": PROMPT_AUTHORING_PIPELINE,
        }

    receipt = _write_receipt(attempt, contract, receipts, failures)
    reference_audit = audit_references(attempt, contract)
    return {"composed": len(entries), "rendered": len(receipts),
            "failed": failures, "receipt": str(receipt),
            "reference_audit": reference_audit}


def main() -> int:
    parser = argparse.ArgumentParser(description="정의된 요소를 레퍼런스 보드로 굳힌다")
    parser.add_argument("attempt", type=Path)
    parser.add_argument("--kind", nargs="*",
                        help="계약의 sheet.kinds 에 선언된 종류")
    parser.add_argument("--only", nargs="*", help="요소 이름")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--generator", choices=[GENERATOR_API, GENERATOR_CODEX],
                        default=GENERATOR_API,
                        help="api는 Python 클라이언트, codex는 imagegen 작업 명세만 준비")
    parser.add_argument("--compose-only", action="store_true",
                        help="구조화 메타 프롬프트로 prompt pack만 작성. codex는 로컬 컴파일, api는 텍스트 모델")
    parser.add_argument("--finalize-manifest", type=Path,
                        help="Codex imagegen 결과를 검사하고 영수증을 확정")
    parser.add_argument("--record-ai-review", type=Path, metavar="MANIFEST",
                        help="한 sheet image attempt의 AI 검수 결과를 기록")
    parser.add_argument("--review-file", type=Path,
                        help="--record-ai-review에 사용할 review JSON")
    parser.add_argument("--codex-surface", choices=sorted(CODEX_SURFACES), default="unknown",
                        help="영수증에 남길 실행 표면")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--draft", action="store_true",
                        help="확인용 별도 경로. 실제 품질은 계약의 draft_quality를 따른다")
    parser.add_argument("--audit-references", action="store_true",
                        help="이미지를 재생성하지 않고 panel manifest와 semantic review를 갱신")
    parser.add_argument("--approve-references", action="store_true",
                        help="완료된 의미 검수를 semantic review에 기록")
    parser.add_argument("--by", help="--approve-references 승인자")
    parser.add_argument("--review-mode", choices=["human", "ai_preflight"], default="human",
                        help="사람 승인 또는 AI 시각 preflight")
    parser.add_argument("--allow-source-variance", nargs="*", default=[],
                        help="재생성·리사이즈 없이 좁은 원본 픽셀 허용차를 승인할 subject id")
    args = parser.parse_args()

    try:
        if args.approve_references:
            if not args.by:
                raise SheetError("--approve-references에는 --by가 필요하다")
            result = approve_references(
                args.attempt, args.by, args.allow_source_variance, args.review_mode)
        elif args.audit_references:
            result = audit_references(args.attempt)
        elif args.record_ai_review:
            if args.generator != GENERATOR_CODEX or not args.review_file:
                raise SheetError(
                    "--record-ai-review는 --generator codex 및 --review-file과 함께 쓴다")
            result = record_ai_sheet_review(
                args.attempt, args.record_ai_review, args.review_file)
        elif args.finalize_manifest:
            if args.generator != GENERATOR_CODEX:
                raise SheetError("--finalize-manifest는 --generator codex와 함께 쓴다")
            result = finalize_codex_jobs(
                args.attempt, args.finalize_manifest, args.codex_surface)
        else:
            result = run(args.attempt, args.kind, args.only, args.model,
                         args.force, args.draft, args.generator, args.compose_only)
    except (SheetError, ContractError) as error:
        print(json.dumps({"ok": False, "problem": str(error)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
