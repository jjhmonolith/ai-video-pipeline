"""MiniMax H3 runtime adapter.

Drives the local ComfyUI H3 stack over its HTTP API. Wiring mirrors the
official `video_minimax_h3_t2v` / `_i2v` templates: cfg-free BasicGuider,
res_multistep sampler, simple scheduler, and a dual VAE decode that splits
the AV latent into video frames and a soundtrack.

Stdlib only, so the package keeps its zero-dependency contract.
"""

from __future__ import annotations

import json
import mimetypes
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_SERVER = "http://127.0.0.1:18188"

# The AV latent is built on a 17k+5 frame grid at 24 fps.
FRAME_GRID_STRIDE = 17
FRAME_GRID_OFFSET = 5
NATIVE_FPS = 24
NATIVE_LANDSCAPE = (1344, 768)
NATIVE_PORTRAIT = (768, 1344)
NATIVE_FRAME_SIZES = (NATIVE_LANDSCAPE, NATIVE_PORTRAIT)
PROFILE_ID = "minimax-h3-local-768p"


class H3RuntimeError(RuntimeError):
    """Raised when the ComfyUI backend rejects or fails a generation."""


@dataclass(frozen=True)
class H3Settings:
    """Model assets and sampling defaults for the local H3 deployment."""

    unet: str = "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
    clip: str = "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
    video_vae: str = "minimax_h3_video_vae_fp16.safetensors"
    audio_vae: str = "minimax_h3_audio_vae_fp32.safetensors"
    turbo_lora: Optional[str] = "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors"
    turbo_strength: float = 1.0
    steps: int = 6
    base_steps: int = 20
    sampler: str = "res_multistep"
    scheduler: str = "simple"
    fps: int = NATIVE_FPS

    def without_turbo(self) -> "H3Settings":
        return replace(self, turbo_lora=None, steps=self.base_steps)


@dataclass(frozen=True)
class H3Request:
    """One generation request. Frames are ComfyUI input names, not local paths.

    `guides` is the answer to the most expensive thing the first two runs
    learned: first/last frame conditioning pins the ends and leaves the path
    between them free. A 15s locked-off wide came back with its middle 90%
    replaced by a hand close-up nobody asked for, twice, with `The camera never
    moves` in the prompt both times.

    Each entry is `(frame_idx, image_name)` and becomes one `MiniMaxH3AddGuide`
    in a chain, anchoring that frame the way `first_frame` anchors frame 0.
    Negative indices count from the end.

    `references` switches the graph to `MiniMaxH3ReferenceToVideo`, which takes
    up to nine reference images and, per the node's own tooltip, carries their
    tokens through every sampling step. That is what a character sheet is for.
    A run that built sheets and then described the subject in words instead came
    back with a different-looking host in five of eleven cuts.

    References combine with the frame anchors rather than replacing them. The
    reference node has no first/last frame inputs of its own, so on that route
    `first_frame` and `last_frame` are folded into the guide chain at frames 0
    and -1. Identity comes from the references, geometry from the anchors.
    """

    prompt: str
    width: int = NATIVE_LANDSCAPE[0]
    height: int = NATIVE_LANDSCAPE[1]
    seconds: float = 5.0
    seed: int = 0
    first_frame: Optional[str] = None
    last_frame: Optional[str] = None
    guides: Tuple[Tuple[int, str], ...] = ()
    references: Tuple[str, ...] = ()
    reference_size: str = "match"
    filename_prefix: str = "video/ai-video-pipeline"


def snap_length(seconds: float, fps: int = NATIVE_FPS) -> int:
    """Snap a duration up to the model's valid frame count (5, 22, 39, ...)."""
    frames = max(FRAME_GRID_OFFSET, round(seconds * fps))
    remainder = (frames - FRAME_GRID_OFFSET) % FRAME_GRID_STRIDE
    return frames if remainder == 0 else frames + (FRAME_GRID_STRIDE - remainder)


