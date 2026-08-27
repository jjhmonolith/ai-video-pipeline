"""Cross-stage lifecycle records for direction changes and draft/release state."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from .contract import Contract


def canonical_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def direction_impact(attempt: Path, contract: Contract, direction: dict) -> dict:
    """Mark files that predate a supplement; semantic compatibility needs review."""
    supplements = direction.get("supplements") or []
    latest = max((_parse_time(s["received_at"]) for s in supplements), default=None)
    roles = {
        "subject_definition": (contract.stage_for("premise", "01-premise"),
                               "output/subjects/*.json"),
        "reference_sheet": (contract.stage_for("sheet", "02-sheet"),
                            "output/sheets/*.png"),
        "scenario": (contract.stage_for("scenario", "03-scenario"),
                     "output/scenario.json"),
    }
    direction_sha256 = canonical_digest(direction)
    sheet_times = {}
    sheet_time_sources = {}
    sheet_receipt = attempt / contract.stage_for("sheet", "02-sheet") / "receipt.json"
    if sheet_receipt.exists():
        try:
            for record in json.loads(sheet_receipt.read_text(encoding="utf-8")).get("sheets", []):
                element = record.get("element")
                revalidation = record.get("direction_revalidation") or {}
                if (
                    revalidation.get("status") == "compatible"
                    and revalidation.get("direction_sha256") == direction_sha256
                    and revalidation.get("revalidated_at")
                    and revalidation.get("basis")
                ):
                    sheet_times[element] = revalidation["revalidated_at"]
                    sheet_time_sources[element] = "sheet.receipt.direction_revalidation.revalidated_at"
                elif record.get("created_at"):
                    sheet_times[element] = record["created_at"]
                    sheet_time_sources[element] = "sheet.receipt.created_at"
        except (OSError, json.JSONDecodeError):
            pass
    sheet_review = attempt / contract.stage_for("sheet", "02-sheet") / "qa" / "semantic-review.json"
    if sheet_review.exists():
        try:
            review_payload = json.loads(sheet_review.read_text(encoding="utf-8"))
            for record in review_payload.get("reviews", []):
                if (record.get("reference_ready") is True
                        and record.get("status") == "approved"
                        and record.get("reviewed_at")):
                    sheet_times[record.get("subject_id")] = record["reviewed_at"]
                    sheet_time_sources[record.get("subject_id")] = \
                        "sheet.semantic-review.reviewed_at"
        except (OSError, json.JSONDecodeError):
            pass
    artifacts = []
    for artifact_type, (stage, pattern) in roles.items():
        for path in sorted((attempt / stage).glob(pattern)):
            source = "filesystem_mtime"
            recorded_time = None
            if artifact_type == "subject_definition":
                try:
                    provenance = (json.loads(path.read_text(encoding="utf-8"))
                                  .get("provenance", {}))
                    recorded_time = provenance.get("approved_at") or provenance.get("decided_at")
                    source = ("subject.provenance.approved_at" if provenance.get("approved_at")
                              else "subject.provenance.decided_at")
                except (OSError, json.JSONDecodeError):
                    pass
            elif artifact_type == "scenario":
                try:
                    recorded_time = json.loads(path.read_text(encoding="utf-8")).get("written_at")
                    source = "scenario.written_at"
                except (OSError, json.JSONDecodeError):
                    pass
            elif artifact_type == "reference_sheet" and sheet_times.get(path.stem):
                recorded_time = sheet_times[path.stem]
                source = sheet_time_sources.get(path.stem, "sheet.receipt.created_at")
            modified = (_parse_time(recorded_time) if recorded_time else
                        datetime.fromtimestamp(path.stat().st_mtime).astimezone())
            if latest is None:
                status, basis = "unaffected", "direction supplement가 없다"
            elif modified < latest:
                status = "revalidation_required"
                basis = "artifact timestamp가 최신 direction supplement보다 앞선다"
            else:
                status = "compatible"
                basis = "artifact timestamp가 최신 direction supplement 이후다"
            artifacts.append({
                "artifact": str(path.relative_to(attempt)), "artifact_type": artifact_type,
                "stage": stage, "artifact_modified_at": modified.isoformat(timespec="seconds"),
                "timestamp_source": source, "status": status, "basis": basis,
            })
    unresolved = [a for a in artifacts
                  if a["status"] in {"revalidation_required", "regeneration_required"}]
    return {
        "schema_version": "direction-impact.v1",
        "direction_sha256": direction_sha256,
        "supplements": supplements,
        "latest_supplement_at": latest.isoformat(timespec="seconds") if latest else None,
        "reviewed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "reviewed_by": "pipeline-timestamp-audit",
        "policy": "timestamps can require review but cannot prove semantic compatibility",
        "artifacts": artifacts,
        "unresolved_count": len(unresolved),
        "downstream_allowed": not unresolved,
    }


def write_direction_impact(attempt: Path, contract: Contract, direction: dict) -> Path:
    target = attempt / contract.stage_for("premise", "01-premise") / "qa" / "direction-impact.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(direction_impact(attempt, contract, direction),
                                 ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def read_direction_impact(attempt: Path, contract: Contract) -> dict:
    path = attempt / contract.stage_for("premise", "01-premise") / "qa" / "direction-impact.json"
    if not path.exists():
        return {"unresolved_count": 0, "downstream_allowed": True,
                "status": "not_assessed"}
    return json.loads(path.read_text(encoding="utf-8"))


def read_premise_state(attempt: Path, contract: Contract) -> dict:
    """State copied into draft downstream records; absence is never release approval."""
    path = attempt / contract.stage_for("premise", "01-premise") / "qa" / "report.json"
    if not path.exists():
        return {"form_ok": None, "human_approved": False, "release_eligible": False,
                "production_state": "not_assessed", "source": str(path.relative_to(attempt))}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {"form_ok": data.get("form_ok"),
            "human_approved": bool(data.get("human_approved", data.get("all_approved"))),
            "release_eligible": bool(data.get("release_eligible")),
            "production_state": data.get("production_state", "draft_unapproved"),
            "source": str(path.relative_to(attempt))}
