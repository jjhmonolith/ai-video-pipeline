# AI Video Pipeline

계약이 단계·해상도·금지선·검수 조건을 정하고, 각 제작 단계가 그 계약을 읽어 실행하는 AI 영상 제작 파이프라인이다.

## 현재 상태

- 현행 레이아웃: 8단계 `v2`
- 기능 구현: `01-premise`–`04-shot-design`, human-gated `05-plate` production runner
- 현행 런 완료: `01-premise`–`04-shot-design` 설계. 4단계는 보조 상호작용 시트 필요성·패널·생성 프롬프트까지 산출
- 다음 실행: `luxury-penthouse-tour/attempts/v2`의 1단계 사람 승인 뒤 정식 `05-plate` 시작판 후보 생성·선발과 H3-only `06-motion` 카나리아
- 현행 검증 런: `runs/sky-village-plumber/attempts/v1-pilot`
- 기준 문서: `docs/pipeline-v2-handoff.md`
- 코드 기준: `src/ai_video_pipeline/run_layout.py`
- 시트 생성 표면: Codex 앱·Codex CLI 공용 `sheet-imagegen` 스킬과 `--generator codex`

이전 9~10단계 파이프라인, 완결·중단된 제작 런, 감사 보고서와 즉석 렌더는 `archive/`에 보존한다. 삭제하지 않았으며 원래 폴더 구조를 유지해 비교·재현 자료로 읽을 수 있다.

## 기준의 우선순위

1. `src/ai_video_pipeline/run_layout.py`: 현행 단계와 디스크 규약
2. `<attempt>/01-premise/output/contract.json`: 해당 시도에 실제로 적용되는 생성·납품 제작 계약
3. `contracts/human-gates.v1.json`: 사람이 승인해야 하는 판단 계약
4. `docs/governance/operating-rules.md`: 보존·승인·산출물 운영 규정
5. `docs/pipeline-v2-handoff.md`: 현재 구현의 인수인계와 다음 작업
6. `research/`, `docs/research/`, `archive/`: 근거와 과거 기록. 현행 규약을 덮어쓰지 않는다

계약과 문서가 충돌하면 실행 코드와 해당 attempt의 계약을 먼저 고치고, 문서를 그 결과에 맞춘다. 도구 안에 프레임 크기나 금지 문구를 다시 복사하지 않는다.

로컬 MiniMax H3 생성 프레임은 가로 `1344×768` 또는 세로 `768×1344`, `24fps`다. YouTube 등 플랫폼의 최종 업로드 해상도는 생성 프레임을 덮어쓰지 않고 계약의 `delivery_frame`과 명시적 편집 변환으로 분리한다.

레퍼런스 시트는 Codex 앱·CLI에서 관측된 네이티브 래스터인 가로 `1672×941` 또는 세로 `941×1672`와 `high`를 계약한다. API 경로는 지원되는 상위 크기로 생성한 뒤 이 크기로 축소할 수 있다. 판은 시트 크기를 상속하지 않고 계약의 영상 `frame`과 가장 가까운 공급자 크기로 요청해 정확한 영상 프레임으로 축소한다. 어떤 역할도 작은 원본을 확대해 계약 크기인 것처럼 기록하지 않는다.

## 현행 파이프라인

| 단계 | 질문 | 주요 산출물 |
|---|---|---|
| `01-premise` | 무엇을 만드는가 | 방향 원문, 조사 근거, 요소 정의, `contract.json` |
| `02-sheet` | 어떻게 생겼는가 | 요소별 레퍼런스 보드 |
| `03-scenario` | 무슨 일이 얼마나 일어나는가 | 막 구조, 비트, 길이 |
| `04-shot-design` | 어떻게 찍고 어떤 보조 설명이 필요한가 | shot card, 카메라, 연기, 상호작용 설명서 명세·프롬프트 |
| `05-plate` | 컷의 시작 상태와 작동 원리는 무엇인가 | 시트를 물린 시작 이미지, 조건부 상호작용 설명서 보드 |
| `06-motion` | 상태 사이가 어떻게 움직이는가 | 영상 클립 |
| `07-edit` | 어떻게 조립·표기하는가 | 리타이밍, 정보 레이어, 편집본 |
| `08-review` | 무엇이 승인 가능한가 | 자동 QA, human gate, 릴리스 판정 |

한 영상의 모든 파일은 `runs/<topic>/attempts/<attempt>/` 안에 둔다. 루트 `renders/`는 연결 시험용 임시 출력일 뿐 제작 원장이 아니다.

## 폴더

