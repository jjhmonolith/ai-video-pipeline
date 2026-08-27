"""QA, blind and serve the H3 stage-04 follow-up experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .h3_followup_experiment import EXPERIMENT_ID


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _attempt(project_root: Path, topic: str) -> Path:
    return project_root / "runs" / topic / "attempts" / "v1-pilot"


def _root(project_root: Path, topic: str) -> Path:
    return (_attempt(project_root, topic) / "06-motion" / "qa" /
            "experiments" / EXPERIMENT_ID)


def _probe(path: Path) -> dict:
    command = [
        "ffprobe", "-v", "error", "-show_entries",
        "stream=index,codec_type,codec_name,width,height,r_frame_rate,nb_frames:format=duration,size",
        "-of", "json", str(path),
    ]
    return json.loads(subprocess.run(command, check=True, capture_output=True, text=True).stdout)


def _mute_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-i", str(source),
        "-map", "0:v:0", "-c:v", "copy", "-an", str(destination),
    ], check=True)


def _extract(video: Path, destination: Path) -> list[str]:
    destination.mkdir(parents=True, exist_ok=True)
    for old in destination.glob("*.jpg"):
        old.unlink()
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-i", str(video),
        "-vf", "select=eq(n\\,0)+eq(n\\,31)+eq(n\\,62)+eq(n\\,93)+eq(n\\,123)",
        "-vsync", "0", "-q:v", "2", str(destination / "%02d.jpg"),
    ], check=True)
    return [str(path) for path in sorted(destination.glob("*.jpg"))]


def _extract_dense(video: Path, destination: Path) -> list[str]:
    """Extract a blind, near-10-frame cadence packet for semantic AI review."""
    destination.mkdir(parents=True, exist_ok=True)
    for old in destination.glob("*.jpg"):
        old.unlink()
    frames = [*range(0, 121, 10), 123]
    expression = "+".join(f"eq(n\\,{frame})" for frame in frames)
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-i", str(video),
        "-vf", f"select={expression}", "-vsync", "0", "-q:v", "2",
        str(destination / "%02d.jpg"),
    ], check=True)
    found = [str(path) for path in sorted(destination.glob("*.jpg"))]
    if len(found) != len(frames):
        raise RuntimeError(f"dense AI sample expected {len(frames)} frames: {video}")
    return found


def _font(size: int) -> ImageFont.ImageFont:
    for path in ("/System/Library/Fonts/AppleSDGothicNeo.ttc",
                 "/System/Library/Fonts/Supplemental/Arial.ttf"):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _contact_sheet(records: list[dict], target: Path) -> Path:
    frame_w, frame_h, label_h = 160, 280, 38
    canvas = Image.new("RGB", (frame_w * 5, (frame_h + label_h) * len(records)), "#111")
    draw = ImageDraw.Draw(canvas)
    font = _font(16)
    for row, record in enumerate(records):
        y = row * (frame_h + label_h)
        draw.text((8, y + 8), record["record_id"], font=font, fill="white")
        for column, frame in enumerate(record["sample_frames"]):
            image = Image.open(frame).convert("RGB")
            image.thumbnail((frame_w, frame_h), Image.Resampling.LANCZOS)
            tile = Image.new("RGB", (frame_w, frame_h), "#000")
            tile.paste(image, ((frame_w - image.width) // 2, (frame_h - image.height) // 2))
            canvas.paste(tile, (column * frame_w, y + label_h))
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(target, quality=90)
    return target


def _dense_contact_sheet(records: list[dict], target: Path) -> Path:
    frame_w, frame_h, label_h = 112, 196, 34
    columns = max((len(item["sample_frames"]) for item in records), default=1)
    canvas = Image.new("RGB", (frame_w * columns, (frame_h + label_h) * len(records)), "#111")
    draw = ImageDraw.Draw(canvas)
    font = _font(15)
    for row, record in enumerate(records):
        y = row * (frame_h + label_h)
        draw.text((8, y + 7), f"후보 {record['candidate']}", font=font, fill="white")
        for column, frame in enumerate(record["sample_frames"]):
            image = Image.open(frame).convert("RGB")
            image.thumbnail((frame_w, frame_h), Image.Resampling.LANCZOS)
            tile = Image.new("RGB", (frame_w, frame_h), "#000")
            tile.paste(image, ((frame_w - image.width) // 2, (frame_h - image.height) // 2))
            canvas.paste(tile, (column * frame_w, y + label_h))
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(target, quality=92)
    return target


def _find_video(record: dict) -> Path:
    found = sorted(Path(record["output_dir"]).glob("*.mp4"))
    if len(found) != 1:
        raise RuntimeError(f"exactly one mp4 required for {record['record_id']}: {found}")
    return found[0]


def automatic_qa(project_root: Path, phase: str = "all") -> dict:
    project_root = project_root.resolve()
    reports = {}
    for topic in ("luxury-penthouse-tour", "sky-village-plumber"):
        root = _root(project_root, topic)
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        records = [item for item in manifest["records"]
                   if phase == "all" or item["phase"] == phase]
        qa_records = []
        for record in records:
            video = _find_video(record)
            probe = _probe(video)
            streams = probe.get("streams") or []
            stream = next(item for item in streams if item.get("codec_type") == "video")
            frames = _extract(video, root / "qa" / "frames" / record["record_id"])
            qa_records.append({
                "record_id": record["record_id"], "phase": record["phase"],
                "video": str(video), "probe": probe,
                "format_ok": (
                    int(stream.get("width", 0)) == int(record["width"])
                    and int(stream.get("height", 0)) == int(record["height"])
                    and stream.get("r_frame_rate") == "24/1"
                    and int(stream.get("nb_frames", 0)) == 124
                    and len(frames) == 5
                ),
                "audio_present_original": any(
                    item.get("codec_type") == "audio" for item in streams),
                "sample_frames": frames,
            })
        report = {
            "schema_version": "h3-followup-automatic-qa.v1", "created_at": _now(),
            "experiment_id": EXPERIMENT_ID, "topic": topic, "phase": phase,
            "records": qa_records,
            "all_format_ok": bool(qa_records) and all(item["format_ok"] for item in qa_records),
            "audio_policy": "original H3 audio is measured but removed from every blind copy",
        }
        contact_sheet = _contact_sheet(qa_records, root / "qa" / f"contact-sheet-{phase}.jpg")
        report["contact_sheet"] = str(contact_sheet)
        target = root / "qa" / f"automatic-qa-{phase}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        reports[topic] = report
    return reports


def _code(index: int) -> str:
    return chr(ord("A") + index)


def _blind_group(records: list[dict], group_id: str) -> tuple[list[dict], dict[str, str]]:
    ordered = sorted(records, key=lambda item: hashlib.sha256(
        f"{EXPERIMENT_ID}:{group_id}:{item['record_id']}".encode()).hexdigest())
    mapping = {_code(index): item["record_id"] for index, item in enumerate(ordered)}
    return ordered, mapping


def _html(page_id: str, title: str, groups: list[dict]) -> str:
    public = json.dumps({"page_id": page_id, "groups": groups}, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
:root{{--bg:#111418;--panel:#1c2229;--line:#34404c;--text:#eef3f7;--muted:#aeb9c3;--accent:#69b9ff;--ok:#69d196}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);font:16px system-ui,sans-serif}}
main{{max-width:1500px;margin:auto;padding:28px}} h1{{margin:0 0 8px}} .notice{{color:var(--muted);margin:0 0 28px}}
.group{{margin:38px 0 58px}} .criteria{{white-space:pre-line;color:#d3dde5;background:#17202a;border-left:4px solid var(--accent);padding:14px 16px;border-radius:8px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:22px;margin-top:22px}}
.card,.overall{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:15px}}
.card h3{{margin:0 0 10px}} video{{width:100%;max-height:70vh;background:#000;border-radius:8px}}
.watch{{display:inline-block;margin-top:8px;padding:5px 8px;border-radius:999px;background:#3a2c20;color:#ffd59b;font-size:13px}} .watch.done{{background:#173c2b;color:#aef0c9}}
label{{display:block;margin-top:12px;color:#dbe4eb}} textarea,input,select{{width:100%;margin-top:6px;background:#0e1216;color:var(--text);border:1px solid #465463;border-radius:7px;padding:10px;font:inherit}}
textarea{{min-height:92px;resize:vertical}} .issues{{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}} .issues label{{display:flex;gap:6px;align-items:center;margin:0;background:#111820;padding:7px 9px;border-radius:7px;font-size:14px}} .issues input{{width:auto;margin:0}}
.overall{{margin-top:24px;border-color:#54718b}} .row{{display:grid;grid-template-columns:1fr 1fr;gap:15px}}
.actions{{position:sticky;bottom:0;background:#111418ee;border-top:1px solid var(--line);padding:14px;display:flex;gap:12px;align-items:center;z-index:5}}
button{{background:var(--accent);color:#07121c;border:0;border-radius:8px;padding:11px 16px;font-weight:700;cursor:pointer}} button.secondary{{background:#364554;color:white}} #save-status{{color:var(--muted)}}
@media(max-width:700px){{main{{padding:16px}}.row{{grid-template-columns:1fr}}}}
</style></head><body><main>
<h1>{title}</h1><p class="notice">모든 영상은 무음입니다. 조건은 숨겨져 있습니다. 영상을 끝까지 본 뒤 후보별 메모와 그룹 승자/순위를 작성하세요. 완주 표시는 재생 위치가 96%에 도달하면 켜집니다. 입력은 브라우저와 프로젝트 JSON에 자동 보존됩니다.</p>
<div id="app"></div></main><div class="actions"><button id="save">응답 저장</button><button class="secondary" id="download">JSON 다운로드</button><span id="save-status">입력 대기</span></div>
<script>
const spec={public}; const storageKey='h3-review:'+spec.page_id; const app=document.querySelector('#app');
function esc(s){{return String(s).replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]))}}
for(const group of spec.groups){{
 const section=document.createElement('section'); section.className='group'; section.dataset.group=group.group_id;
 section.innerHTML=`<h2>${{esc(group.title)}}</h2><div class="criteria">${{esc(group.criteria)}}</div><div class="grid"></div>`;
 const grid=section.querySelector('.grid');
 for(const c of group.candidates){{ const card=document.createElement('article'); card.className='card'; card.dataset.candidate=c.candidate;
  card.innerHTML=`<h3>후보 ${{c.candidate}}</h3><video controls loop playsinline preload="metadata" src="${{esc(c.video)}}"></video><span class="watch">미완주</span>
  <label>점수 (1–5)<select data-field="score"><option value="">선택</option>${{[1,2,3,4,5].map(n=>`<option>${{n}}</option>`).join('')}}</select></label>
  <div class="issues">${{group.issues.map(x=>`<label><input type="checkbox" data-issue="${{esc(x)}}">${{esc(x)}}</label>`).join('')}}</div>
  <label>후보별 피드백<textarea data-field="feedback" placeholder="자연스러운 점, 실패한 동작, 변형·환각 등을 구체적으로 기록"></textarea></label>`; grid.appendChild(card); }}
 const overall=document.createElement('div'); overall.className='overall'; overall.innerHTML=`<h3>그룹 최종 판정</h3><div class="row">
 <label>승자<select data-overall="winner"><option value="">선택</option><option value="no_winner">승자 없음</option>${{group.candidates.map(c=>`<option>${{c.candidate}}</option>`).join('')}}</select></label>
 <label>순위<input data-overall="ranking" placeholder="예: C > A > F 또는 공동순위"></label></div>
 <label>종합 피드백<textarea data-overall="feedback" placeholder="승자 이유와 공통 실패 패턴"></textarea></label>`; section.appendChild(overall); app.appendChild(section);
}}
function collect(){{const response={{schema_version:'h3-followup-human-response.v1',page_id:spec.page_id,saved_at:new Date().toISOString(),review_complete:false,groups:[]}};
 for(const group of spec.groups){{const section=document.querySelector(`[data-group="${{group.group_id}}"]`); const candidates=[];
  for(const card of section.querySelectorAll('.card')){{candidates.push({{candidate:card.dataset.candidate,watched:card.dataset.watched==='true',score:card.querySelector('[data-field="score"]').value||null,issues:[...card.querySelectorAll('[data-issue]:checked')].map(x=>x.dataset.issue),feedback:card.querySelector('[data-field="feedback"]').value}})}}
  response.groups.push({{group_id:group.group_id,candidates,winner:section.querySelector('[data-overall="winner"]').value||null,ranking:section.querySelector('[data-overall="ranking"]').value,feedback:section.querySelector('[data-overall="feedback"]').value}}); }} return response; }}
function refreshCompletion(){{const cards=[...document.querySelectorAll('.card')];const watched=cards.filter(x=>x.dataset.watched==='true').length;document.querySelector('#save-status').textContent=`완주 ${{watched}}/${{cards.length}} · 입력 자동 저장`;}}
function setWatched(card,value){{card.dataset.watched=value?'true':'false';const badge=card.querySelector('.watch');badge.textContent=value?'완주':'미완주';badge.classList.toggle('done',value);}}
function apply(saved){{if(!saved||!saved.groups)return; for(const group of saved.groups){{const section=document.querySelector(`[data-group="${{group.group_id}}"]`);if(!section)continue;
 for(const c of group.candidates||[]){{const card=section.querySelector(`[data-candidate="${{c.candidate}}"]`);if(!card)continue;setWatched(card,Boolean(c.watched));card.querySelector('[data-field="score"]').value=c.score||'';card.querySelector('[data-field="feedback"]').value=c.feedback||'';for(const x of card.querySelectorAll('[data-issue]'))x.checked=(c.issues||[]).includes(x.dataset.issue);}}
 section.querySelector('[data-overall="winner"]').value=group.winner||'';section.querySelector('[data-overall="ranking"]').value=group.ranking||'';section.querySelector('[data-overall="feedback"]').value=group.feedback||'';}}}}
let timer; function localSave(){{const data=collect();localStorage.setItem(storageKey,JSON.stringify(data));refreshCompletion();clearTimeout(timer);timer=setTimeout(apiSave,900)}}
async function apiSave(){{const status=document.querySelector('#save-status');const data=collect();data.review_complete=data.groups.every(g=>g.winner&&g.candidates.every(c=>c.watched&&c.score));try{{const r=await fetch('/api/save-review',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(data)}});if(!r.ok)throw Error(await r.text());const j=await r.json();status.textContent=(data.review_complete?'평가 완료 · ':'부분 저장 · ')+j.saved_at;}}catch(e){{status.textContent='프로젝트 저장 실패—JSON 다운로드 사용 · '+e.message;}}}}
document.addEventListener('input',localSave);document.querySelector('#save').onclick=apiSave;document.querySelector('#download').onclick=()=>{{const blob=new Blob([JSON.stringify(collect(),null,2)],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=spec.page_id+'-human-review-response.json';a.click();URL.revokeObjectURL(a.href)}};
for(const video of document.querySelectorAll('video')){{const card=video.closest('.card');setWatched(card,false);video.addEventListener('timeupdate',()=>{{if(video.duration&&video.currentTime/video.duration>=.96&&card.dataset.watched!=='true'){{setWatched(card,true);localSave();}}}})}}
(async()=>{{let saved=null;try{{saved=JSON.parse(localStorage.getItem(storageKey)||'null')}}catch(e){{}};if(!saved){{try{{const r=await fetch('human-review-response.json',{{cache:'no-store'}});if(r.ok)saved=await r.json();}}catch(e){{}}}}apply(saved);refreshCompletion();}})();
</script></body></html>"""