def build_workflow(request: H3Request, settings: H3Settings = H3Settings()) -> Dict[str, Any]:
    """Build a ComfyUI API-format prompt graph for one H3 generation."""
    if not request.prompt.strip():
        raise H3RuntimeError("prompt is empty")
    for axis, value in (("width", request.width), ("height", request.height)):
        if value % 32 or value < 32:
            raise H3RuntimeError(f"{axis} must be a multiple of 32")
    if (request.width, request.height) not in NATIVE_FRAME_SIZES:
        allowed = ", ".join(f"{w}x{h}" for w, h in NATIVE_FRAME_SIZES)
        raise H3RuntimeError(
            f"{PROFILE_ID} supports only {allowed}; got {request.width}x{request.height}")
    if settings.fps != NATIVE_FPS:
        raise H3RuntimeError(
            f"{PROFILE_ID} runs at {NATIVE_FPS} fps; got {settings.fps} fps")

    # References and frame anchors answer different questions and belong
    # together. `MiniMaxH3ReferenceToVideo` says what the subject looks like;
    # `MiniMaxH3AddGuide` says where things are at a given frame. The reference
    # node emits conditioning and a latent, and AddGuide takes exactly those, so
    # the two chain. Sending references alone leaves composition unanchored,
    # which is what three failed attempts looked like: the right kind of scene
    # with the wrong car in it and the presenter missing.
    if len(request.references) > 9:
        raise H3RuntimeError(f"레퍼런스는 최대 9장이다. {len(request.references)}장 주어짐")
    if request.reference_size not in {"match", "max"}:
        raise H3RuntimeError("reference_size 는 match 또는 max")

    length = snap_length(request.seconds, settings.fps)
    model_ref = ["turbo_lora", 0] if settings.turbo_lora else ["unet", 0]

    graph: Dict[str, Any] = {
        "unet": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": settings.unet, "weight_dtype": "default"},
        },
        "clip": {
            "class_type": "CLIPLoader",
            "inputs": {"clip_name": settings.clip, "type": "minimax", "device": "default"},
        },
        "video_vae": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": settings.video_vae},
        },
        "audio_vae": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": settings.audio_vae},
        },
        "conditioning": {
            "class_type": "MiniMaxH3ImageToVideo",
            "inputs": {
                "clip": ["clip", 0],
                "vae": ["video_vae", 0],
                "prompt": request.prompt,
                "width": request.width,
                "height": request.height,
                "length": length,
            },
        },
        "noise": {
            "class_type": "RandomNoise",
            "inputs": {"noise_seed": request.seed},
        },
        "sampler_select": {
            "class_type": "KSamplerSelect",
            "inputs": {"sampler_name": settings.sampler},
        },
        "sigmas": {
            "class_type": "BasicScheduler",
            "inputs": {
                "model": model_ref,
                "scheduler": settings.scheduler,
                "steps": settings.steps,
                "denoise": 1.0,
            },
        },
        "guider": {
            "class_type": "BasicGuider",
            "inputs": {"model": model_ref, "conditioning": ["conditioning", 0]},
        },
        "sample": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["noise", 0],
                "guider": ["guider", 0],
                "sampler": ["sampler_select", 0],
                "sigmas": ["sigmas", 0],
                "latent_image": ["conditioning", 1],
            },
        },
        "decode_video": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["sample", 0], "vae": ["video_vae", 0]},
        },
        "decode_audio": {
            "class_type": "VAEDecodeAudio",
            "inputs": {"samples": ["sample", 0], "vae": ["audio_vae", 0]},
        },
        "mux": {
            "class_type": "CreateVideo",
            "inputs": {
                "images": ["decode_video", 0],
                "audio": ["decode_audio", 0],
                "fps": float(settings.fps),
                "bit_depth": 8,
            },
        },
        "save": {
            "class_type": "SaveVideo",
            "inputs": {
                "video": ["mux", 0],
                "filename_prefix": request.filename_prefix,
                "format": "auto",
                "codec": "auto",
            },
        },
    }

    if request.references:
        # Reference conditioning is a different node with its own inputs; the
        # audio VAE is required here where the image-to-video node does not ask
        # for it. Each reference becomes one autogrow slot, ref_image_1 upward.
        reference_inputs: Dict[str, Any] = {
            "clip": ["clip", 0],
            "vae": ["video_vae", 0],
            "audio_vae": ["audio_vae", 0],
            "prompt": request.prompt,
            "width": request.width,
            "height": request.height,
            "length": length,
            "ref_image_size": request.reference_size,
        }
        # `ref_images` is an autogrow input: the whole set arrives as one dict
        # keyed by the template prefix, not as separate top-level inputs.
        # The node presents them to the text encoder as <Picture i>, 1-based, in
        # this order, and its own description says to use the same tags when
        # prompting, so a prompt that names them will bind them.
        ref_images: Dict[str, Any] = {}
        for order, name in enumerate(request.references, start=1):
            loader = f"load_ref_{order}"
            graph[loader] = {"class_type": "LoadImage", "inputs": {"image": name}}
            ref_images[f"ref_image_{order}"] = [loader, 0]
        reference_inputs["ref_images"] = ref_images
        graph["conditioning"] = {
            "class_type": "MiniMaxH3ReferenceToVideo",
            "inputs": reference_inputs,
        }

    if settings.turbo_lora:
        graph["turbo_lora"] = {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": ["unet", 0],
                "lora_name": settings.turbo_lora,
                "strength_model": settings.turbo_strength,
            },
        }

    # The reference node has no first_frame/last_frame inputs, so on that route
    # the frame anchors become guides at the two ends instead.
    anchors: List[Tuple[int, str]] = list(request.guides)
    if request.references:
        if request.first_frame:
            anchors.insert(0, (0, request.first_frame))
        if request.last_frame:
            anchors.append((-1, request.last_frame))
    else:
        for slot, frame in (("first_frame", request.first_frame),
                            ("last_frame", request.last_frame)):
            if frame:
                loader = f"load_{slot}"
                graph[loader] = {"class_type": "LoadImage", "inputs": {"image": frame}}
                graph["conditioning"]["inputs"][slot] = [loader, 0]

    # Chain one MiniMaxH3AddGuide per anchored frame. The node returns
    # conditioning only, so the latent keeps coming from the I2V node.
    positive: List[Any] = ["conditioning", 0]
    for order, (frame_idx, image_name) in enumerate(anchors):
        if not -length <= frame_idx < length:
            raise H3RuntimeError(f"guide frame_idx {frame_idx} outside 0..{length - 1}")
        loader = f"load_guide_{order}"
        node = f"guide_{order}"
        graph[loader] = {"class_type": "LoadImage", "inputs": {"image": image_name}}
        graph[node] = {
            "class_type": "MiniMaxH3AddGuide",
            "inputs": {
                "positive": positive,
                "latent": ["conditioning", 1],
                "frame_idx": int(frame_idx),
                "vae": ["video_vae", 0],
                "image": [loader, 0],
            },
        }
        positive = [node, 0]
    graph["guider"]["inputs"]["conditioning"] = positive

    return graph