```text
src/ai_video_pipeline/   현행 실행 코드
tests/                   계약·레이아웃·런타임 테스트
contracts/               실행 계약과 design-only 참고 계약
docs/                    현행 설계·운영·인수인계
research/                아직 규약으로 승격하지 않은 조사
runs/                    진행 중인 현행 제작 런만
renders/                 임시 런타임 출력
archive/                 과거 런·보고서·설계·렌더·도구
```

자세한 파일 배치와 보존 규칙은 `docs/design/run-layout.md`, 아카이브 목록은 `archive/README.md`에 있다.

## Codex에서 2단계 이미지 생성

Codex 앱과 Codex CLI는 같은 프로젝트 스킬 `.agents/skills/sheet-imagegen/SKILL.md`를 읽는다. 두 표면 모두 공식 composer가 `WRITER_RULES + 계약 sheet policy + kind spec + 요소 정의 + 적용 조항`으로 만든 `sheet-prompt-pack.v2`만 허용한다. 각 입력과 전체 메타 프롬프트는 해시로 결박되며, 누락·구형·수기 prompt pack은 ImageGen 전에 차단된다. 유효한 pack과 manifest가 결박한 계약 크기/high 요청문을 그대로 렌더하고 같은 `sheet-receipt.v2` 영수증을 만든다. ImageGen 단계는 별도 `OPENAI_API_KEY`를 쓰지 않는다.

- Codex 앱: `sheet-imagegen`으로 특정 attempt의 2단계 시트를 생성해 달라고 요청한다.
- Codex CLI: 프로젝트 루트에서 대화형 `codex`를 열고 `$sheet-imagegen`을 호출한다.
- 정식 시트 요청은 가로 `1672×941`, 세로 `941×1672`, `high`다. 더 작은 원본이 반환되면 후보로 보존하고 채택·확대하지 않는다.
- 기존 채택본은 기본적으로 건너뛴다. 교체를 명시한 경우에만 `--force`를 쓰며 이전 파일은 `02-sheet/rejected/`로 이동한다.
- 대량·무인 배치와 CI는 Codex 직접 생성 범위가 아니다. 필요할 때만 `--generator api`를 별도로 선택한다.

세부 명령과 영수증 필드는 `docs/design/codex-image-generation.md`에 있다.

## Codex에서 5단계 시작판 생성

`adaptive-generation-harness.v1`은 정의·구조화 프롬프트·시트·시나리오·샷 설계·interaction manual·plate를 모두 한 장/한 결과씩 생성하고 즉시 검증한다. 실패하면 원본 계약과 provenance를 유지한 채 실패 기준을 다음 프롬프트에 넣고, 시도마다 다른 복구 전략으로 최대 10회까지 계속한다. stale manifest, 생성 파생물 누락, 의미 검수 실패와 큰 픽셀 오차는 자동으로 소유 단계에 돌아가 재생성한다.

실행 모드는 attempt 단위다. 기록이 없으면 항상 `normal`이며 기존 중간 사람 승인 지점을 유지한다. 사용자가 해당 attempt에 패스트트랙을 명시한 경우에만 `fast_track`을 기록하고, AI가 내부 검수 패킷을 판정·적용해 단계 사이에서 멈추지 않는다. 10회차에도 남은 비안전 품질 실패는 `accepted_defect`로 증거와 함께 남기고 계속한다. 패스트트랙은 외부 게시·메시지·구매·권한 상승이나 안전 경계 우회를 허가하지 않는다.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m ai_video_pipeline.execution_mode ATTEMPT show
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m ai_video_pipeline.execution_mode \
  ATTEMPT set fast_track --by user --reason "사용자의 명시적 패스트트랙 요청"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m ai_video_pipeline.execution_mode \
  ATTEMPT set normal --by user --reason "일반 검토 모드로 복귀"
```

`plate-imagegen` 스킬과 `ai-video-stage5` runner가 4단계 shot card를 정식 5단계 작업으로 실행한다. 입력 감사가 통과하면 필수 상호작용 설명서를 먼저 생성해 AI preflight로 승격한다. Plate manifest의 모든 고유 레퍼런스는 시작 이미지보다 먼저 검수되어야 하며, 전부 통과한 뒤 샷마다 한 장을 만들고 같은 레퍼런스와 비교 검수한다. 실패한 경우에만 최대 10회까지 서로 다르게 변주하며 순차 재생성한다. Normal은 10회차와 AI 선택본을 사람 검토 대상으로 사용하고, fast-track은 mode-bound AI review packet을 자동 적용한다. Production은 끝 이미지를 만들지 않는다.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m ai_video_pipeline.stage5 \
  runs/luxury-penthouse-tour/attempts/v2 --audit
```

