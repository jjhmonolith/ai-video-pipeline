# 5단계 production 실행

`src/ai_video_pipeline/stage5.py`가 `04-shot-design/output/shot-cards.json`을
실제 시작판과 조건부 상호작용 설명서로 전환한다. 이미지 생성은 Codex 내장
ImageGen이 담당하고 Python runner는 작업 명세, 입력 해시, 픽셀 검증, 모드별 승인,
영수증과 H3 handoff를 담당한다.

## 실행 순서

1. `--audit`으로 계약, 1단계 승인, direction 영향, 2단계 의미 승인, 4단계
   프롬프트와 모든 reference hash를 검사한다.
2. 4단계가 요구한 interaction manual 또는 3단계 reference debt가 있으면
   `--prepare references`로 5A를 먼저 실행한다. `--prepare manuals`는 이전 자동화용
   별칭이다. `BLOCKED DRAFT` 프롬프트는 production 입력이 아니다.
3. finalize가 clean board와 deterministic annotated QA board, AI preflight
   packet을 만든다. AI가 기준을 통과시킨 manual은 자동 승격하며, 실패 시 최대
   10회까지 서로 다른 실패 기준 변주로 순차 재생성한다.
4. 모든 필수 신규 reference가 승인된 뒤 `--prepare plates`가 기존 2단계 시트와
   새 reference를 합친 전역 reference preflight 명세와 샷별 시작판 작업을 만든다.
5. 모든 고유 reference image를 먼저 시각 검수하고
   `--record-reference-review`로 기록한다. 하나라도 실패하거나 미검수이면 어떤
   시작판도 생성할 수 없다.
6. 전역 reference 장벽이 통과하면 샷마다 시작판 한 장을 생성하고, 승인된
   reference들을 다시 함께 보며 AI가 시작 상태와 reference 일치성을 검수한다.
   실패한 경우에만 같은 구조화 프롬프트에 보정문을 붙여 다음 한 장을 생성한다.
   최대 10회이며 모두 실패하면 10회차를 유지한다.
7. `normal`은 사람이 AI가 고른 단일 후보와 기준을 승인한다. 명시적
   `fast_track`은 AI가 같은 packet을 증거와 함께 판정·적용한다. 10회차의 남은
   비안전 품질 실패는 이 모드에서만 `accepted_defect`로 기록할 수 있다. 화면 이동이
   있는 샷은 선택한 시작판 위에서 정규화 start/end 좌표, 방향 벡터와 depth intent도
   기록한다.
8. 승인본만 `output/plates/`로 승격된다. 전 샷이 승인되면
   `output/h3-conditioning.json`이 `ready: true`가 된다.

Production에서는 end plate를 생성하지 않으며 H3 `last_plate`는 항상 `null`이다.

## 보편 렌더 계약

5단계 runner는 manual과 plate의 모든 ImageGen 작업에
`stage5-universal-render.v2` 계약을 자동으로 덧붙인다. 이 계약은 주제와 관계없이
중력·지지·균형, 접촉과 관절, 강체 형상과 부품 수, 원근·가림·반사, 재질 반응,
광원과 그림자의 물리적 일치를 요구하고 부유·관통·융합·복제·고스트·한 이미지 안의
시간 혼합을 금지한다.

보편 계약은 구체적인 미술 결정을 새로 만들지 않는다. 시각·태양 방향·그림자 경도처럼
4단계가 전달한 컷별 계약이 더 구체적일 때는 그것이 우선한다. 계약 버전과 프롬프트
해시는 prompt pack, Codex job, manifest에 함께 기록되며 finalize 때 다시 검증된다.

## 명령

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m ai_video_pipeline.stage5 \
  runs/luxury-penthouse-tour/attempts/v2 --audit

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m ai_video_pipeline.stage5 \
  runs/luxury-penthouse-tour/attempts/v2 --prepare plates

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m ai_video_pipeline.stage5 \
  runs/luxury-penthouse-tour/attempts/v2 \
  --record-reference-review <manifest.json> --review-file <reference-review.json>

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m ai_video_pipeline.stage5 \
  runs/luxury-penthouse-tour/attempts/v2 \
  --record-ai-review <manifest.json> --review-file <attempt-review.json>

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m ai_video_pipeline.stage5 \
  runs/luxury-penthouse-tour/attempts/v2 \
  --finalize-manifest <manifest.json> --codex-surface desktop

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m ai_video_pipeline.stage5 \
  runs/luxury-penthouse-tour/attempts/v2 --apply-review <review.json>
```

대화형 생성은 `.agents/skills/plate-imagegen/SKILL.md`를 사용한다. 스킬은 먼저
reference 검수 wave를 완료한 뒤 시작판 생성 wave를 실행하고, manifest의 프롬프트와
reference 순서를 바꾸지 않는다. 최종 packet은 normal에서 사람이, fast-track에서
AI가 완성한다.

3–6단계 전체 시간·reference·take 계약은
`docs/design/stage3-stage6-production-contract.md`가 소유한다.

## 주요 산출물

```text
05-plate/
  prompts/production/          실제 생성 프롬프트와 reference 결속
  qa/codex/manifests/          Codex ImageGen 작업 명세
  qa/codex/candidates/         수정 전 원본
  qa/manual-candidates/        검증된 설명서 후보
  qa/plate-candidates/         검증된 시작판 후보
  qa/reviews/                  실행 모드에 따라 사람 또는 AI가 완성하는 승인 packet
  output/manuals/              승인된 clean interaction manual
  output/plates/               승인된 첫 프레임
  output/h3-conditioning.json  first-only 6단계 handoff
  receipt.json                 승인된 asset과 생성·검수 증거
```

## 펜트하우스 v2 현재 상태

`luxury-penthouse-tour/attempts/v2`에는 9개 시작판 프롬프트와 필요한 2단계
시트가 모두 있다. 2단계 semantic review도 승인되었고 interaction manual은 필요하지
않다. 현재 production 차단 조건은 `host-minchae`와 `lumen-penthouse`의 1단계 사람
승인 기록이 비어 있다는 한 가지다. runner는 이 승인을 추정하거나 자동 기록하지 않는다.
