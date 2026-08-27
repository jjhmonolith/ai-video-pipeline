"""A clickable graph of a run, so a broken pipeline shows itself.

`pipeline_map` already reads the tools' AST and knows what each script really
touches. What it renders is two tables, and a table cannot answer the question
that actually gets asked while repairing a run: if I change this stage, what has
to be made again?

So the same facts are laid out as a graph. Nodes are stages, edges are the
artifacts that pass between them, and selecting a node walks the edges forward
to mark everything downstream of it. The right drawer carries what a person
needs in order to judge the stage: the prompt that was sent, the reference
images that went in with it, and the file that came out, side by side.

Two levels, because the failures live at both. A historical run generated
subject sheets and never fed them to plate generation. That defect was hidden
when both artifacts lived in one stage; at artifact level the sheets are a node
with no outgoing edge. The view toggle is there for that class of defect.

Nothing here is a claim. Edges drawn solid come from the tools' AST. Edges drawn
dashed come from the `## input` section of a stage's NOTES.md, which is prose
written afterwards and has been wrong before. Where the two disagree, the
disagreement is the finding.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .pipeline_map import analyse_tool
from .prompt_docs import PROMPT_KEYS, _find_prompt_lists, _label
from .run_layout import LEGACY_STAGES, STAGE_DIR_RE as STAGE_RE, STAGE_TITLES
BACKTICK_RE = re.compile(r"`([^`]+)`")

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
VIDEO_EXT = {".mp4", ".mov", ".webm", ".m4v"}
TEXT_EXT = {".json", ".md", ".txt", ".csv"}
TEXT_CAP = 14000
FILE_CAP = 400

SUBDIR_ORDER = ["output", "prompts", "qa", "rejected"]


# ---------------------------------------------------------------- filesystem


def _kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in IMAGE_EXT:
        return "image"
    if suffix in VIDEO_EXT:
        return "video"
    if suffix in TEXT_EXT:
        return "text"
    return "file"


def _visible(path: Path) -> bool:
    return not any(part.startswith(".") for part in path.parts)


def _describe(path: Path, root: Path) -> dict:
    entry = {
        "name": path.name,
        "rel": path.relative_to(root).as_posix(),
        "kind": _kind(path),
        "bytes": path.stat().st_size,
    }
    if entry["kind"] == "text":
        raw = path.read_text(encoding="utf-8", errors="replace")
        entry["text"] = raw[:TEXT_CAP]
        entry["truncated"] = len(raw) > TEXT_CAP
    return entry


def _list_files(directory: Path, root: Path) -> list[dict]:
    if not directory.exists():
        return []
    found = sorted(p for p in directory.rglob("*") if p.is_file() and _visible(p.relative_to(directory)))
    return [_describe(p, root) for p in found[:FILE_CAP]]


def _read(path: Path) -> str | None:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else None


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _shared_digests(topic_dir: Path) -> dict[str, str]:
    """Hash of every topic-level fact file, keyed by digest.

    Historical attempts copied these into a stage output to record what they
    were built against. The copy is only worth anything if something reads it;
    a byte-identical copy that nothing reads is a promise the run does not keep.
    """
    shared = topic_dir / "topic"
    if not shared.exists():
        return {}
    return {
        _digest(p): p.relative_to(topic_dir).as_posix()
        for p in sorted(shared.rglob("*"))
        if p.is_file() and _visible(p.relative_to(shared)) and p.stat().st_size < 4_000_000
    }


# ------------------------------------------------------------------ prompts


def _prompt_text(entry: dict) -> tuple[str, str]:
    for key in PROMPT_KEYS:
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return key, value
    return "", ""


def _entry_meta(entry: dict, label: str) -> list[list[str]]:
    rows = []
    for key, value in entry.items():
        if key in PROMPT_KEYS:
            continue
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        if str(value) == label:  # the id is already the card's heading
            continue
        rows.append([key, str(value)])
    return rows


def _scan_prompts(stage_dir: Path, root: Path) -> list[dict]:
    prompts_dir = stage_dir / "prompts"
    if not prompts_dir.exists():
        return []

    packs = []
    for pack_path in sorted(prompts_dir.glob("*.json")):
        try:
            data = json.loads(pack_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        meta = ([[k, str(v)] for k, v in data.items() if not isinstance(v, (dict, list))]
                if isinstance(data, dict) else [])

        groups = []
        for group_name, entries in _find_prompt_lists(data):
            items = []
            for index, entry in enumerate(entries):
                key, text = _prompt_text(entry)
                refs = entry.get("references") or entry.get("refs") or []
                label = _label(entry, index)
                items.append({
                    "label": label,
                    "prompt_key": key,
                    "prompt": text,
                    "meta": _entry_meta(entry, label),
                    "refs": [str(r) for r in refs] if isinstance(refs, list) else [],
                })
            groups.append({"name": group_name, "entries": items})

        packs.append({
            "file": pack_path.name,
            "rel": pack_path.relative_to(root).as_posix(),
            "meta": meta,
            "groups": groups,
        })
    return packs


def _build_stem_index(attempt_dir: Path, root: Path) -> dict[str, list[dict]]:
    """Every media file in the attempt, keyed by filename stem.

    Prompt entries carry an id (`C02`, `SHEET-HOST`) and the runners name their
    output after it, sometimes with a suffix (`C02_seed24.mp4`). Matching on the
    stem is how a prompt gets shown next to the thing it made.
    """
    index: dict[str, list[dict]] = {}
    for path in sorted(attempt_dir.rglob("*")):
        if not path.is_file() or not _visible(path.relative_to(attempt_dir)):
            continue
        if _kind(path) not in {"image", "video"}:
            continue
        index.setdefault(path.stem, []).append(_describe(path, root))
    return index


def _match_files(label: str, index: dict[str, list[dict]], stage_id: str) -> tuple[list[dict], list[dict]]:
    """What this prompt made here, and what became of it later.

    A shot id survives the whole run: `C01` can be a plate in `05-plate`, a clip
    in `06-motion` and a cut in `07-edit`. The drawer shows the stage's own
    result without burying it, while still showing what changes downstream.
    """
    hits: list[dict] = []
    for stem, files in index.items():
        if stem == label or stem.startswith(label + "_") or stem.startswith(label + "-"):
            hits.extend(files)
    hits.sort(key=lambda f: ("/output/" not in f["rel"], f["rel"]))
    here = [f for f in hits if f["rel"].split("/")[2:3] == [stage_id]]
    later = [f for f in hits if f not in here]
    return here, later


# -------------------------------------------------------------------- graph


def _stage_of(artifact: str) -> str | None:
    head = artifact.split("/")[0]
    return head if STAGE_RE.match(head) else None


def _tool_home(tool: dict) -> str | None:
    """Which stage a tool belongs to: the one it writes into."""
    stages = [_stage_of(t) for t in tool["writes"] + tool["both"]]
    counts = Counter(s for s in stages if s)
    if not counts:
        stages = [_stage_of(t) for t in tool["reads"] + tool["mentions"]]
        counts = Counter(s for s in stages if s)
    if not counts:
        return None
    top = max(counts.values())
    return max(s for s, n in counts.items() if n == top)


def _declared_inputs(notes: str | None) -> list[str]:
    """Paths the stage's own prose claims it read. Treated as a claim, not a fact."""
    if not notes:
        return []
    claimed: list[str] = []
    in_section = False
    for line in notes.splitlines():
        if line.startswith("#"):
            in_section = "input" in line.lower() or "입력" in line
            continue
        if in_section:
            claimed.extend(BACKTICK_RE.findall(line))
    out, seen = [], set()
    for path in claimed:
        path = path.strip().strip("/")
        if path and path not in seen:
            seen.add(path)
            out.append(path)
    return out