세부 절차와 파일 계약은 `docs/design/stage5-production.md`에 있다.

## 확인 명령

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m ai_video_pipeline.run_layout runs/sky-village-plumber
PYTHONPATH=src python3 -m ai_video_pipeline.contract show \
  runs/sky-village-plumber/attempts/v1-pilot
PYTHONPATH=src python3 -m ai_video_pipeline.premise report \
  runs/sky-village-plumber/attempts/v1-pilot
PYTHONPATH=src python3 -m ai_video_pipeline.contract_gate \
  runs/sky-village-plumber/attempts/v1-pilot
PYTHONPATH=src python3 -m ai_video_pipeline.shot_design \
  runs/sky-village-plumber/attempts/v1-pilot --audit-only
```

단계 그래프:

```bash
PYTHONPATH=src python3 -m ai_video_pipeline.graph_dashboard \
  runs/sky-village-plumber
```

게이트 계약 예제:

```bash
uv run --project . --no-editable ai-video-gates resolve examples/g3-performance-event.json
uv run --project . --no-editable ai-video-gates validate-packet examples/g7-pacing-review.json
uv run --project . --no-editable ai-video-gates validate-feedback examples/g7-feedback-delta.json
```

## 제작 원칙

- 생성모델은 장면과 레퍼런스를 만들고, 이름·수치·라벨·지도·읽히는 문자는 결정론적 편집 레이어가 그린다.
- 실제 인물의 likeness를 생성하지 않는다. 익명 재현이 필요한 경우 결과물에 재현 고지를 남긴다.
- 형식 검증, 사람 승인, 공개 가능 여부는 각각 `form_ok`, `human_approved`, `release_eligible`이다. 미승인 2·3단계는 `draft_unapproved`로만 진행한다.
- 프롬프트, 입력 해시, 생성 표면, 모델·파라미터, 결과 경로를 `receipt.json`에 남긴다. Codex 직접 생성은 API 토큰 수치 대신 Codex 사용량 계정과 `token_detail: not-exposed`를 기록한다.
- 최종 공개는 관련 human gate가 완료되고 `08-review`가 릴리스 가능으로 판정한 뒤에만 한다.

## 구현 경계

구현됨:

- attempt 계약 로더, 검증, digest와 receipt block
- 조사·요소 정의·레퍼런스 시트·시나리오의 계약 기반 실행
- H3-only shot card 컴파일, 원자 동작 경고, first-only 상태·불변/허용 변화, plate/H3 후보 정책
- 관련 2단계 전체 시트 필수 결속, 상호작용 설명서 필요성 판정, 6패널 다각도·다상태 명세와 5단계 이미지 생성 프롬프트
- 고정 1–3단계 기반 M1–M4 4단계 비교와 5단계 이미지 카나리아 패킷
- 전 단계 공통 검증·복구 하네스, 시도별 프롬프트 변주, 산출물당 최대 10회 자동 재시도
- 5단계 입력 감사, 설명서 우선 실행, 전역 레퍼런스 검수 장벽, 시작판 단일 생성·최대 10회 순차 재시도, mode-bound 승인, 영수증과 H3 first-only handoff
- Codex 앱·CLI 공용 시트 ImageGen 작업 명세, 결과 확정, `sheet-receipt.v2`
- G1–G10 human gate routing, 기본 normal 사람 승인, 명시적 fast-track AI 판정
- MiniMax H3 t2v, first/last frame anchoring, guide, 결과 회수
- 단계 레이아웃 검사와 실제 읽기·쓰기 기반 그래프

미구현 또는 미연결:

- 승인된 `05-plate` 결과를 사용하는 `06-motion`부터 `08-review`까지의 현행 end-to-end 실행
- 4단계 이후까지 이어지는 통합 production ledger (1단계 field decision ledger는 구현됨)
- gate와 생성 런타임의 단일 오케스트레이션
- 사운드 제작·검수 전체
- 배포 어댑터와 승인된 정보 그래픽 미술 방향

강아지 배관공과 펜트하우스의 v1은 과거 receipt와 제작물을 보존하는 회귀 fixture다. 새 제작은 Codex 네이티브 `1672×941` high 계약을 사용하며 어느 한쪽도 다른 쪽의 창작 레퍼런스가 아니다. 과거 차이는 stage별 compatibility record와 semantic QA에 남긴다. 상세 규약은 `docs/governance/stage-1-3-regression.md`를 따른다.

GPU·H3 세부 설정은 코드와 런타임 테스트를 기준으로 확인한다. 운영 호스트나 포트 같은 환경별 값은 저장소 규약으로 고정하지 않는다.
