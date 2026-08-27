"""Web search that leaves a citable record, so an invented fact can still have a basis.

The supercar run's vehicle spec announced itself as fixed fact and carried no
origin at all. Its one consistency check compared two of its own numbers, which
catches a typo and says nothing about whether anyone ever agreed the numbers.
When the provenance block was finally added, `basis` had nothing to put in it
except "made up".

For a film about something real, search is sourcing. For a film about something
invented, search is still worth doing, because invention has to land inside the
plausible: an 830 ps mid-engined car that weighs 1495 kg is a claim about the
world even though the car is not real, and real cars in that class are where
you find out whether the claim is silly. A probe run for this module came back
correcting its own question, separating dry weight from kerb weight and noting
that two of the three cars were not mid-engined. That is the kind of thing a
`basis` field should be able to quote.

So a query and its answer are kept together with the URLs the answer leaned on
and the day it was asked. Nothing here decides anything. It produces evidence
that a later stage cites by id, and a reader can follow the URL and disagree.

Answers age. The record carries `asked_at` so a stale one is visible as stale
rather than quietly wrong.

Some questions are not answerable in words. A run once decided a car reviewer
holds a broadcast microphone, which reads plausibly and is not what anyone does;
one photograph of a real shoot settles it, and the prose never would have. So a
question can also ask for pictures, and the ones that come back are downloaded
and kept beside the text.

Those pictures are evidence and never generation input. They carry real brands,
real plates and real people, and feeding them to an image model would put all
three into the output. What crosses into the definition is a sentence about what
was seen.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SERVICE = "ai-native-openai-api"
DEFAULT_MODEL = "gpt-5.4"
EVIDENCE_DIRNAME = "evidence"
URL_RE = re.compile(r"https?://[^\s\)\]\"'>]+")


class ResearchError(RuntimeError):
    """The search could not be run, or came back with nothing to record."""


def _slug(text: str, limit: int = 48) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z가-힣]+", "-", text).strip("-").lower()
    return (cleaned[:limit] or "q") + "-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


@dataclass
class Evidence:
    evidence_id: str
    question: str
    answer: str
    citations: list[dict] = field(default_factory=list)
    model: str = DEFAULT_MODEL
    asked_at: str = ""
    searches: int = 0
    images: list[dict] = field(default_factory=list)
    image_dir: str = ""

    def as_dict(self) -> dict:
        return {
            "evidence_id": self.evidence_id,
            "question": self.question,
            "asked_at": self.asked_at,
            "model": self.model,
            "searches_run": self.searches,
            "answer": self.answer,
            "citations": self.citations,
            "images": self.images,
            "image_dir": self.image_dir,
            "images_on_disk": sum(1 for i in self.images if i.get("ok")),
            "note": "검색 결과는 낡는다. asked_at 을 보고 다시 물을지 판단한다. "
                    "인용은 근거이지 승인이 아니다. 사람이 URL 을 열어 확인한다",
        }


def _client(api_key: str | None = None):
    from openai import OpenAI  # 지연 임포트. 검색을 안 쓰는 경로에서 의존을 만들지 않는다

    if api_key:
        return OpenAI(api_key=api_key)
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        import keyring

        key = keyring.get_password(SERVICE, os.environ.get("USER", "jjh"))
    if not key:
        raise ResearchError(f"OpenAI 키가 없다. Keychain {SERVICE} 또는 OPENAI_API_KEY")
    return OpenAI(api_key=key)


def _citations(response: Any, answer: str) -> list[dict]:
    """Prefer the model's own annotations; fall back to URLs in the text.

    Annotations carry the title and the span the citation supports, which is
    what makes a claim checkable rather than merely accompanied by links.
    """
    found: dict[str, dict] = {}
    for item in getattr(response, "output", []) or []:
        for part in getattr(item, "content", []) or []:
            for note in getattr(part, "annotations", []) or []:
                url = getattr(note, "url", None)
                if not url:
                    continue
                found.setdefault(url, {
                    "url": url,
                    "title": getattr(note, "title", "") or "",
                    "type": getattr(note, "type", "") or "",
                })
    if not found:
        for url in URL_RE.findall(answer):
            found.setdefault(url, {"url": url, "title": "", "type": "text"})
    return list(found.values())


def ask(question: str, model: str = DEFAULT_MODEL, api_key: str | None = None,
        asked_at: str | None = None) -> Evidence:
    """One question, answered against the live web, kept with its sources."""
    client = _client(api_key)
    try:
        response = client.responses.create(
            model=model,
            tools=[{"type": "web_search"}],
            input=question,
        )
    except Exception as error:  # noqa: BLE001 - 원인을 그대로 보여주는 편이 낫다
        raise ResearchError(f"검색 실패: {type(error).__name__} {error}") from error

    answer = (getattr(response, "output_text", "") or "").strip()
    if not answer:
        raise ResearchError("응답에 본문이 없다")

    searches = sum(1 for item in (getattr(response, "output", []) or [])
                   if getattr(item, "type", "") == "web_search_call")
    return Evidence(
        evidence_id=_slug(question),
        question=question,
        answer=answer,
        citations=_citations(response, answer),
        model=model,
        asked_at=asked_at or datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        searches=searches,
    )


IMAGE_RULES = """
사진으로 확인해야 하는 질문이다. 웹에서 실제 사진이 실린 페이지를 찾고,
각 결과에 대해 직접 이미지 파일 URL 을 .jpg 또는 .png 로 끝나는 형태로 주어라.