def _artifact_class(path: str) -> str:
    """Assets are the pipeline. Prompts and receipts are the record of it.

    Both come out of the same AST walk, and lumping them together buries the
    finding: a prompt pack is written and never read by another script because
    the thing that reads it is an image API, not Python. Only assets are judged
    on whether anything downstream picks them up.
    """
    parts = path.split("/")
    if "prompts" in parts:
        return "prompt"
    if "qa" in parts or parts[-1] in {"receipt.json"} or parts[-1].endswith("-receipt.json"):
        return "record"
    return "asset"


def _artifact_state(art: dict) -> str:
    """Three separate facts, not one verdict.

    `unread` is the failure that has actually happened here: v1 generated
    subject sheets and no script ever opened the directory. `stage-local` is
    weaker and often fine, because a runner legitimately prepares frames for
    itself. The drawer shows the files either way and a person decides.
    """
    if art["klass"] != "asset":
        return "record"
    if not art["consumers"]:
        return "unread"
    if not art["cross_consumers"]:
        return "self-only"
    if not art["downstream_consumers"]:
        return "stage-local"
    return "ok"


def scan_attempt(attempt_dir: Path, root: Path, shared: dict[str, str] | None = None) -> dict:
    tools_dir = attempt_dir / "tools"
    tools = [analyse_tool(p) for p in sorted(tools_dir.glob("*.py"))] if tools_dir.exists() else []
    for tool in tools:
        tool["home"] = _tool_home(tool)
        tool["rel"] = (tools_dir / tool["tool"]).relative_to(root).as_posix()

    artifacts: dict[str, dict] = {}

    def slot(path: str) -> dict:
        return artifacts.setdefault(path, {
            "path": path,
            "stage": _stage_of(path),
            "klass": _artifact_class(path),
            "producers": [],
            "consumers": [],
        })

    for tool in tools:
        for target in tool["writes"] + tool["both"]:
            record = slot(target)
            if tool["tool"] not in record["producers"]:
                record["producers"].append(tool["tool"])
        for target in tool["reads"] + tool["both"] + tool["mentions"]:
            record = slot(target)
            if tool["tool"] not in record["consumers"]:
                record["consumers"].append(tool["tool"])

    # A bare stage name is the stage directory, not an artifact. It arrives
    # here because tools may hold a bare stage directory in a constant; keeping
    # it would duplicate the stage node on the graph.
    for path in [p for p in artifacts if "/" not in p]:
        del artifacts[path]

    tool_home = {t["tool"]: t["home"] for t in tools}

    # A tool that writes into a loop variable resolves as a mention, not a
    # write, so the directory it fills looks parentless. When exactly one tool
    # in the owning stage touches such an asset, it made it. Marked inferred,
    # because it is read off the shape of the code rather than off a call.
    for record in artifacts.values():
        if record["klass"] != "asset" or record["producers"]:
            continue
        local = [n for n in record["consumers"] if tool_home.get(n) == record["stage"]]
        if len(local) == 1:
            record["producers"] = local
            record["producer_inferred"] = True

    for path, record in artifacts.items():
        record.setdefault("producer_inferred", False)
        stage = record["stage"]
        # The tool that made it, plus any sibling tool living in the same stage.
        # An artifact only counts as wired in when something outside its own
        # stage reaches for it.
        owners = set(record["producers"]) | {
            name for name in record["consumers"] if tool_home.get(name) == stage
        }
        record["owners"] = sorted(owners)
        record["cross_consumers"] = [n for n in record["consumers"] if n not in record["producers"]]
        record["downstream_consumers"] = [n for n in record["consumers"] if n not in owners]

        on_disk = attempt_dir / path
        if on_disk.is_dir():
            record["files"] = _list_files(on_disk, root)
        elif on_disk.is_file():
            record["files"] = [_describe(on_disk, root)]
        else:
            record["files"] = []
        record["external"] = stage is None
        record["state"] = _artifact_state(record)

    # Stage directories are numbered, so name order is pipeline order. Sorting
    # the directories that exist keeps both the current layout and the
    # pre-split one in the right sequence without a lookup table.
    stage_ids = sorted(p.name for p in attempt_dir.iterdir()
                       if p.is_dir() and STAGE_RE.match(p.name))

    stem_index = _build_stem_index(attempt_dir, root)

    stages = []
    for stage_id in stage_ids:
        stage_dir = attempt_dir / stage_id
        notes = _read(stage_dir / "NOTES.md")
        packs = _scan_prompts(stage_dir, root)

        for pack in packs:
            for group in pack["groups"]:
                for entry in group["entries"]:
                    here, later = _match_files(entry["label"], stem_index, stage_id)
                    entry["results"] = here
                    entry["downstream"] = later
                    entry["ref_files"] = [
                        f for ref in entry["refs"]
                        for f in (_match_files(ref, stem_index, stage_id)[0]
                                  or _match_files(ref, stem_index, stage_id)[1])[:1]
                    ]

        buckets = {name: _list_files(stage_dir / name, root) for name in SUBDIR_ORDER}
        for entry in buckets["output"]:
            origin = (shared or {}).get(_digest(root / entry["rel"]))
            if origin:
                entry["copy_of"] = origin

        receipt = stage_dir / "receipt.json"
        prompt_count = sum(len(g["entries"]) for p in packs for g in p["groups"])
        owned = [a for a in artifacts.values() if a["stage"] == stage_id]

        stages.append({
            "id": stage_id,
            "title": STAGE_TITLES.get(stage_id, ""),
            "legacy": stage_id in LEGACY_STAGES,
            "notes": notes,
            "declared_inputs": _declared_inputs(notes),
            "packs": packs,
            "files": buckets,
            "receipt": _describe(receipt, root) if receipt.exists() else None,
            "tools": [t["tool"] for t in tools if t["home"] == stage_id],
            "counts": {
                "prompts": prompt_count,
                "output": len(buckets["output"]),
                "rejected": len(buckets["rejected"]),
                "qa": len(buckets["qa"]),
            },
            "artifacts": sorted(a["path"] for a in owned),
            "flags": sorted({a["state"] for a in owned} - {"ok", "record", "stage-local"}),
            "state": ("wired" if any(t["home"] == stage_id for t in tools)
                      else "authored" if buckets["output"]
                      else "empty"),
        })

    # ---- edges
    edge_map: dict[tuple[str, str], dict] = {}

    def link(src: str, dst: str, artifact: str, origin: str) -> None:
        if src == dst or not src or not dst:
            return
        edge = edge_map.setdefault((src, dst), {"from": src, "to": dst, "artifacts": [], "origin": set()})
        if artifact not in edge["artifacts"]:
            edge["artifacts"].append(artifact)
        edge["origin"].add(origin)

    for path, record in artifacts.items():
        source = record["stage"] or "topic"
        for consumer in record["downstream_consumers"]:
            link(source, tool_home.get(consumer) or "", path, "code")

    stage_set = set(stage_ids)
    for stage in stages:
        for claim in stage["declared_inputs"]:
            source = _stage_of(claim) or ("topic" if claim.startswith("topic/") else None)
            if source and (source in stage_set or source == "topic"):
                link(source, stage["id"], claim, "docs")

    edges = []
    for edge in edge_map.values():
        origin = edge["origin"]
        edges.append({
            "from": edge["from"],
            "to": edge["to"],
            "artifacts": edge["artifacts"],
            "origin": "both" if len(origin) > 1 else next(iter(origin)),
        })
    edges.sort(key=lambda e: (e["from"], e["to"]))

    # A stage that produced files and hands none of them on is a dead branch.
    # The last stage is exempt, since a run has to end somewhere. Historical
    # research snapshots motivated this check: downstream consumers sometimes
    # read a live shared file instead, leaving the snapshot unconnected.
    outgoing = {e["from"] for e in edges}
    for position, stage in enumerate(stages):
        stage["dead_branch"] = bool(
            stage["counts"]["output"]
            and stage["id"] not in outgoing
            and position < len(stages) - 1
        )
        stage["copies"] = [f["rel"] for f in stage["files"]["output"] if f.get("copy_of")]
        if stage["dead_branch"]:
            stage["flags"] = sorted(set(stage["flags"]) | {"dead-branch"})

    # ---- artifact-level graph
    art_nodes, art_edges = [], []
    for path in sorted(artifacts):
        record = artifacts[path]
        art_nodes.append({
            "id": path,
            "stage": record["stage"] or "topic",
            "label": path.split("/")[-1] or path,
            "sub": path,
            "klass": record["klass"],
            "state": record["state"],
            "producers": record["producers"],
            "producer_inferred": record["producer_inferred"],
            "consumers": record["consumers"],
            "downstream": record["downstream_consumers"],
            "files": record["files"],
        })
    produced_by_tool: dict[str, list[str]] = {}
    for path, record in artifacts.items():
        for producer in record["producers"]:
            produced_by_tool.setdefault(producer, []).append(path)
    for path, record in artifacts.items():
        for consumer in record["cross_consumers"]:
            for target in produced_by_tool.get(consumer, []):
                if target != path:
                    art_edges.append({"from": path, "to": target,
                                      "artifacts": [consumer], "origin": "code"})

    attempt_doc = _read(attempt_dir / "ATTEMPT.md")
    version = attempt_dir / "VERSION.json"

    return {
        "id": attempt_dir.name,
        "rel": attempt_dir.relative_to(root).as_posix(),
        "doc": attempt_doc,
        "version": json.loads(version.read_text(encoding="utf-8")) if version.exists() else None,
        "tools": tools,
        "stages": stages,
        "edges": edges,
        "artifacts": art_nodes,
        "artifact_edges": art_edges,
    }


