"""The terms of one attempt, in a form its tools have to obey rather than restate.

The failure this exists to stop, seen whole in the supercar run: a brief
declared four forbidden things and a 1080x1920 frame; every forbidden thing was
then retyped by hand into a constant inside each generation tool; the frame was
retyped as 576x1024 in the runner and 1080x1920 in the compositor; nothing
connected the three; the film was generated at 576x1024, upscaled 1.875x, and
no receipt recorded either number. A document nobody reads binds nobody.

So terms are loaded, not copied. A tool asks for the clauses that bind its
stage and appends what it gets. A tool asks how large to make a picture and is
told, from the frame, so changing the frame in one place changes every image
the run produces.

Nothing here knows about cars, or circuits, or any particular film. It knows
about frames, roles and clauses. A new project writes its own contract.json and
uses the same loader, the same gate and the same receipt block.

Three ideas carry the whole thing.

**Frames.** `frame` is the native production raster used for plates and motion.
`delivery_frame` is the final edit raster. Keeping them separate makes any crop
or upscale an explicit recorded transform instead of disguising a platform
delivery size as a model generation request. Reference-only stages are left
out of both `applies_to` lists.

**Image roles.** An image provider offers a fixed menu of sizes and none of
them is likely to be the frame. A role says what an image is for, and the
contract works out which menu item to request and how to bring it to size. A
plate is a frame of the film and stays close to the native video raster. A
production sheet never reaches the screen and uses the explicit reference
raster declared for its generation surface.

**Clauses.** Text that must appear in a prompt, bound to the stages it applies
to. A clause may be conditional on a flag the caller passes, so one clause can
say two different things about a cut that holds a person and one that does not.

Every receipt carries the contract digest, which is what lets a later reader
tell whether a file was made under the terms as they now stand.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .h3_runtime import NATIVE_FPS, NATIVE_FRAME_SIZES, PROFILE_ID
from .run_layout import STAGE_ROLES

CONTRACT_FILENAME = "contract.json"
SCENARIO_DIR = Path(__file__).resolve().parent / "scenario_structures"
SIZE_RE = re.compile(r"^(\d+)x(\d+)$")

REQUIRED_TOP = {"contract_id", "attempt", "frame", "delivery_frame", "clauses"}
REQUIRED_FRAME = {"width", "height", "fps"}
REQUIRED_DELIVERY_FRAME = {"width", "height", "fps", "applies_to", "transform"}
DELIVERY_MODES = {"frame", "max", "native"}


class ContractError(ValueError):
    """The contract is missing, malformed, or asks for something impossible."""


# --------------------------------------------------------------------- frame


@dataclass(frozen=True)
class Frame:
    width: int
    height: int
    fps: int

    @property
    def pixels(self) -> int:
        return self.width * self.height

    @property
    def aspect(self) -> float:
        return self.width / self.height

    @property
    def portrait(self) -> bool:
        return self.height > self.width

    def as_dict(self) -> dict:
        return {"width": self.width, "height": self.height, "fps": self.fps}

    def __str__(self) -> str:
        return f"{self.width}x{self.height}"


@dataclass(frozen=True)
class ImagePlan:
    """What to order from the image API for one role, and what to do with it."""

    role: str
    target: tuple[int, int]
    api_size: str
    fit: str        # exact | crop-and-downscale | crop-and-upscale
    scale: float    # target pixels over api pixels
    why: str

    def as_dict(self) -> dict:
        return {"role": self.role, "target": list(self.target), "api_size": self.api_size,
                "fit": self.fit, "scale": self.scale, "why": self.why}


def _parse_size(text: str) -> tuple[int, int]:
    match = SIZE_RE.match(str(text).strip())
    if not match:
        raise ContractError(f"크기 표기가 WxH 가 아니다: {text!r}")
    return int(match.group(1)), int(match.group(2))


DEFAULT_MAX_OVERSAMPLE = 4.0


def _closest(sizes: Iterable[tuple[int, int]], target: tuple[int, int],
             max_oversample: float = DEFAULT_MAX_OVERSAMPLE) -> tuple[int, int]:
    """Nearest aspect first, then the least excess pixels, within a spending limit.

    Aspect comes before area because a size with the wrong shape has to be
    cropped, and cropping throws away composition the prompt asked for.

    But aspect alone will spend anything. Once the catalogue gained 3840-edge
    sizes, a 768x1344 plate started ordering 2160x3840 because that aspect is
    nearer, which is eight times the pixels for a frame that gets scaled back
    down. `max_oversample` bounds how much larger than the target a size may be
    before its better shape stops being worth it. A role that genuinely wants
    every pixel raises it.
    """
    tw, th = target
    want_aspect = tw / th
    want_pixels = tw * th

    affordable = [s for s in sizes if s[0] * s[1] <= want_pixels * max_oversample]
    big_enough = [s for s in (affordable or sizes) if s[0] * s[1] >= want_pixels]
    pool = big_enough or affordable or list(sizes)
    return min(pool, key=lambda s: (round(abs(s[0] / s[1] - want_aspect), 4), s[0] * s[1]))


# ------------------------------------------------------------------ contract


def find_contract(target: Path) -> Path:
    """A file, or the earliest stage of an attempt that publishes one.

    Stage folders are numbered, so the lowest number is the earliest stage, and
    that is where terms belong. Nothing here hard-codes a stage name, because a
    different project may not number its stages the same way.
    """
    target = Path(target)
    if target.is_file():
        return target
    direct = target / CONTRACT_FILENAME
    if direct.exists():
        return direct
    found = sorted(target.glob(f"*/output/{CONTRACT_FILENAME}"))
    if not found:
        raise ContractError(
            f"계약이 없다: {target} 아래 어느 단계에도 {CONTRACT_FILENAME} 이 없다")
    return found[0]


@dataclass(frozen=True)
class Contract:
    path: Path
    root: Path
    data: dict
    digest: str

    # ------------------------------------------------------------- loading

    @classmethod
    def load(cls, target: Path) -> "Contract":
        path = find_contract(Path(target))
        raw = path.read_bytes()
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as error:
            raise ContractError(f"{path}: JSON 아님. {error}") from error

        problems = validate(data)
        if problems:
            raise ContractError(f"{path.name}: " + " / ".join(problems))

        # attempt root is two levels above <stage>/output/contract.json
        root = path.parents[2] if path.parent.name == "output" else path.parent
        return cls(path=path, root=root, data=data,
                   digest=hashlib.sha256(raw).hexdigest()[:16])

    @property
    def rel_path(self) -> str:
        try:
            return self.path.relative_to(self.root).as_posix()
        except ValueError:
            return self.path.name

    # --------------------------------------------------------------- frame

    @property
    def frame(self) -> Frame:
        f = self.data["frame"]
        return Frame(int(f["width"]), int(f["height"]), int(f["fps"]))

    def frame_binds(self, stage: str) -> bool:
        """Whether a stage delivers native production pixels."""
        allowed = self.data["frame"].get("applies_to")
        return stage in allowed if allowed is not None else True

    @property
    def upscale_allowed(self) -> bool:
        return bool(self.data["frame"].get("upscale", {}).get("allowed", False))

    @property
    def delivery_frame(self) -> Frame:
        f = self.data["delivery_frame"]
        return Frame(int(f["width"]), int(f["height"]), int(f["fps"]))

    def delivery_frame_binds(self, stage: str) -> bool:
        """Whether a stage delivers final distribution pixels."""
        return stage in self.data["delivery_frame"].get("applies_to", [])

    @property
    def delivery_transform(self) -> dict:
        return dict(self.data["delivery_frame"].get("transform") or {})

    def frame_for_stage(self, stage: str) -> Frame | None:
        """The exact raster a stage must leave on disk, if it delivers picture."""
        if self.delivery_frame_binds(stage):
            return self.delivery_frame
        if self.frame_binds(stage):
            return self.frame
        return None

    # --------------------------------------------------------------- image

    @property
    def image(self) -> dict:
        return self.data.get("image", {})

    @property
    def api_sizes(self) -> list[tuple[int, int]]:
        listed = self.image.get("api_sizes") or []
        if not listed:
            raise ContractError("image.api_sizes 가 없다. 모델이 내주는 크기를 계약이 알아야 한다")
        return [_parse_size(s) for s in listed]

    def image_plan(self, role: str) -> ImagePlan:
        """How large to order, and how to bring it to what the role needs.

        The frame is never hard-coded into a tool. A plate becomes a frame of
        the film, so its target is the frame, and if the frame changes in the
        contract the plate follows without anyone editing a tool. A sheet is
        conditioning input that never reaches the screen, so it takes the
        largest size the API offers in the orientation asked for.
        """
        roles = self.image.get("roles") or {}
        if role not in roles:
            raise ContractError(f"image.roles 에 {role!r} 가 없다. 있는 것: {sorted(roles)}")
        cfg = roles[role]
        mode = cfg.get("deliver_at", "frame")
        if mode not in DELIVERY_MODES:
            raise ContractError(f"{role}.deliver_at 은 {sorted(DELIVERY_MODES)} 중 하나여야 한다")

        sizes = self.api_sizes
        frame = self.frame

        limit = float(cfg.get("max_oversample", DEFAULT_MAX_OVERSAMPLE))
        # 긴 변 상한. 과금이 픽셀에 비례하므로 품질을 어디서 멈출지가 곧 예산이다.
        cap = int(cfg.get("max_edge", 0) or 0)
        if cap:
            capped = [s for s in sizes if max(s) <= cap]
            if capped:
                sizes = capped
        if mode == "frame":
            target = (frame.width, frame.height)
            api = _closest(sizes, target, limit)
        else:
            want = cfg.get("orientation", "portrait" if frame.portrait else "landscape")
            # 정사각형은 가로도 세로도 아니다. 명시적으로 요청할 때만 고른다.
            # 이걸 안 걸러서 16:9 보드가 2048x2048 로 나갔다.
            shape = {"portrait": lambda s: s[1] > s[0],
                     "landscape": lambda s: s[0] > s[1],
                     "square": lambda s: s[0] == s[1]}.get(want, lambda s: True)
            pool = [s for s in sizes if shape(s)] or sizes
            explicit_targets = cfg.get("target_sizes") or {}
            explicit = explicit_targets.get(want) or cfg.get("target_size")
            if explicit:
                target = _parse_size(explicit)
                api = _closest(pool, target, limit)
            else:
                api = max(pool, key=lambda s: s[0] * s[1])
                target = api

        scale = round((target[0] * target[1]) / (api[0] * api[1]), 4)
        if api == target:
            fit = "exact"
        elif api[0] * api[1] >= target[0] * target[1]:
            fit = "crop-and-downscale"
        else:
            fit = "crop-and-upscale"
        return ImagePlan(role=role, target=target, api_size=f"{api[0]}x{api[1]}",
                         fit=fit, scale=scale, why=cfg.get("why", ""))

    # --------------------------------------------------------------- sheet

    def sheet_policy(self, kind: str) -> dict:
        """How many views a sheet of this kind carries, and what they show.

        Three kinds, because three things need pinning and they need pinning
        differently. A character is pinned by face, build and clothing seen
        around. A subject is pinned by its form seen around. A setting has no
        around: it is pinned by the same place at different distances, because
        what has to stay constant is the geometry and the light, not a silhouette.

        Any kind may have several elements. One film can carry two presenters
        and three locations, and each gets its own sheet.
        """
        policies = (self.data.get("sheet") or {}).get("kinds") or {}
        if kind not in policies:
            raise ContractError(
                f"sheet.kinds 에 {kind!r} 가 없다. 있는 것: {sorted(policies)}")
        return policies[kind]

    def sheet_plan(self, kind: str) -> ImagePlan:
        """Sheet size per kind, because the kinds are not the same shape.

        A character board laid out in three columns wants landscape; a subject
        turnaround may want portrait. Resolving this off the `sheet` role alone
        would force one orientation on all three and quietly crop whichever kind
        disagreed. The kind's own orientation wins, and the role's is the
        fallback.
        """
        policy = self.sheet_policy(kind)
        roles = self.image.get("roles") or {}
        base = dict(roles.get("sheet") or {"deliver_at": "max"})
        if policy.get("orientation"):
            base["orientation"] = policy["orientation"]
        if policy.get("why"):
            base["why"] = policy["why"]

        merged = json.loads(json.dumps(self.data))
        merged.setdefault("image", {}).setdefault("roles", {})[f"sheet:{kind}"] = base
        twin = Contract(path=self.path, root=self.root, data=merged, digest=self.digest)
        return twin.image_plan(f"sheet:{kind}")

    def elements(self, kind: str | None = None) -> dict[str, dict]:
        """Declared elements, optionally of one kind. Several per kind is normal."""
        declared = (self.data.get("subjects") or {}).get("declared") or {}
        if kind is None:
            return dict(declared)
        return {name: rules for name, rules in declared.items()
                if rules.get("kind") == kind}

    def elements_by_kind(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for name, rules in self.elements().items():
            out.setdefault(rules.get("kind", "subject"), []).append(name)
        return {k: sorted(v) for k, v in sorted(out.items())}

    @property
    def image_model(self) -> str:
        return self.image.get("model", "")

    def image_quality(self, role: str | None = None, draft: bool = False) -> str:
        """Quality is where the money is, not size.

        Measured on one board: at 2048x1152 the low tier came back at 157 output
        tokens and the high tier at 5,650, a factor of thirty-six, while the same
        tier at 1024x1024 and at 2048x1152 differed by less than a third and in
        the wrong direction. Size barely moves the bill. The tier moves it.

        A role may name separate final and draft tiers. The project template
        deliberately pins sheets to high in both cases: a draft may use a
        separate output path, but Codex app/CLI must not quietly turn a
        contract-sized reference board into a low-quality preview.
        """
        cfg = (self.image.get("roles") or {}).get(role or "", {})
        if draft:
            return cfg.get("draft_quality") or self.image.get("draft_quality") or "low"
        return cfg.get("quality") or self.image.get("quality", "high")

    # ------------------------------------------------------------- clauses

    @staticmethod
    def clause_text_variants(clause: dict) -> list[str]:
        """Return every literal prompt branch a clause can contribute."""
        return [str(clause[key]) for key in ("en", "en_true", "en_false")
                if clause.get(key)]

    @staticmethod
    def clause_scope_applies(clause: dict, stage: str,
                             subject_kind: str | None = None,
                             element: str | None = None) -> bool:
        """Resolve stage/kind/element scope without resolving a condition branch."""
        if stage not in clause["applies_to"]:
            return False
        kinds = clause.get("subject_kinds") or []
        if kinds and subject_kind not in kinds:
            return False
        elements = clause.get("elements") or []
        if elements and element not in elements:
            return False
        return True

    def excluded_clauses_for(self, stage: str, subject_kind: str | None = None,
                             element: str | None = None) -> list[dict]:
        """Clauses bound to a stage but excluded from this prompt by its scope."""
        return [clause for clause in self.data["clauses"]
                if stage in clause["applies_to"]
                and not self.clause_scope_applies(
                    clause, stage, subject_kind, element)]

    def clauses_for(self, stage: str, conditions: dict | None = None,
                    subject_kind: str | None = None,
                    element: str | None = None) -> list[dict]:
        conditions = conditions or {}
        out = []
        for clause in self.data["clauses"]:
            if not self.clause_scope_applies(clause, stage, subject_kind, element):
                continue
            flag = clause.get("when")
            if flag:
                if flag not in conditions:
                    continue
                text = clause["en_true"] if conditions[flag] else clause["en_false"]
            else:
                text = clause["en"]
            out.append({"id": clause["id"], "text": text})
        return out

    def clause_text(self, stage: str, conditions: dict | None = None,
                    subject_kind: str | None = None,
                    element: str | None = None) -> str:
        """Exactly the string a tool appends to its prompt."""
        return " ".join(c["text"] for c in self.clauses_for(
            stage, conditions, subject_kind, element))

    def clause_ids(self, stage: str, conditions: dict | None = None,
                   subject_kind: str | None = None,
                   element: str | None = None) -> list[str]:
        return [c["id"] for c in self.clauses_for(
            stage, conditions, subject_kind, element)]

    @property
    def condition_flags(self) -> list[str]:
        return sorted({c["when"] for c in self.data["clauses"] if c.get("when")})

    @property
    def bound_stages(self) -> list[str]:
        return sorted({s for c in self.data["clauses"] for s in c["applies_to"]})

    # ------------------------------------------------------------- receipt

    def receipt_block(self, stage: str, conditions: dict | None = None,
                      role: str | None = None) -> dict:
        """Goes into every receipt, so a file traces back to the terms it was made under."""
        block = {
            "source": self.rel_path,
            "contract_id": self.data["contract_id"],
            "sha256": self.digest,
            "frame": self.frame.as_dict(),
            "delivery_frame": self.delivery_frame.as_dict(),
            "upscale_allowed": self.upscale_allowed,
            "clauses_applied": self.clause_ids(stage, conditions),
        }
        stage_frame = self.frame_for_stage(stage)
        if stage_frame:
            block["stage_frame"] = stage_frame.as_dict()
        if self.delivery_frame_binds(stage):
            block["delivery_transform"] = self.delivery_transform
        if role:
            block["image_plan"] = self.image_plan(role).as_dict()
        return block

    # ---------------------------------------------------------- scenario

    def scenario_structure(self) -> dict:
        """The acts this film is built from, and how long each should run.

        Not an enum. A first pass at this listed four forms and eight more came
        to mind within a minute: comparison, countdown, before-and-after,
        reaction, montage, testimonial, advert, demonstration. Enumerating them
        in code means editing code whenever a new one turns up, which is the
        thing the contract exists to avoid.

        So the contract declares its own acts, exactly as it declares sheet
        kinds and forbidden clauses. `scenario_structures/` holds starting
        points; a project that needs a shape none of them describe writes it.
        """
        block = self.data.get("scenario") or {}
        named = block.get("structure_id")
        if block.get("acts"):
            return block
        if named:
            path = SCENARIO_DIR / f"{named}.json"
            if not path.exists():
                raise ContractError(
                    f"시나리오 구조가 없다: {named}. 있는 것: "
                    f"{sorted(p.stem for p in SCENARIO_DIR.glob('*.json'))}")
            loaded = json.loads(path.read_text(encoding="utf-8"))
            return {**loaded, **{k: v for k, v in block.items() if k != "structure_id"}}
        raise ContractError("scenario.acts 도 scenario.structure_id 도 없다")

    def acts(self) -> list[dict]:
        return list(self.scenario_structure().get("acts", []))

    def act_ids(self) -> list[str]:
        return [a["id"] for a in self.acts()]

    @property
    def spatial_graph(self) -> dict:
        """Declared places and traversable links; photography is deliberately absent."""
        return dict((self.data.get("scenario") or {}).get("spatial_graph") or {})

    # ------------------------------------------------------------- stages

    def stage_for(self, role: str, fallback: str) -> str:
        """Which stage plays a role in this project.

        A module that hard-codes `01-premise` works for one numbering scheme and
        breaks the moment a project inserts a stage or starts at zero. The
        contract names the stage that holds definitions and the stage that holds
        sheets; the modules ask.
        """
        return (self.data.get("stages") or {}).get(role, fallback)

    def stage_dir(self, role: str, fallback: str) -> str:
        return self.stage_for(role, fallback)

    @property
    def text_model(self) -> str:
        """The reasoning model. Named by the contract so a project can change it."""
        return (self.data.get("text") or {}).get("model", "")

    @property
    def runtime_contract(self) -> dict:
        """Stage-01-owned edit-runtime intent.

        Historical attempts only declared ``duration_seconds``.  They remain a
        fixed-runtime contract, but no later stage may silently substitute its
        own default (45, 60, or otherwise).  New attempts may declare a fixed
        target, a bounded range, or an open runtime whose final value is chosen
        in editorial review.
        """
        declared = self.data.get("runtime_contract")
        if isinstance(declared, dict) and declared:
            return dict(declared)
        legacy = self.data.get("duration_seconds")
        if isinstance(legacy, (int, float)) and not isinstance(legacy, bool) and legacy > 0:
            return {
                "mode": "fixed",
                "target_seconds": float(legacy),
                "source": "legacy_duration_seconds",
            }
        return {"mode": "open", "source": "stage01_not_yet_fixed"}

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)


# ---------------------------------------------------------------- validation


def validate(data: dict) -> list[str]:
    """Everything wrong with a contract, as a list, without raising."""
    problems: list[str] = []

    missing = REQUIRED_TOP - set(data)
    if missing:
        problems.append(f"빠진 항목 {sorted(missing)}")
        return problems

    runtime = data.get("runtime_contract")
    if runtime is not None:
        if not isinstance(runtime, dict):
            problems.append("runtime_contract 는 객체여야 한다")
        else:
            mode = runtime.get("mode")
            if mode not in {"fixed", "range", "open"}:
                problems.append("runtime_contract.mode 은 fixed/range/open 중 하나여야 한다")
            if mode == "fixed":
                value = runtime.get("target_seconds")
                if (not isinstance(value, (int, float)) or isinstance(value, bool)
                        or value <= 0):
                    problems.append("fixed runtime_contract.target_seconds 는 양수여야 한다")
            if mode == "range":
                low, high = runtime.get("min_seconds"), runtime.get("max_seconds")
                numeric = all(isinstance(value, (int, float)) and not isinstance(value, bool)
                              for value in (low, high))
                if not numeric or low <= 0 or high < low:
                    problems.append("range runtime_contract에는 유효한 min_seconds/max_seconds가 필요하다")

    missing = REQUIRED_FRAME - set(data["frame"])
    if missing:
        problems.append(f"frame 에 빠진 항목 {sorted(missing)}")

    delivery = data["delivery_frame"]
    missing = REQUIRED_DELIVERY_FRAME - set(delivery)
    if missing:
        problems.append(f"delivery_frame 에 빠진 항목 {sorted(missing)}")

    for name, block in (("frame", data["frame"]), ("delivery_frame", delivery)):
        for key in ("width", "height", "fps"):
            value = block.get(key)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                problems.append(f"{name}.{key} 는 양의 정수여야 한다")

    frame = data["frame"]
    production_stages = set(frame.get("applies_to") or [])
    delivery_stages = set(delivery.get("applies_to") or [])
    overlap = production_stages & delivery_stages
    if overlap:
        problems.append(f"frame 과 delivery_frame 적용 단계가 겹친다: {sorted(overlap)}")

    if all(isinstance(frame.get(k), int) for k in ("width", "height", "fps")):
        motion = data.get("motion") or {}
        declared_motion_stage = (data.get("stages") or {}).get("motion")
        if declared_motion_stage and not motion:
            problems.append("stages.motion 이 있으면 motion.runtime 계약이 필요하다")
        if motion:
            runtime = motion.get("runtime")
            if runtime != PROFILE_ID:
                problems.append(f"지원하지 않는 motion.runtime {runtime!r}")
            else:
                size = (frame["width"], frame["height"])
                if size not in NATIVE_FRAME_SIZES:
                    allowed = ", ".join(f"{w}x{h}" for w, h in NATIVE_FRAME_SIZES)
                    problems.append(
                        f"{PROFILE_ID} frame 은 {allowed} 중 하나여야 한다: "
                        f"{frame['width']}x{frame['height']}")
                if frame["fps"] != NATIVE_FPS:
                    problems.append(
                        f"{PROFILE_ID} fps 는 {NATIVE_FPS}여야 한다: {frame['fps']}")
                motion_stage = (data.get("stages") or {}).get("motion", "06-motion")
                if production_stages and motion_stage not in production_stages:
                    problems.append(f"frame.applies_to 에 motion 단계 {motion_stage!r}가 없다")

    if all(isinstance(delivery.get(k), int) for k in ("width", "height", "fps")):
        if delivery.get("fps") != frame.get("fps"):
            problems.append("delivery_frame.fps 는 frame.fps 와 같아야 한다")
        transform = delivery.get("transform") or {}
        source_size = (frame.get("width"), frame.get("height"))
        target_size = (delivery.get("width"), delivery.get("height"))
        if target_size != source_size:
            if transform.get("allowed") is not True:
                problems.append("delivery_frame 크기가 다르면 transform.allowed=true 여야 한다")
            if transform.get("operation") != "center-crop-and-scale":
                problems.append(
                    "delivery_frame 크기가 다르면 transform.operation 은 "
                    "'center-crop-and-scale' 이어야 한다")
            crop = transform.get("crop") or {}
            cw, ch = crop.get("width"), crop.get("height")
            scale = transform.get("scale")
            if not all(isinstance(v, int) and not isinstance(v, bool) and v > 0
                       for v in (cw, ch)):
                problems.append("delivery_frame.transform.crop 에 양의 width/height 가 필요하다")
            elif all(isinstance(v, int) and v > 0 for v in source_size + target_size):
                if cw > frame["width"] or ch > frame["height"]:
                    problems.append("delivery_frame.transform.crop 이 frame 보다 클 수 없다")
                if delivery["width"] * ch != delivery["height"] * cw:
                    problems.append("delivery_frame.transform.crop 비율이 납품 프레임과 다르다")
                expected_scale = delivery["width"] / cw
                if (not isinstance(scale, (int, float)) or isinstance(scale, bool)
                        or abs(float(scale) - expected_scale) > 0.000001):
                    problems.append(
                        "delivery_frame.transform.scale 이 crop에서 납품 프레임으로 가는 "
                        "균일 배율과 다르다")
        elif transform.get("allowed") is True and transform.get("operation") != "none":
            problems.append("frame 과 delivery_frame 이 같으면 transform.operation 은 'none' 이어야 한다")

    seen: set[str] = set()
    for clause in data["clauses"]:
        for key in ("id", "applies_to"):
            if key not in clause:
                problems.append(f"조항에 {key} 없음: {clause}")
        cid = clause.get("id", "?")
        if cid in seen:
            problems.append(f"조항 id 중복 {cid}")
        seen.add(cid)
        if clause.get("when"):
            if not (clause.get("en_true") and clause.get("en_false")):
                problems.append(f"조건부 조항 {cid} 에 en_true/en_false 가 필요하다")
        elif not clause.get("en"):
            problems.append(f"조항 {cid} 에 en 이 없다")
        unknown_kinds = set(clause.get("subject_kinds") or []) - {"character", "subject", "setting"}
        if unknown_kinds:
            problems.append(f"조항 {cid} 의 subject_kinds 오류 {sorted(unknown_kinds)}")

    sheet = data.get("sheet") or {}
    kinds = sheet.get("kinds") or {}
    for name, policy in kinds.items():
        if not policy.get("panels"):
            problems.append(f"sheet.kinds.{name} 에 panels 가 없다")
    declared = (data.get("subjects") or {}).get("declared") or {}
    for element, rules in declared.items():
        kind = rules.get("kind")
        if kinds and kind not in kinds:
            problems.append(f"{element} 의 kind 가 {kind!r} 인데 sheet.kinds 에 없다")
        owner = rules.get("canonical_owner", element)
        if owner not in declared:
            problems.append(f"{element} 의 canonical_owner {owner!r} 가 선언되지 않았다")

    graph = (data.get("scenario") or {}).get("spatial_graph") or {}
    nodes = graph.get("nodes") or []
    node_ids = {n.get("id") for n in nodes if isinstance(n, dict)}
    if len(node_ids) != len(nodes):
        problems.append("scenario.spatial_graph.nodes 에 id 누락 또는 중복이 있다")
    for node in nodes:
        owner = node.get("where_subject_id")
        if owner not in declared or declared.get(owner, {}).get("kind") != "setting":
            problems.append(f"공간 node {node.get('id')} 의 setting owner {owner!r} 오류")
    for edge in graph.get("edges") or []:
        if edge.get("from") not in node_ids or edge.get("to") not in node_ids:
            problems.append(f"공간 edge {edge.get('from')}->{edge.get('to')} 가 없는 node를 가리킨다")

    image = data.get("image") or {}
    if image:
        for text in image.get("api_sizes") or []:
            if not SIZE_RE.match(str(text)):
                problems.append(f"image.api_sizes 표기 오류 {text!r}")
        for role, cfg in (image.get("roles") or {}).items():
            mode = cfg.get("deliver_at", "frame")
            if mode not in DELIVERY_MODES:
                problems.append(f"image.roles.{role}.deliver_at 이 {mode!r}")
            targets = cfg.get("target_sizes") or {}
            for orientation, text in targets.items():
                if orientation not in {"landscape", "portrait", "square"}:
                    problems.append(
                        f"image.roles.{role}.target_sizes 방향 오류 {orientation!r}")
                    continue
                if not SIZE_RE.match(str(text)):
                    problems.append(
                        f"image.roles.{role}.target_sizes.{orientation} 표기 오류 {text!r}")
                    continue
                width, height = _parse_size(text)
                correct = ((orientation == "landscape" and width > height)
                           or (orientation == "portrait" and height > width)
                           or (orientation == "square" and width == height))
                if not correct:
                    problems.append(
                        f"image.roles.{role}.target_sizes.{orientation} 방향과 크기가 다르다")
            explicit = cfg.get("target_size")
            if explicit and not SIZE_RE.match(str(explicit)):
                problems.append(f"image.roles.{role}.target_size 표기 오류 {explicit!r}")

    audio = data.get("audio") or {}
    if audio:
        if audio.get("h3_native_audio") != "discard":
            problems.append("audio.h3_native_audio 는 'discard'여야 한다")
        if not str(audio.get("target_language", "")).strip():
            problems.append("audio.target_language 가 필요하다")
        if audio.get("dialogue_source") != "approved_script_only":
            problems.append("audio.dialogue_source 는 'approved_script_only'여야 한다")
        if audio.get("lip_sync") != "only_when_onscreen_speaker_is_explicit":
            problems.append(
                "audio.lip_sync 는 'only_when_onscreen_speaker_is_explicit'여야 한다")
    return problems


# -------------------------------------------------------------- scaffolding

TEMPLATE = {
    "contract_id": "CHANGE-ME",
    "attempt": "CHANGE-ME",
    "stages": {
        **STAGE_ROLES,
        "_why": "역할과 단계 이름을 여기서 잇는다. 다른 프로젝트가 다르게 번호를 매겨도 모듈은 안 고친다",
    },
    "text": {"model": "gpt-5.4", "_why": "추론에 쓰는 모델. 이미지 모델은 image.model 이다"},
    "note": "이 계약은 이 시도에만 적용된다. 도구는 이 파일을 읽어 프롬프트를 조립하며 금지 문구를 도구 안에 다시 적지 않는다.",
    "frame": {
        "width": 768, "height": 1344, "fps": 24,
        "why": "로컬 H3 세로 네이티브 생성 프레임. 판과 모션은 이 크기를 쓴다",
        "upscale": {"allowed": False, "why": "생성 단계에서는 확대하지 않는다"},
        "applies_to": [STAGE_ROLES["plate"], STAGE_ROLES["motion"]],
    },
    "delivery_frame": {
        "width": 768, "height": 1344, "fps": 24,
        "why": "기본 납품은 생성 프레임을 그대로 보존한다",
        "applies_to": [STAGE_ROLES["edit"]],
        "transform": {"allowed": False, "operation": "none",
                      "why": "기본 계약에는 숨은 크롭이나 확대가 없다"},
    },
    "motion": {
        "runtime": PROFILE_ID,
        "frame_source": "frame",
        "why": "H3 요청 크기와 fps는 frame에서 읽고 런타임 프로파일로 검증한다",
    },
    "audio": {
        "h3_native_audio": "discard",
        "target_language": "ko",
        "dialogue_source": "approved_script_only",
        "lip_sync": "only_when_onscreen_speaker_is_explicit",
        "why": "H3 생성 음성은 언어·대사·입 모양이 승인본과 일치하지 않으므로 영상 조건화 결과로만 취급한다",
    },
    "duration_seconds": 60,
    "runtime_contract": {
        "mode": "fixed", "target_seconds": 60,
        "why": "총 편집 길이는 1단계가 정한다. 3단계 비트나 4단계 샷 공식이 정하지 않는다",
    },
    "image": {
        "model": "gpt-image-2",
        "quality": "high",
        "api_sizes": [
            "1024x1024", "1024x1536", "1536x1024",
            "2048x1152", "1152x2048", "3840x2160", "2160x3840",
        ],
        "roles": {
            "plate": {
                "deliver_at": "frame",
                "max_edge": 1536,
                "max_oversample": 2.0,
                "quality": "high",
                "draft_quality": "low",
                "why": "판은 영상의 첫·끝 프레임이므로 4K가 아니라 영상 네이티브 프레임과 가장 가까운 공급자 크기로 요청한 뒤 frame에 맞춘다",
            },
            "sheet": {
                "deliver_at": "max",
                "orientation": "portrait",
                "target_sizes": {
                    "landscape": "1672x941",
                    "portrait": "941x1672"
                },
                "max_edge": 2048,
                "quality": "high",
                "draft_quality": "high",
                "why": "시트는 화면에 나가지 않는 조건화 입력이다. Codex 앱·CLI에서 관측된 네이티브 래스터와 high 품질을 계약한다",
            },
        },
    },
    "sheet": {
        "why": "시트는 정의를 그림으로 굳힌 것이다. 정의 바로 다음에 만들고, 뒤의 모든 이미지가 이것을 물린다",
        "kinds": {
            "character": {
                "panels": ["전신 정면. 머리는 마네킹 처리",
                           "전신 후면. 머리 포함",
                           "얼굴과 어깨 클로즈업. 정면"],
                "why": "얼굴을 두 번 이상 넣으면 모델이 두 사람으로 읽는다",
            },
            "subject": {
                "panels": ["정면 3/4, 낮은 카메라",
                           "후면 3/4, 낮은 카메라",
                           "특징이 가장 잘 드러나는 세부"],
                "why": "형태를 둘러보는 세 각도",
            },
            "setting": {
                "panels": ["장소 전경. 넓은 시야",
                           "중간 거리. 인물이 설 자리가 보이게",
                           "바닥과 벽의 재질, 빛이 떨어지는 방식"],
                "why": "장소는 둘러볼 실루엣이 없다. 거리를 바꿔가며 기하와 빛을 고정한다",
            },
        },
    },
    "charter": ["금지 문구는 이 계약에서만 온다. 도구 안에 다시 적지 않는다"],
    "clauses": [
        {"id": "no-text", "ko": "생성 화면에 읽히는 문자 금지",
         "en": "No readable words, letters or numerals anywhere in the frame.",
         "applies_to": [STAGE_ROLES["plate"], STAGE_ROLES["motion"]]},
        {"id": "people", "ko": "인물 수는 컷이 정한다",
         "when": "has_host",
         "en_true": "Exactly one person is in frame. No other people anywhere in the frame.",
         "en_false": "No people are visible anywhere in the frame.",
         "applies_to": [STAGE_ROLES["plate"], STAGE_ROLES["motion"]]},
    ],
}


def scaffold(target: Path, contract_id: str, attempt: str) -> Path:
    data = json.loads(json.dumps(TEMPLATE))
    data["contract_id"] = contract_id
    data["attempt"] = attempt
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def load(target: Path) -> Contract:
    return Contract.load(target)


def main() -> int:
    parser = argparse.ArgumentParser(description="시도의 계약을 읽고 단계별 조항과 이미지 계획을 보여준다")
    sub = parser.add_subparsers(dest="command", required=True)

    show = sub.add_parser("show")
    show.add_argument("attempt", type=Path)
    show.add_argument("--stage")
    show.add_argument("--role")
    show.add_argument("--flag", action="append", default=[],
                      help="조건 플래그. has_host=true 형태")

    init = sub.add_parser("init", help="새 시도의 계약 뼈대를 쓴다")
    init.add_argument("target", type=Path, help="쓸 파일 경로")
    init.add_argument("--id", required=True)
    init.add_argument("--attempt", required=True)

    args = parser.parse_args()

    if args.command == "init":
        path = scaffold(args.target, args.id, args.attempt)
        print(f"작성: {path}")
        return 0

    contract = load(args.attempt)
    conditions = {}
    for item in args.flag:
        key, _, value = item.partition("=")
        conditions[key] = value.lower() not in {"false", "0", "no", ""}

    report: dict[str, Any] = {
        "contract_id": contract.data["contract_id"],
        "attempt": contract.data["attempt"],
        "path": contract.rel_path,
        "sha256": contract.digest,
        "frame": contract.frame.as_dict(),
        "delivery_frame": contract.delivery_frame.as_dict(),
        "delivery_transform": contract.delivery_transform,
        "upscale_allowed": contract.upscale_allowed,
        "frame_binds": contract.data["frame"].get("applies_to"),
        "delivery_frame_binds": contract.data["delivery_frame"].get("applies_to"),
        "bound_stages": contract.bound_stages,
        "condition_flags": contract.condition_flags,
    }
    if contract.image:
        report["image"] = {role: contract.image_plan(role).as_dict()
                           for role in (contract.image.get("roles") or {})}
    if args.role:
        report["image_plan"] = contract.image_plan(args.role).as_dict()
    if args.stage:
        report["stage"] = args.stage
        report["clauses_applied"] = contract.clause_ids(args.stage, conditions)
        report["clause_text"] = contract.clause_text(args.stage, conditions)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