- 최대 {count} 개.
- 스톡 일러스트나 렌더가 아니라 실제 현장 사진을 우선한다.
- 각 URL 마다 그 사진이 무엇을 보여주는지 한 줄로 적어라.
- 아래 JSON 형식 하나만 반환하라. 다른 문장을 붙이지 마라.

{{"summary": "사진들이 공통으로 보여주는 사실 한 문단",
  "images": [{{"url": "...", "shows": "...", "page": "..."}}]}}
"""


def _first_json_object(text: str) -> dict | None:
    """Pull the object out of prose, since JSON mode is unavailable here.

    Web search and JSON mode are mutually exclusive on this endpoint, so the
    shape can only be asked for, not enforced. The answer usually arrives inside
    a fence or with a sentence in front of it.
    """
    if not text.strip():
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass
    depth, start = 0, None
    for index, char in enumerate(text):
        if char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    return json.loads(text[start:index + 1])
                except json.JSONDecodeError:
                    start = None
    return None


def fetch_image(url: str, target: Path, timeout: float = 25.0) -> dict:
    """Pull one picture down so the record does not depend on a URL staying up.

    Roughly half of the direct URLs a search returns answer with 403 to a plain
    client, so a link alone is not a record. What was actually looked at has to
    sit on disk next to the note that cites it.
    """
    import urllib.error
    import urllib.request

    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            kind = response.headers.get("Content-Type", "")
    except Exception as error:  # noqa: BLE001 - 실패 사유를 그대로 남긴다
        return {"url": url, "ok": False, "problem": f"{type(error).__name__}: {error}"}

    if not kind.startswith("image/") or len(body) < 2048:
        return {"url": url, "ok": False,
                "problem": f"이미지가 아니다. content-type={kind!r} bytes={len(body)}"}

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(body)
    return {"url": url, "ok": True, "file": target.name,
            "content_type": kind, "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest()[:16]}


def look(question: str, stage_output: Path, count: int = 4,
         model: str = DEFAULT_MODEL, api_key: str | None = None) -> Evidence:
    """A question answered with pictures, downloaded and filed with the text."""
    client = _client(api_key)
    try:
        response = client.responses.create(
            model=model,
            tools=[{"type": "web_search"}],
            # JSON 모드는 웹 검색과 같이 못 쓴다. API 가 직접 그렇게 답했다.
            # "Web Search cannot be used with JSON mode." 그래서 형식은 지시로만
            # 요구하고 본문에서 뽑는다.
            input=IMAGE_RULES.format(count=count) + "\n\n질문: " + question,
        )
    except Exception as error:  # noqa: BLE001
        raise ResearchError(f"이미지 조사 실패: {type(error).__name__} {error}") from error

    found = _first_json_object(getattr(response, "output_text", "") or "")
    if found is None:
        raise ResearchError("이미지 조사 응답에서 JSON 을 찾지 못했다")

    evidence_id = _slug(question)
    holder = evidence_dir(stage_output) / evidence_id
    pulled = []
    for index, item in enumerate(found.get("images", [])[:count]):
        url = item.get("url", "")
        if not url:
            continue
        suffix = ".png" if url.lower().split("?")[0].endswith(".png") else ".jpg"
        record = fetch_image(url, holder / f"{index + 1:02d}{suffix}")
        record["shows"] = item.get("shows", "")
        record["page"] = item.get("page", "")
        pulled.append(record)

    searches = sum(1 for item in (getattr(response, "output", []) or [])
                   if getattr(item, "type", "") == "web_search_call")
    kept = [p for p in pulled if p.get("ok")]
    return Evidence(
        evidence_id=evidence_id,
        question=question,
        answer=found.get("summary", ""),
        citations=[{"url": p["url"], "title": p.get("shows", ""), "type": "image"}
                   for p in pulled],
        model=model,
        asked_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        searches=searches,
        images=pulled,
        image_dir=f"{evidence_id}/" if kept else "",
    )


def evidence_dir(stage_output: Path) -> Path:
    return Path(stage_output) / EVIDENCE_DIRNAME


def record(evidence: Evidence, stage_output: Path) -> Path:
    target = evidence_dir(stage_output) / f"{evidence.evidence_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(evidence.as_dict(), ensure_ascii=False, indent=2),
                      encoding="utf-8")
    return target


def load_all(stage_output: Path) -> dict[str, dict]:
    directory = evidence_dir(stage_output)
    if not directory.exists():
        return {}
    return {p.stem: json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(directory.glob("*.json"))}


def check_citations(stage_output: Path, cited: list[str]) -> dict:
    """Every evidence id a definition leans on must exist and carry a source.

    A basis that points at nothing is worse than an empty basis, because it
    reads as though someone checked.
    """
    have = load_all(stage_output)
    missing = [c for c in cited if c not in have]
    uncited = [eid for eid, ev in have.items() if not ev.get("citations")]
    return {
        "evidence_on_file": sorted(have),
        "referenced_but_missing": missing,
        "recorded_without_any_source": uncited,
        "ok": not missing and not uncited,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="웹 검색을 하고 인용과 함께 근거로 남긴다")
    sub = parser.add_subparsers(dest="command", required=True)

    one = sub.add_parser("ask")
    one.add_argument("question")
    one.add_argument("--out", type=Path, required=True, help="단계의 output 폴더")
    one.add_argument("--model", default=DEFAULT_MODEL)

    pics = sub.add_parser("look", help="사진으로 확인한다. 근거로만 쓰고 생성에 안 넣는다")
    pics.add_argument("question")
    pics.add_argument("--out", type=Path, required=True)
    pics.add_argument("--count", type=int, default=4)
    pics.add_argument("--model", default=DEFAULT_MODEL)

    many = sub.add_parser("batch", help="질문 목록 JSON 을 한 번에")
    many.add_argument("questions", type=Path)
    many.add_argument("--out", type=Path, required=True)
    many.add_argument("--model", default=DEFAULT_MODEL)

    listing = sub.add_parser("list")
    listing.add_argument("--out", type=Path, required=True)

    args = parser.parse_args()

    if args.command == "list":
        have = load_all(args.out)
        print(json.dumps({eid: {"question": e["question"], "asked_at": e["asked_at"],
                                "citations": len(e["citations"])}
                          for eid, e in have.items()}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "look":
        evidence = look(args.question, args.out, args.count, args.model)
        record(evidence, args.out)
        kept = sum(1 for i in evidence.images if i.get("ok"))
        print(json.dumps({"evidence_id": evidence.evidence_id,
                          "searches": evidence.searches,
                          "urls": len(evidence.images), "downloaded": kept,
                          "failed": [i["url"] for i in evidence.images if not i.get("ok")]},
                         ensure_ascii=False, indent=2))
        return 0

    questions = [args.question] if args.command == "ask" else \
        json.loads(args.questions.read_text(encoding="utf-8"))
    written = []
    for question in questions:
        evidence = ask(question, args.model)
        path = record(evidence, args.out)
        written.append({"evidence_id": evidence.evidence_id, "path": str(path),
                        "searches": evidence.searches,
                        "citations": len(evidence.citations)})
        print(f"{evidence.evidence_id}: 검색 {evidence.searches}회, 인용 {len(evidence.citations)}건",
              flush=True)
    print(json.dumps(written, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