def scan_topic(topic_dir: Path) -> dict:
    holder = topic_dir / "attempts"
    attempts = sorted(p for p in holder.iterdir() if p.is_dir()) if holder.exists() else []
    shared_dir = topic_dir / "topic"
    digests = _shared_digests(topic_dir)
    return {
        "topic": topic_dir.name,
        "doc": _read(topic_dir / "TOPIC.md"),
        "plan": _read(topic_dir / "VERSION-PLAN.md"),
        "shared": _list_files(shared_dir, topic_dir) if shared_dir.exists() else [],
        "attempts": [scan_attempt(a, topic_dir, digests) for a in attempts],
    }


# ------------------------------------------------------------------- render

PAGE = r"""<meta charset="utf-8">
<title>__TITLE__ · 파이프라인 대시보드</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{
  --bg:#0e0f11; --panel:#141619; --panel2:#181b1f; --line:#24272c; --line2:#2f3339;
  --ink:#e9e5dd; --dim:#8d8579; --dim2:#6b665e;
  --gold:#d6b260; --green:#7fa87a; --red:#e0806f; --blue:#7d9dc4; --violet:#a893c9;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:14px/1.6 -apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Segoe UI',sans-serif;
  overflow:hidden;height:100vh}
button{font:inherit;color:inherit;background:none;border:none;cursor:pointer}

/* ---- top bar */
header{display:flex;align-items:center;gap:14px;flex-wrap:wrap;
  padding:12px 20px;border-bottom:1px solid var(--line);background:var(--panel)}
header h1{font-size:15px;margin:0;font-weight:600;letter-spacing:.01em}
header .why{color:var(--dim2);font-size:12px}
.seg{display:flex;border:1px solid var(--line2);border-radius:7px;overflow:hidden}
.seg button{padding:5px 12px;font-size:12.5px;color:var(--dim)}
.seg button.on{background:#22262b;color:var(--ink)}
select{background:var(--panel2);color:var(--ink);border:1px solid var(--line2);
  border-radius:7px;padding:5px 10px;font-size:12.5px}
.spacer{flex:1}
.stat{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--dim);
  border:1px solid var(--line);border-radius:20px;padding:3px 11px;cursor:pointer}
.stat b{font-variant-numeric:tabular-nums;color:var(--ink);font-weight:600}
.stat.bad b{color:var(--red)} .stat.warn b{color:var(--gold)} .stat.on{border-color:var(--line2);background:#1c2025}

/* ---- layout */
main{display:flex;height:calc(100vh - 53px)}
#canvas-wrap{flex:1;overflow:auto;position:relative;padding:0 0 80px}
#canvas{position:relative}
#wires{position:absolute;inset:0;pointer-events:none;overflow:visible}
#wires path{pointer-events:stroke;cursor:pointer}

/* ---- nodes */
.node{position:absolute;background:var(--panel);border:1px solid var(--line2);overflow:hidden;
  border-radius:10px;padding:11px 13px;cursor:pointer;transition:border-color .12s,opacity .12s,background .12s}
.node:hover{border-color:#4a5058;background:var(--panel2)}
.node.sel{border-color:var(--gold);background:#1e1d1a;box-shadow:0 0 0 1px var(--gold)}
.node.up{border-color:#3f5064}
.node.down{border-color:#5c4c2c;background:#1a1815}
.node.faded{opacity:.26}
.node .top{display:flex;align-items:center;gap:8px}
.nid{font-size:12.5px;letter-spacing:.05em;color:var(--gold);font-weight:600}
.node.artifact .nid{color:var(--ink);letter-spacing:0;font-weight:600}
.ntitle{color:var(--dim);font-size:12px;margin-top:2px;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.nmeta{display:flex;gap:10px;margin-top:7px;font-size:11px;color:var(--dim2);
  font-variant-numeric:tabular-nums;flex-wrap:wrap}
.nmeta span{max-width:100%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.nmeta i{font-style:normal;color:#b9b1a3}
.node.artifact .nmeta{display:block}
.node.artifact .nmeta span{display:block;margin-top:2px}
.pill{font-size:10.5px;padding:1px 7px;border-radius:20px;border:1px solid var(--line2);color:var(--dim)}
.pill.wired{color:var(--green);border-color:#2f4030}
.pill.authored{color:var(--blue);border-color:#31404f}
.pill.empty{color:var(--dim2)}
.pill.bad{color:var(--red);border-color:#4a2f2a}
.pill.warn{color:var(--gold);border-color:#4a3f26}
.pill.ok{color:var(--green);border-color:#2f4030}
.band{position:absolute;font-size:11px;color:var(--dim2);letter-spacing:.06em}
.elabel{position:absolute;font-size:10.5px;color:var(--dim2);background:var(--bg);
  padding:0 5px;border-radius:4px;cursor:pointer;white-space:nowrap;
  max-width:190px;overflow:hidden;text-overflow:ellipsis}
.elabel:hover{color:var(--ink)}
.elabel.hot{color:var(--gold)}

/* ---- drawer */
#drawer{width:46%;min-width:430px;max-width:760px;border-left:1px solid var(--line);
  background:var(--panel);display:flex;flex-direction:column}
#drawer.hidden{display:none}
.dhead{padding:14px 18px 0;border-bottom:1px solid var(--line)}
.dhead .row{display:flex;align-items:flex-start;gap:10px}
.dhead h2{margin:0;font-size:17px}
.dhead p{margin:3px 0 0;color:var(--dim);font-size:12.5px}
.close{color:var(--dim2);font-size:20px;line-height:1;padding:0 4px}
.tabs{display:flex;gap:2px;margin-top:12px}
.tabs button{padding:7px 12px;font-size:12.5px;color:var(--dim);border-bottom:2px solid transparent}
.tabs button.on{color:var(--ink);border-bottom-color:var(--gold)}
.tabs button:disabled{color:#43403b;cursor:default}
#dbody{flex:1;overflow:auto;padding:16px 18px 60px}

.impact{border:1px solid var(--line2);border-radius:9px;padding:11px 13px;margin:0 0 16px;
  background:var(--panel2)}
.impact h3{margin:0 0 7px;font-size:12px;color:var(--dim);font-weight:500;letter-spacing:.04em}
.chiprow{display:flex;flex-wrap:wrap;gap:6px}
.chip{font-size:11.5px;padding:3px 9px;border-radius:6px;border:1px solid var(--line2);
  color:var(--dim);cursor:pointer}
.chip:hover{color:var(--ink);border-color:#4a5058}
.chip.down{color:var(--gold);border-color:#4a3f26}
.chip.up{color:var(--blue);border-color:#31404f}
.none{color:var(--dim2);font-size:12px}

section.blk{margin:0 0 22px}
section.blk > h3{font-size:12px;color:var(--dim);font-weight:500;letter-spacing:.04em;
  margin:0 0 9px;padding-bottom:6px;border-bottom:1px solid var(--line)}

.card{border:1px solid var(--line);border-radius:9px;margin:0 0 12px;overflow:hidden}
.card > .ch{display:flex;align-items:center;gap:9px;padding:9px 12px;background:var(--panel2);
  cursor:pointer}
.card > .ch .k{font-weight:600;font-size:13px}
.card > .ch .s{color:var(--dim2);font-size:11.5px}
.card > .cb{padding:12px;border-top:1px solid var(--line)}
.card.closed > .cb{display:none}

.pair{display:grid;grid-template-columns:1fr;gap:12px}
@media (min-width:1500px){.pair{grid-template-columns:1.15fr .85fr}}
pre.prompt{margin:0;white-space:pre-wrap;word-break:break-word;font-size:12px;line-height:1.62;
  font-family:ui-monospace,SFMono-Regular,Menlo,monospace;color:#cfc8ba;
  background:#0c0d0f;border:1px solid var(--line);border-radius:7px;padding:11px;
  max-height:340px;overflow:auto}
table.kv{border-collapse:collapse;width:100%;font-size:11.5px;margin:9px 0 0}
table.kv td{padding:3px 8px 3px 0;border-bottom:1px solid #1e2024;vertical-align:top;color:#bdb6a9}
table.kv td:first-child{color:var(--dim2);white-space:nowrap;width:1%}
.subh{font-size:11px;color:var(--dim2);letter-spacing:.04em;margin:0 0 6px}

.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:9px}
.thumb{border:1px solid var(--line);border-radius:7px;overflow:hidden;background:#0c0d0f}
.thumb img,.thumb video{width:100%;display:block;aspect-ratio:9/16;object-fit:cover;background:#000}
.thumb.wide img,.thumb.wide video{aspect-ratio:16/9}
.thumb .cap{padding:5px 7px;font-size:10.5px;color:var(--dim);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.thumb a{color:inherit;text-decoration:none;display:block}
.filelist{font-size:12px}
.filelist a{display:flex;justify-content:space-between;gap:12px;padding:5px 0;
  border-bottom:1px solid #1e2024;color:#c4bdb0;text-decoration:none}
.filelist a:hover{color:var(--ink)}
.filelist .sz{color:var(--dim2);font-variant-numeric:tabular-nums;font-size:11px}
.md{font-size:13px;color:#cbc4b7}
.md h1,.md h2,.md h3{font-size:13px;color:var(--gold);margin:16px 0 5px;font-weight:600}
.md code{font-family:ui-monospace,Menlo,monospace;font-size:11.5px;color:#a8c0a0;
  background:#0c0d0f;padding:1px 4px;border-radius:4px}
.md table{border-collapse:collapse;font-size:12px;margin:8px 0}
.md td,.md th{border:1px solid var(--line);padding:4px 9px;text-align:left}
.md th{color:var(--dim)}
.md ul{padding-left:18px;margin:5px 0}
.md hr{border:none;border-top:1px solid var(--line);margin:14px 0}
/* ---- structured json */
.jwrap{margin:0 0 6px}
.seg.small{display:inline-flex;margin:0 0 9px;border-radius:6px}
.seg.small button{padding:3px 10px;font-size:11px}
table.jt{border-collapse:collapse;width:100%;font-size:12px;margin:0}
table.jt td,table.jt th{padding:4px 9px 4px 0;vertical-align:top;
  border-bottom:1px solid #1e2024;text-align:left}
table.jt td.jkey{color:var(--dim2);white-space:nowrap;width:1%;padding-right:14px}
table.jt.grid{width:auto;min-width:100%}
table.jt.grid td,table.jt.grid th{padding:5px 12px 5px 0;white-space:nowrap}
table.jt.grid th{color:var(--gold);font-weight:500;font-size:11px;
  letter-spacing:.03em;border-bottom:1px solid var(--line2)}
table.jt.grid tr:hover td{background:#17191d}
.jscroll{overflow-x:auto;margin:0 0 10px;padding-bottom:2px}
.jn{font-variant-numeric:tabular-nums;color:#c8b78a}
.jb{color:var(--violet)}
.jf{color:var(--green);font-family:ui-monospace,Menlo,monospace;font-size:11.5px}
.nil{color:#4d4f54}
.jchip{font-size:11.5px;padding:2px 8px;border-radius:5px;background:#181b1f;
  border:1px solid var(--line);color:#c4bdb0}
.jnest{border-left:2px solid var(--line2);padding-left:11px;margin:8px 0}
.jlong{white-space:pre-wrap;word-break:break-word;color:#cfc8ba;font-size:12px;line-height:1.6;
  background:#0c0d0f;border:1px solid var(--line);border-radius:6px;padding:9px;margin:3px 0}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:11px;color:var(--dim2);
  padding:8px 20px;border-top:1px solid var(--line);background:var(--panel)}
.legend span{display:flex;align-items:center;gap:5px}
.swatch{width:16px;height:0;border-top-width:2px;border-top-style:solid}
</style>

<header>
  <h1>__TITLE__</h1>
  <span class="why">코드의 AST에서 뽑은 실제 흐름</span>
  <select id="attempt"></select>
  <div class="seg" id="viewseg">
    <button data-view="stage" class="on">단계</button>
    <button data-view="artifact">산출물</button>
  </div>
  <div class="spacer"></div>
  <div id="stats"></div>
</header>

<main>
  <div id="canvas-wrap"><div id="canvas"><svg id="wires"></svg></div></div>
  <aside id="drawer" class="hidden">
    <div class="dhead">
      <div class="row">
        <div style="flex:1">
          <h2 id="dtitle"></h2>
          <p id="dsub"></p>
        </div>
        <button class="close" id="dclose">×</button>
      </div>
      <div class="tabs" id="dtabs"></div>
    </div>
    <div id="dbody"></div>
  </aside>
</main>
<div class="legend">
  <span><i class="swatch" style="border-color:#4f555d"></i>코드가 확인한 연결</span>
  <span><i class="swatch" style="border-color:#4f555d;border-top-style:dashed"></i>NOTES.md만 주장하는 연결</span>
  <span><i class="swatch" style="border-color:var(--gold)"></i>선택한 단계의 하류 · 다시 만들어야 함</span>
  <span><i class="swatch" style="border-color:var(--blue)"></i>상류 · 이 단계가 의존함</span>
  <span>노드 클릭 = 드로어 · 선 클릭 = 흐르는 산출물 · Esc 닫기 · ↑↓ 이동</span>
</div>

<script>
const DATA = __DATA__;

/* ------------------------------------------------------------- utilities */
const esc = s => String(s ?? "").replace(/[&<>"']/g, c =>
  ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const url = p => p.split("/").map(encodeURIComponent).join("/");
const kb = n => n < 1024 ? n + " B"
  : n < 1048576 ? (n/1024).toFixed(0) + " KB"
  : (n/1048576).toFixed(1) + " MB";

const STATE_LABEL = {
  wired:"코드가 만듦", authored:"손으로 씀", empty:"비어 있음",
  ok:"다음 단계로 넘어감", unread:"아무 도구도 안 읽음",
  "self-only":"만든 도구만 씀", "stage-local":"같은 단계 안에서만",
  record:"기록물", "dead-branch":"나가는 곳 없음",
};
const FLAG_TONE = {unread:"bad", "dead-branch":"bad", "self-only":"warn",
  "stage-local":"warn", record:"", ok:"ok"};

let view = "stage", attemptIndex = 0, sel = null, selEdge = null, tab = null;

const A = () => DATA.attempts[attemptIndex];
const nodes = () => view === "stage" ? A().stages : A().artifacts;
const edges = () => view === "stage" ? A().edges : A().artifact_edges;
const nodeById = id => nodes().find(n => n.id === id);

/* --------------------------------------------------------------- closure */
function reach(id, dir) {
  const adj = {};
  for (const e of edges()) {
    const [a, b] = dir === "down" ? [e.from, e.to] : [e.to, e.from];
    (adj[a] = adj[a] || []).push(b);
  }
  const seen = new Set(), queue = [id];
  while (queue.length) {
    for (const next of adj[queue.shift()] || []) {
      if (!seen.has(next)) { seen.add(next); queue.push(next); }
    }
  }
  seen.delete(id);
  return seen;
}

/* ---------------------------------------------------------------- layout */
const NW = 348, TOP = 34, LANE = 24;
let NX = 60;   // set per layout, so back-edge lanes never run under the nodes
let NH = 96, ROW = 130;   // artifact cards carry two more lines than stage cards

function assignLanes(list, key) {
  const lanes = [];
  for (const e of list) {
    const lo = Math.min(e.i, e.j), hi = Math.max(e.i, e.j);
    let lane = 0;
    while (lanes[lane] && lanes[lane].some(s => !(hi <= s[0] || lo >= s[1]))) lane++;
    (lanes[lane] = lanes[lane] || []).push([lo, hi]);
    e[key] = lane;
  }
  return lanes.length;
}

function layout() {
  NH = view === "stage" ? 96 : 118;
  ROW = NH + 34;
  const list = nodes();
  const index = {};
  list.forEach((n, i) => index[n.id] = i);
  const y = i => TOP + i * ROW;

  const drawn = edges()
    .filter(e => index[e.from] !== undefined && index[e.to] !== undefined)
    .map(e => ({...e, i: index[e.from], j: index[e.to]}));

  const right = drawn.filter(e => e.j > e.i + 1);
  const left  = drawn.filter(e => e.j < e.i);
  const rLanes = assignLanes(right.sort((a,b) => (a.j-a.i) - (b.j-b.i)), "lane");
  const lLanes = assignLanes(left.sort((a,b) => (a.i-a.j) - (b.i-b.j)), "lane");

  NX = 34 + (lLanes ? 26 + lLanes * LANE : 0);
  return {
    list, index, y, drawn,
    width: NX + NW + 46 + rLanes * LANE + 30,
    height: TOP + list.length * ROW + 40,
  };
}

/* ----------------------------------------------------------------- paint */
function paint() {
  const L = layout();
  const canvas = document.getElementById("canvas");
  const svg = document.getElementById("wires");
  canvas.style.width = L.width + "px";
  canvas.style.height = L.height + "px";
  svg.setAttribute("width", L.width);
  svg.setAttribute("height", L.height);

  const down = sel ? reach(sel, "down") : new Set();
  const up   = sel ? reach(sel, "up")   : new Set();

  /* wires */
  const arrow = (id, color) =>
    `<marker id="${id}" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7"
      orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="${color}"/></marker>`;
  let svgHtml = `<defs>${arrow("a-d","#4f555d")}${arrow("a-hot","#d6b260")}${arrow("a-up","#7d9dc4")}${arrow("a-f","#26292e")}</defs>`;
  const labels = [];

  for (const e of L.drawn) {
    const y1 = L.y(e.i), y2 = L.y(e.j);
    const hot = sel && (e.from === sel || (down.has(e.from) && down.has(e.to)) || (e.from === sel));
    const isDown = sel && (e.from === sel || down.has(e.from)) && (e.to === sel || down.has(e.to));
    const isUp   = sel && (e.to === sel || up.has(e.to)) && (e.from === sel || up.has(e.from));
    const on = isDown || isUp;
    const tone = !sel ? "d" : isDown ? "hot" : isUp ? "up" : "f";
    const color = {d:"#4f555d", hot:"#d6b260", up:"#7d9dc4", f:"#26292e"}[tone];
    const dash = e.origin === "docs" ? ' stroke-dasharray="5 4"' : "";
    const w = on ? 2 : 1.4;

    let d, lx, ly;
    if (e.j === e.i + 1) {
      const x = NX + NW / 2;
      d = `M${x},${y1 + NH} L${x},${y2 - 7}`;
      lx = x + 10; ly = (y1 + NH + y2) / 2;
    } else if (e.j > e.i) {
      const x0 = NX + NW, gx = NX + NW + 30 + e.lane * LANE;
      d = `M${x0},${y1 + NH/2} C${gx},${y1 + NH/2} ${gx},${y2 + NH/2} ${x0 + 7},${y2 + NH/2}`;
      lx = gx + 6; ly = (y1 + y2) / 2 + NH/2;
    } else {
      const x0 = NX, gx = NX - 26 - e.lane * LANE;
      d = `M${x0},${y1 + NH/2} C${gx},${y1 + NH/2} ${gx},${y2 + NH/2} ${x0 - 7},${y2 + NH/2}`;
      lx = gx - 6; ly = (y1 + y2) / 2 + NH/2;
    }
    const key = e.from + "::" + e.to;
    const text = e.artifacts.length === 1
      ? e.artifacts[0].split("/").slice(-1)[0]
      : e.artifacts.length + "개";
    svgHtml += `<path d="${d}" fill="none" stroke="${color}" stroke-width="${w}"${dash}
      marker-end="url(#a-${tone})" data-edge="${esc(key)}"><title>${esc(e.from)} → ${esc(e.to)}
${esc(e.artifacts.join("\n"))}</title></path>`;

    // In artifact view every edge is labelled with the tool that bridges it,
    // and the labels pile on top of each other. The hover title carries the
    // same text, and clicking the line opens it in the drawer.
    if (view === "stage" || on) {
      labels.push(`<div class="elabel${on ? " hot" : ""}" data-edge="${esc(key)}"
        style="left:${lx}px;top:${ly - 9}px;${!sel || on ? "" : "opacity:.25"}">${esc(text)}</div>`);
    }
  }
  svg.innerHTML = svgHtml;

  /* nodes */
  let html = "";
  L.list.forEach((n, i) => {
    const cls = ["node", view === "artifact" ? "artifact" : ""];
    if (sel === n.id) cls.push("sel");
    else if (down.has(n.id)) cls.push("down");
    else if (up.has(n.id)) cls.push("up");
    else if (sel) cls.push("faded");

    let body;
    if (view === "stage") {
      const c = n.counts;
      const flags = n.flags.map(f =>
        `<span class="pill ${FLAG_TONE[f] || "warn"}">${esc(STATE_LABEL[f] || f)}</span>`).join("");
      body = `<div class="top"><span class="nid">${esc(n.id)}</span>
          <span class="pill ${n.state}">${esc(STATE_LABEL[n.state])}</span>${flags}</div>
        <div class="ntitle">${esc(n.title || "")}</div>
        <div class="nmeta">
          <span>프롬프트 <i>${c.prompts}</i></span><span>출력 <i>${c.output}</i></span>
          <span>기각 <i>${c.rejected}</i></span><span>검사 <i>${c.qa}</i></span>
          ${n.tools.length ? `<span>도구 <i>${n.tools.length}</i></span>` : ""}
        </div>`;
    } else {
      const tone = FLAG_TONE[n.state] || "ok";
      body = `<div class="top"><span class="nid">${esc(n.label)}</span>
          <span class="pill ${tone}">${esc(STATE_LABEL[n.state] || n.state)}</span></div>
        <div class="ntitle">${esc(n.sub)}</div>
        <div class="nmeta">
          <span>파일 <i>${n.files.length}</i>${n.producer_inferred ? " · 생산자 추론" : ""}</span>
          <span>만듦 <i>${esc(n.producers.join(", ") || "—")}</i></span>
          <span>다음 단계로 <i>${esc(n.downstream.join(", ") || "넘어가지 않음")}</i></span>
        </div>`;
    }
    html += `<div class="${cls.filter(Boolean).join(" ")}" data-node="${esc(n.id)}"
      style="left:${NX}px;top:${L.y(i)}px;width:${NW}px;height:${NH}px">${body}</div>`;
  });

  canvas.querySelectorAll(".node,.elabel").forEach(el => el.remove());
  canvas.insertAdjacentHTML("beforeend", html + labels.join(""));
}

/* ----------------------------------------------------------------- stats */
function paintStats() {
  const a = A();
  const count = s => a.artifacts.filter(x => x.state === s).length;
  const dead = a.stages.filter(s => s.dead_branch).length;
  const empty = a.stages.filter(s => s.state === "empty").length;
  const claims = a.edges.filter(e => e.origin === "docs").length;
  const box = (n, label, tone) =>
    `<span class="stat ${n ? tone : ""}"><b>${n}</b>${esc(label)}</span>`;
  document.getElementById("stats").innerHTML =
    box(dead, "나가는 곳 없는 단계", "bad") +
    box(count("unread") + count("self-only"), "아무 데도 안 넘어가는 산출물", "bad") +
    box(count("stage-local"), "같은 단계 안에서만 도는 산출물", "warn") +
    box(empty, "빈 단계", "warn") +
    box(claims, "문서만 주장하는 연결", "warn");
}

/* ---------------------------------------------------------------- drawer */
function mdToHtml(src) {
  const lines = String(src).split("\n");
  let out = "", inTable = false, inList = false, inCode = false;
  const inline = s => esc(s)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
  for (const raw of lines) {
    const line = raw.trimEnd();
    if (line.startsWith("```")) {
      out += inCode ? "</pre>" : '<pre class="prompt">';
      inCode = !inCode; continue;
    }
    if (inCode) { out += esc(raw) + "\n"; continue; }
    const isRow = /^\|.*\|$/.test(line);
    if (isRow && /^\|[\s:|-]+\|$/.test(line)) continue;
    if (isRow) {
      if (!inTable) { out += "<table>"; inTable = true; }
      const cells = line.slice(1, -1).split("|").map(c => `<td>${inline(c.trim())}</td>`).join("");
      out += `<tr>${cells}</tr>`; continue;
    }
    if (inTable) { out += "</table>"; inTable = false; }
    const li = line.match(/^[-*]\s+(.*)/);
    if (li) {
      if (!inList) { out += "<ul>"; inList = true; }
      out += `<li>${inline(li[1])}</li>`; continue;
    }
    if (inList) { out += "</ul>"; inList = false; }
    const h = line.match(/^(#{1,6})\s+(.*)/);
    if (h) { out += `<h3>${inline(h[2])}</h3>`; continue; }
    if (line === "---") { out += "<hr>"; continue; }
    if (line.trim()) out += `<p>${inline(line)}</p>`;
  }
  if (inTable) out += "</table>";
  if (inList) out += "</ul>";
  if (inCode) out += "</pre>";
  return out;
}

function thumbs(files) {
  if (!files.length) return '<p class="none">없음</p>';
  const media = files.filter(f => f.kind === "image" || f.kind === "video");
  const rest = files.filter(f => f.kind !== "image" && f.kind !== "video");
  let out = "";
  if (media.length) {
    out += '<div class="grid">' + media.map(f => `
      <div class="thumb"><a href="${url(f.rel)}" target="_blank">
        ${f.kind === "image"
          ? `<img src="${url(f.rel)}" loading="lazy" alt="">`
          : `<video src="${url(f.rel)}" controls preload="metadata"></video>`}
        <div class="cap">${esc(f.name)}</div></a></div>`).join("") + "</div>";
  }
  if (rest.length) {
    out += '<div class="filelist">' + rest.map(f =>
      `<a href="${url(f.rel)}" target="_blank"><span>${esc(f.rel)}</span>
        <span class="sz">${kb(f.bytes)}</span></a>`).join("") + "</div>";
  }
  return out;
}

/* --------------------------------------------------- structured json view
   The stage outputs that matter are JSON: shot cards, receipts, gate results.
   Reading them as escaped text is how the sheet-that-nothing-read went unseen
   for a whole version. Objects become key/value tables, uniform arrays become
   real tables, and anything too long for a cell drops into a block underneath
   so the table stays scannable. The raw text is one click away. */
const SCALAR = v => v === null || ["string", "number", "boolean"].includes(typeof v);

function jsonScalar(v) {
  if (v === null) return '<span class="nil">없음</span>';
  if (typeof v === "boolean") return `<span class="jb">${v ? "예" : "아니오"}</span>`;
  if (typeof v === "number") return `<span class="jn">${v}</span>`;
  const s = String(v);
  if (!s) return '<span class="nil">빈 문자열</span>';
  if (s.length > 160) return `<div class="jlong">${esc(s)}</div>`;
  if (/\.(png|jpg|jpeg|webp|mp4|mov|webm|json)$/i.test(s)) return `<span class="jf">${esc(s)}</span>`;
  return esc(s);
}

function jsonNode(v, depth) {
  if (depth > 7) return '<span class="nil">…</span>';
  if (SCALAR(v)) return jsonScalar(v);
  if (Array.isArray(v)) return jsonArray(v, depth);
  return jsonObject(v, depth);
}

function jsonObject(o, depth) {
  const keys = Object.keys(o);
  if (!keys.length) return '<span class="nil">비어 있음</span>';
  return "<table class='jt'>" + keys.map(k =>
    `<tr><td class="jkey">${esc(k)}</td><td>${jsonNode(o[k], depth + 1)}</td></tr>`).join("")
    + "</table>";
}

function jsonArray(a, depth) {
  if (!a.length) return '<span class="nil">비어 있음</span>';
  if (a.every(SCALAR) && a.every(x => x === null || String(x).length <= 60)) {
    return '<div class="chiprow">' + a.map(x => `<span class="jchip">${jsonScalar(x)}</span>`).join("") + "</div>";
  }
  if (a.every(x => x && typeof x === "object" && !Array.isArray(x))) return jsonTable(a, depth);
  return a.map((x, i) =>
    `<div class="jnest"><div class="subh">#${i + 1}</div>${jsonNode(x, depth + 1)}</div>`).join("");
}

function jsonTable(rows, depth) {
  const keys = [];
  for (const r of rows) for (const k of Object.keys(r)) if (!keys.includes(k)) keys.push(k);
  const fitsCell = k => rows.every(r =>
    r[k] === undefined || (SCALAR(r[k]) && String(r[k] ?? "").length <= 64));
  const cols = keys.filter(fitsCell).slice(0, 9);
  const details = keys.filter(k => !cols.includes(k));

  if (!cols.length) {
    return rows.map(r => `<div class="jnest">${jsonObject(r, depth + 1)}</div>`).join("");
  }

  let out = '<div class="jscroll"><table class="jt grid"><tr>'
    + cols.map(k => `<th>${esc(k)}</th>`).join("") + "</tr>"
    + rows.map(r => "<tr>" + cols.map(k =>
        `<td>${r[k] === undefined ? '<span class="nil">—</span>' : jsonScalar(r[k])}</td>`).join("") + "</tr>").join("")
    + "</table></div>";

  if (details.length) {
    out += rows.map((r, i) => {
      const has = details.filter(k => r[k] !== undefined);
      if (!has.length) return "";
      const head = cols.map(k => r[k]).find(v => v !== undefined && String(v).length < 40);
      return `<div class="card closed"><div class="ch">
          <span class="k">${esc(String(head ?? "#" + (i + 1)))}</span>
          <span class="s">${esc(has.join(" · "))}</span></div>
        <div class="cb">` + has.map(k =>
          `<div class="subh">${esc(k)}</div>${jsonNode(r[k], depth + 1)}`).join("") + "</div></div>";
    }).join("");
  }
  return out;
}

let jsonSeq = 0;

function textBlock(file) {
  if (!file || file.text === undefined) return "";
  const raw = `<pre class="prompt">${esc(file.text)}${file.truncated ? "\n… 잘림" : ""}</pre>`;
  if (!file.name.endsWith(".json") || file.truncated) return raw;
  let data;
  try { data = JSON.parse(file.text); } catch { return raw; }
  const id = "j" + (++jsonSeq);
  return `<div class="jwrap">
    <div class="seg small" data-jsontoggle="${id}">
      <button class="on" data-mode="table">표</button><button data-mode="raw">원본</button></div>
    <div data-json="${id}" data-panel="table">${jsonNode(data, 0)}</div>
    <div data-json="${id}" data-panel="raw" hidden>${raw}</div></div>`;
}

function promptCards(stage) {
  if (!stage.packs.length) return '<p class="none">이 단계는 프롬프트를 보내지 않는다. 손으로 쓴 문서가 산출물이다.</p>';
  let out = "";
  for (const pack of stage.packs) {
    out += `<section class="blk"><h3>${esc(pack.file)}</h3>`;
    if (pack.meta.length) {
      out += "<table class='kv'>" + pack.meta.map(([k, v]) =>
        `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join("") + "</table>";
    }
    for (const group of pack.groups) {
      for (const e of group.entries) {
        const refs = e.ref_files.length
          ? `<div class="subh">함께 들어간 레퍼런스</div>${thumbs(e.ref_files)}` : "";
        const res = `<div class="subh">이 단계의 결과물</div>${thumbs(e.results)}`
          + (e.downstream.length
            ? `<div class="subh" style="margin-top:12px">이후 단계에서 이것이 된 것</div>${thumbs(e.downstream)}`
            : "");
        out += `<div class="card closed">
          <div class="ch"><span class="k">${esc(e.label)}</span>
            <span class="s">${esc(e.meta.slice(0,3).map(m => m[1]).join(" · ").slice(0,70))}</span>
            <span class="s" style="margin-left:auto">${e.results.length ? "결과 " + e.results.length : "결과 없음"}</span></div>
          <div class="cb"><div class="pair">
            <div><pre class="prompt">${esc(e.prompt)}</pre>
              ${e.meta.length ? "<table class='kv'>" + e.meta.map(([k,v]) =>
                `<tr><td>${esc(k)}</td><td>${esc(String(v).slice(0,400))}</td></tr>`).join("") + "</table>" : ""}
            </div>
            <div>${res}${refs}</div>
          </div></div></div>`;
      }
    }
    out += "</section>";
  }
  return out;
}

function impactBlock(id) {
  const down = [...reach(id, "down")], up = [...reach(id, "up")];
  const chips = (ids, cls) => ids.length
    ? ids.map(x => `<button class="chip ${cls}" data-node="${esc(x)}">${esc(x)}</button>`).join("")
    : '<span class="none">없음</span>';
  return `<div class="impact">
    <h3>이 노드를 바꾸면 다시 만들어야 하는 것</h3>
    <div class="chiprow">${chips(down, "down")}</div>
    <h3 style="margin-top:12px">이 노드가 기대고 있는 것</h3>
    <div class="chiprow">${chips(up, "up")}</div></div>`;
}

function stageTabs(stage) {
  return [
    ["overview", "개요", true],
    ["prompts", "프롬프트 · 결과", stage.packs.length > 0],
    ["output", "산출물", stage.counts.output > 0],
    ["qa", "검사", stage.counts.qa > 0 || !!stage.receipt],
    ["rejected", "기각", stage.counts.rejected > 0],
  ];
}

function stageBody(stage, which) {
  if (which === "prompts") return promptCards(stage);
  if (which === "output") return thumbs(stage.files.output) +
    stage.files.output.filter(f => f.kind === "text").map(f =>
      `<section class="blk"><h3>${esc(f.name)}</h3>${textBlock(f)}</section>`).join("");
  if (which === "qa") return (stage.receipt
      ? `<section class="blk"><h3>receipt.json</h3>${textBlock(stage.receipt)}</section>` : "")
    + thumbs(stage.files.qa)
    + stage.files.qa.filter(f => f.kind === "text").map(f =>
      `<section class="blk"><h3>${esc(f.name)}</h3>${textBlock(f)}</section>`).join("");
  if (which === "rejected") return thumbs(stage.files.rejected);

  const inbound = A().edges.filter(e => e.to === stage.id);
  const outbound = A().edges.filter(e => e.from === stage.id);
  const flow = (list, dir) => list.length ? `<div class="filelist">` + list.map(e =>
      `<a><span>${esc(dir === "in" ? e.from : e.to)} · ${esc(e.artifacts.join(", "))}</span>
       <span class="sz">${e.origin === "docs" ? "문서 주장" : e.origin === "both" ? "코드+문서" : "코드 확인"}</span></a>`
    ).join("") + "</div>" : '<p class="none">없음</p>';

  const arts = A().artifacts.filter(x => x.stage === stage.id);
  const artRows = arts.length ? "<table class='kv'>" + arts.map(x =>
    `<tr><td>${esc(x.sub)}</td><td>${esc(STATE_LABEL[x.state] || x.state)} ·
      파일 ${x.files.length} · 읽는 도구 ${x.consumers.join(", ") || "없음"}</td></tr>`).join("")
    + "</table>" : '<p class="none">코드가 만지는 산출물이 없다</p>';

  const verdict = stage.dead_branch ? `<div class="impact" style="border-color:#4a2f2a">
      <h3 style="color:var(--red)">이 단계는 나가는 곳이 없다</h3>
      <p style="margin:0;font-size:12.5px;color:#c4bdb0">
        출력이 ${stage.counts.output}개 있는데 뒤의 어떤 도구도 이 단계를 읽지 않는다.
        ${stage.copies.length ? "게다가 출력 " + stage.copies.length +
          "개가 주제 층 파일의 바이트 단위 사본이다. 실제 소비자는 사본이 아니라 원본을 읽는다." : ""}</p>
      ${stage.copies.length ? '<table class="kv" style="margin-top:8px">' + stage.files.output
        .filter(f => f.copy_of)
        .map(f => `<tr><td>${esc(f.name)}</td><td>${esc(f.copy_of)} 와 동일</td></tr>`).join("")
        + "</table>" : ""}
    </div>` : "";

  return verdict + impactBlock(stage.id)
    + `<section class="blk"><h3>들어오는 것</h3>${flow(inbound, "in")}</section>`
    + `<section class="blk"><h3>나가는 것</h3>${flow(outbound, "out")}</section>`
    + `<section class="blk"><h3>이 단계의 산출물 상태</h3>${artRows}</section>`
    + (stage.notes ? `<section class="blk"><h3>NOTES.md</h3>
        <div class="md">${mdToHtml(stage.notes)}</div></section>` : "");
}

function artifactBody(node, which) {
  if (which === "files") return thumbs(node.files) +
    node.files.filter(f => f.kind === "text").slice(0, 6).map(f =>
      `<section class="blk"><h3>${esc(f.name)}</h3>${textBlock(f)}</section>`).join("");
  const tools = A().tools;
  const row = t => `<tr><td>${esc(t.tool)}</td><td>쓰기 ${esc((t.writes.concat(t.both)).join(", ") || "—")}<br>
    읽기 ${esc(t.reads.concat(t.mentions).join(", ") || "—")}</td></tr>`;
  const related = tools.filter(t => node.producers.includes(t.tool) || node.consumers.includes(t.tool));
  return impactBlock(node.id)
    + `<section class="blk"><h3>판정</h3><table class="kv">
        <tr><td>종류</td><td>${esc({asset:"자산", prompt:"프롬프트 팩", record:"기록"}[node.klass] || node.klass)}</td></tr>
        <tr><td>상태</td><td>${esc(STATE_LABEL[node.state] || node.state)}</td></tr>
        <tr><td>만드는 도구</td><td>${esc(node.producers.join(", ") || "코드에서 확인 안 됨")}
          ${node.producer_inferred ? '<span class="pill warn">추론</span>' : ""}</td></tr>
        <tr><td>만지는 도구</td><td>${esc(node.consumers.join(", ") || "없음")}</td></tr>
        <tr><td>다음 단계로</td><td>${esc(node.downstream.join(", ") || "넘어가지 않는다")}</td></tr>
        <tr><td>디스크</td><td>파일 ${node.files.length}개</td></tr></table></section>`
    + `<section class="blk"><h3>관련 도구</h3>${related.length
        ? "<table class='kv'>" + related.map(row).join("") + "</table>"
        : '<p class="none">없음</p>'}</section>`;
}

function openNode(id) {
  const node = nodeById(id);
  if (!node) return;
  sel = id; selEdge = null;
  const tabsDef = view === "stage" ? stageTabs(node)
    : [["overview", "개요", true], ["files", "파일 " + node.files.length, node.files.length > 0]];
  if (!tabsDef.some(t => t[0] === tab && t[2])) {
    tab = view === "stage" && node.packs.length ? "prompts" : "overview";
  }
  document.getElementById("drawer").classList.remove("hidden");
  document.getElementById("dtitle").textContent = view === "stage" ? node.id : node.label;
  document.getElementById("dsub").textContent = view === "stage"
    ? (node.title || "") : node.sub;
  document.getElementById("dtabs").innerHTML = tabsDef.map(([k, label, on]) =>
    `<button data-tab="${k}" class="${tab === k ? "on" : ""}" ${on ? "" : "disabled"}>${esc(label)}</button>`).join("");
  document.getElementById("dbody").innerHTML = view === "stage"
    ? stageBody(node, tab) : artifactBody(node, tab);
  document.getElementById("dbody").scrollTop = 0;
  paint();
}

function openEdge(key) {
  const [from, to] = key.split("::");
  const edge = edges().find(e => e.from === from && e.to === to);
  if (!edge) return;
  sel = from; selEdge = key; tab = "overview";
  document.getElementById("drawer").classList.remove("hidden");
  document.getElementById("dtitle").textContent = from + "  →  " + to;
  document.getElementById("dsub").textContent =
    edge.origin === "docs" ? "NOTES.md만 주장하는 연결이다. 코드는 이 흐름을 확인해 주지 않는다."
    : edge.origin === "both" ? "코드와 문서가 일치한다" : "코드가 확인한 연결";
  document.getElementById("dtabs").innerHTML = "";
  document.getElementById("dbody").innerHTML =
    `<section class="blk"><h3>이 선을 타고 흐르는 것</h3><div class="filelist">` +
    edge.artifacts.map(a => `<a><span>${esc(a)}</span></a>`).join("") +
    `</div></section>` + impactBlock(to);
  paint();
}

/* ------------------------------------------------------------------ wire */
function loadAttempt() {
  const select = document.getElementById("attempt");
  select.innerHTML = DATA.attempts.map((a, i) =>
    `<option value="${i}" ${i === attemptIndex ? "selected" : ""}>${esc(a.id)}</option>`).join("");
  sel = null; selEdge = null;
  document.getElementById("drawer").classList.add("hidden");
  paintStats(); paint();
}

document.getElementById("attempt").addEventListener("change", e => {
  attemptIndex = +e.target.value; loadAttempt();
});
document.getElementById("viewseg").addEventListener("click", e => {
  const button = e.target.closest("button"); if (!button) return;
  view = button.dataset.view; sel = null; selEdge = null; tab = null;
  document.querySelectorAll("#viewseg button").forEach(b => b.classList.toggle("on", b === button));
  document.getElementById("drawer").classList.add("hidden");
  paint();
});
document.getElementById("dclose").addEventListener("click", () => {
  sel = null; selEdge = null;
  document.getElementById("drawer").classList.add("hidden"); paint();
});
document.getElementById("dtabs").addEventListener("click", e => {
  const button = e.target.closest("button[data-tab]");
  if (button && !button.disabled) { tab = button.dataset.tab; openNode(sel); }
});
document.getElementById("canvas").addEventListener("click", e => {
  const node = e.target.closest("[data-node]");
  if (node) return openNode(node.dataset.node);
  const edge = e.target.closest("[data-edge]");
  if (edge) return openEdge(edge.dataset.edge);
});
document.getElementById("dbody").addEventListener("click", e => {
  const chip = e.target.closest(".chip[data-node]");
  if (chip) { tab = null; return openNode(chip.dataset.node); }

  const toggle = e.target.closest("[data-jsontoggle] button");
  if (toggle) {
    const id = toggle.parentElement.dataset.jsontoggle;
    toggle.parentElement.querySelectorAll("button")
      .forEach(b => b.classList.toggle("on", b === toggle));
    document.querySelectorAll(`[data-json="${id}"]`)
      .forEach(p => p.hidden = p.dataset.panel !== toggle.dataset.mode);
    return;
  }

  const head = e.target.closest(".card > .ch");
  if (head) head.parentElement.classList.toggle("closed");
});
document.addEventListener("keydown", e => {
  if (e.key === "Escape") {
    sel = null; selEdge = null;
    document.getElementById("drawer").classList.add("hidden"); paint();
  }
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    const list = nodes();
    const at = list.findIndex(n => n.id === sel);
    const next = e.key === "ArrowDown" ? Math.min(at + 1, list.length - 1) : Math.max(at - 1, 0);
    if (list[next]) { e.preventDefault(); tab = null; openNode(list[next].id); }
  }
});

loadAttempt();
</script>
"""