class ComfyClient:
    """Minimal ComfyUI HTTP client: upload, submit, poll, download."""

    def __init__(self, server: str = DEFAULT_SERVER, timeout: float = 120.0) -> None:
        self.server = server.rstrip("/")
        self.timeout = timeout
        self.client_id = str(uuid.uuid4())

    def _request(self, path: str, data: Optional[bytes] = None, headers: Optional[Dict[str, str]] = None) -> bytes:
        req = urllib.request.Request(f"{self.server}{path}", data=data, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            raise H3RuntimeError(f"{path} -> HTTP {error.code}: {error.read().decode('utf-8', 'replace')[:400]}") from error
        except urllib.error.URLError as error:
            raise H3RuntimeError(f"{path} unreachable at {self.server}: {error.reason}") from error

    def system_stats(self) -> Dict[str, Any]:
        return json.loads(self._request("/system_stats"))

    def upload_image(self, path: Path | str) -> str:
        """Upload a local image into ComfyUI's input folder; returns its input name."""
        path = Path(path)
        payload = path.read_bytes()
        boundary = f"----ai-video-pipeline-{uuid.uuid4().hex}"
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        body = b"".join([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="image"; filename="{path.name}"\r\n'.encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(),
            payload,
            f"\r\n--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n',
            f"--{boundary}--\r\n".encode(),
        ])
        result = json.loads(self._request(
            "/upload/image", body, {"Content-Type": f"multipart/form-data; boundary={boundary}"}
        ))
        subfolder = result.get("subfolder") or ""
        name = result["name"]
        return f"{subfolder}/{name}" if subfolder else name

    def submit(self, workflow: Dict[str, Any]) -> str:
        payload = json.dumps({"prompt": workflow, "client_id": self.client_id}).encode("utf-8")
        result = json.loads(self._request("/prompt", payload, {"Content-Type": "application/json"}))
        if "prompt_id" not in result:
            raise H3RuntimeError(f"rejected: {json.dumps(result, ensure_ascii=False)[:600]}")
        return result["prompt_id"]

    def wait(self, prompt_id: str, poll_seconds: float = 3.0, timeout_seconds: float = 3600.0) -> Dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        transient = 0
        while time.monotonic() < deadline:
            try:
                history = json.loads(self._request(f"/history/{prompt_id}"))
            except H3RuntimeError:
                # A dropped tunnel or a busy server should not lose a running job.
                transient += 1
                if transient > 40:
                    raise
                time.sleep(poll_seconds)
                continue
            transient = 0
            entry = history.get(prompt_id)
            if entry:
                status = entry.get("status", {})
                if status.get("status_str") == "error" or status.get("completed") is False:
                    raise H3RuntimeError(f"generation failed: {json.dumps(status, ensure_ascii=False)[:800]}")
                if status.get("completed"):
                    return entry
            time.sleep(poll_seconds)
        raise H3RuntimeError(f"timed out after {timeout_seconds}s waiting for {prompt_id}")

    def download(self, entry: Dict[str, Any], destination: Path | str) -> List[Path]:
        """Download every file produced by a finished prompt."""
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True)
        saved: List[Path] = []
        for reference in _iter_output_files(entry):
            query = urllib.parse.urlencode({
                "filename": reference[0], "subfolder": reference[1], "type": reference[2],
            })
            target = destination / Path(reference[0]).name
            target.write_bytes(self._request(f"/view?{query}"))
            saved.append(target)
        return saved


def _iter_output_files(entry: Dict[str, Any]) -> List[Tuple[str, str, str]]:
    references: List[Tuple[str, str, str]] = []
    for node_output in entry.get("outputs", {}).values():
        for items in node_output.values():
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict) and item.get("filename"):
                    references.append((item["filename"], item.get("subfolder", ""), item.get("type", "output")))
    return references


def generate(
    request: H3Request,
    destination: Path | str,
    settings: H3Settings = H3Settings(),
    server: str = DEFAULT_SERVER,
    timeout_seconds: float = 3600.0,
) -> Dict[str, Any]:
    """Run one H3 generation end to end and pull the artifacts down locally."""
    client = ComfyClient(server)
    workflow = build_workflow(request, settings)
    started = time.monotonic()
    prompt_id = client.submit(workflow)
    entry = client.wait(prompt_id, timeout_seconds=timeout_seconds)
    files = client.download(entry, destination)
    return {
        "prompt_id": prompt_id,
        "length_frames": snap_length(request.seconds, settings.fps),
        "steps": settings.steps,
        "turbo_lora": settings.turbo_lora,
        "elapsed_seconds": round(time.monotonic() - started, 1),
        "files": [str(path) for path in files],
    }