def build_blind_review(project_root: Path) -> dict:
    project_root = project_root.resolve()
    automatic_qa(project_root, "all")
    outputs = {}
    page_specs = {
        "luxury-penthouse-tour": [{
            "group_id": "L1", "title": "펜트하우스 · 호스트 이동",
            "criteria": (
                "요청: 팔을 내리고 몸 전체를 실내로 돌린 뒤 자연스럽게 세 걸음 이동, "
                "계속 등을 보이고 팔은 내린 상태.\n평가: 회전·보행 방향, 팔 동작, 되돌아보기/재제스처, "
                "카메라 추종 자연스러움, 건축·조명·인물 안정성."
            ),
            "issues": ["역방향/뒷걸음", "재제스처", "부자연스러운 카메라", "인물 변형",
                       "공간/가구 변형", "조명 깜빡임", "새 사람/장비"],
            "filter": lambda r: True,
        }],
        "sky-village-plumber": [
            {
                "group_id": "M1-seat", "title": "배관공 · 렌치 안착",
                "criteria": (
                    "요청: 렌치를 짧게 이동해 양쪽 턱을 커플링에 완전히 안착하고 정지. 회전 금지.\n"
                    "평가: 정확한 대상, 양쪽 턱 접촉, 손–도구–관 관통, 고정부·도구 정체성, 물/객체 환각."
                ),
                "issues": ["잘못된 대상", "한쪽 턱/접촉 실패", "관통", "도구 변형/소실",
                           "고정부 변형", "물 분출", "새 객체/팔다리"],
                "filter": lambda r: r["factors"]["task"] == "seat_wrench",
            },
            {
                "group_id": "M1-turn", "title": "배관공 · 커플링 소회전",
                "criteria": (
                    "요청: 이미 안착된 렌치를 작은 호로 당겨 커플링만 약 15도 회전하고 정지.\n"
                    "평가: 접촉 유지, 작은 단일 회전, 인접 관 고정, 관통, 도구·커플링·물 환각."
                ),
                "issues": ["접촉 이탈", "회전 없음/과다", "인접 관 이동", "관통",
                           "도구 변형/소실", "물 분출", "새 객체/팔다리"],
                "filter": lambda r: r["factors"]["task"] == "turn_coupling",
            },
        ],
    }
    for topic, group_defs in page_specs.items():
        root = _root(project_root, topic)
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        comparison = root / "comparison"
        groups, key = [], {}
        for group_def in group_defs:
            selected = [record for record in manifest["records"] if group_def["filter"](record)]
            ordered, mapping = _blind_group(selected, group_def["group_id"])
            key[group_def["group_id"]] = mapping
            candidates = []
            for index, record in enumerate(ordered):
                code = _code(index)
                target = comparison / "blind-clips" / group_def["group_id"] / f"{code}.mp4"
                _mute_copy(_find_video(record), target)
                blind_probe = _probe(target)
                if any(s.get("codec_type") == "audio" for s in blind_probe.get("streams") or []):
                    raise RuntimeError(f"blind clip still has audio: {target}")
                candidates.append({"candidate": code,
                                   "video": f"blind-clips/{group_def['group_id']}/{code}.mp4"})
            groups.append({"group_id": group_def["group_id"], "title": group_def["title"],
                           "criteria": group_def["criteria"], "issues": group_def["issues"],
                           "candidates": candidates})
        comparison.mkdir(parents=True, exist_ok=True)
        title = ("H3 블라인드 테스트 · 펜트하우스" if topic == "luxury-penthouse-tour"
                 else "H3 블라인드 테스트 · 배관공")
        html_path = comparison / "blind-review.html"
        html_path.write_text(_html(topic, title, groups), encoding="utf-8")
        (comparison / "blind-key.json").write_text(json.dumps({
            "schema_version": "h3-followup-blind-key.v1", "created_at": _now(),
            "do_not_show_before_human_review": True, "mapping": key,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        (comparison / "review-spec.json").write_text(json.dumps({
            "schema_version": "h3-followup-review-spec.v1", "page_id": topic,
            "audio_excluded": True, "groups": groups,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        response_path = comparison / "human-review-response.json"
        if not response_path.exists():
            response_path.write_text(json.dumps({
                "schema_version": "h3-followup-human-response.v1", "page_id": topic,
                "saved_at": None, "groups": [],
            }, ensure_ascii=False, indent=2), encoding="utf-8")
        outputs[topic] = {"html": str(html_path), "response": str(response_path),
                          "groups": len(groups),
                          "candidates": sum(len(group["candidates"]) for group in groups)}
    return outputs


def build_ai_sampling_packet(project_root: Path) -> dict:
    """Build an opaque dense-frame packet; it contains no condition key."""
    project_root = project_root.resolve()
    outputs = {}
    for topic in ("luxury-penthouse-tour", "sky-village-plumber"):
        comparison = _root(project_root, topic) / "comparison"
        spec_path = comparison / "review-spec.json"
        if not spec_path.is_file():
            raise RuntimeError(f"build the blind review first: {spec_path}")
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        packet_groups = []
        for group in spec["groups"]:
            sampled = []
            for candidate in group["candidates"]:
                video = comparison / candidate["video"]
                frames = _extract_dense(
                    video, comparison / "ai-review" / "frames" /
                    group["group_id"] / candidate["candidate"])
                sampled.append({"candidate": candidate["candidate"], "sample_frames": frames})
            contact = _dense_contact_sheet(
                sampled, comparison / "ai-review" /
                f"contact-sheet-{group['group_id']}.jpg")
            packet_groups.append({
                "group_id": group["group_id"], "title": group["title"],
                "criteria": group["criteria"], "issues": group["issues"],
                "candidates": [item["candidate"] for item in sampled],
                "sample_frame_count": len(sampled[0]["sample_frames"]) if sampled else 0,
                "contact_sheet": str(contact),
            })
        packet = {
            "schema_version": "h3-followup-ai-review-packet.v1",
            "created_at": _now(), "experiment_id": EXPERIMENT_ID,
            "page_id": topic, "blind": True, "condition_key_included": False,
            "audio_excluded": True, "review_method": "14 frames at n=0,10,...,120,123",
            "groups": packet_groups,
        }
        packet_path = comparison / "ai-review" / "packet.json"
        packet_path.parent.mkdir(parents=True, exist_ok=True)
        packet_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
        outputs[topic] = {"packet": str(packet_path), "groups": packet_groups}
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description="QA and blind the H3 follow-up experiment")
    parser.add_argument("project_root", type=Path)
    parser.add_argument("--qa-phase", choices=["pilot", "main", "all"])
    parser.add_argument("--build-blind", action="store_true")
    parser.add_argument("--build-ai-packet", action="store_true")
    args = parser.parse_args()
    if args.build_ai_packet:
        result = build_ai_sampling_packet(args.project_root)
    elif args.build_blind:
        result = build_blind_review(args.project_root)
    else:
        result = automatic_qa(args.project_root, args.qa_phase or "all")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