def render(report: dict, out: Path) -> Path:
    payload = json.dumps(report, ensure_ascii=False, separators=(",", ":"))
    page = PAGE.replace("__TITLE__", report["topic"]).replace("__DATA__", payload)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return out


def summarise(report: dict) -> list[dict]:
    rows = []
    for attempt in report["attempts"]:
        rows.append({
            "attempt": attempt["id"],
            "stages": len(attempt["stages"]),
            "dead_branch_stages": [s["id"] for s in attempt["stages"] if s["dead_branch"]],
            "output_that_is_a_copy": {s["id"]: s["copies"]
                                      for s in attempt["stages"] if s["copies"]},
            "empty_stages": [s["id"] for s in attempt["stages"] if s["state"] == "empty"],
            "never_handed_on": [a["id"] for a in attempt["artifacts"]
                                if a["state"] in {"unread", "self-only"}],
            "stage_local_only": [a["id"] for a in attempt["artifacts"]
                                 if a["state"] == "stage-local"],
            "claimed_only_edges": [f"{e['from']} -> {e['to']}" for e in attempt["edges"]
                                   if e["origin"] == "docs"],
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="단계 그래프 대시보드를 만든다")
    parser.add_argument("topic", type=Path)
    parser.add_argument("--out", type=Path, help="기본값은 <topic>/PIPELINE.html")
    args = parser.parse_args()

    report = scan_topic(args.topic)
    target = render(report, args.out or args.topic / "PIPELINE.html")
    print(f"작성: {target}")
    print(json.dumps(summarise(report), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
