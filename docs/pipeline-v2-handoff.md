# 새 파이프라인 인수인계 · 1~4단계까지 (legacy)

> 역사 문서: 전체 v2 기준본은 `archive/pipeline-v2-hybrid-2026-08-27/`에
> 보존되어 있다. 새 제작은 `docs/pipeline-v3/`와 단계별 스킬을 따른다.

> 보존 안내: 이 문서는 기존 `beats[].seconds` attempt를 이해하기 위한 자료다.
> v2 당시 3–6단계 정본은 `docs/design/stage3-stage6-production-contract.md`였다. 아래의
> 비트 합·고정 길이 범위·H3 best-of-N은 신규 생성 규약으로 사용하지 않는다.

> 작성: 2026-08-25
> 상태: 5단계 production runner 구현 완료. 펜트하우스 v2 시작판 생성은 1단계 사람 승인 대기
> 검증 프로젝트: `runs/luxury-penthouse-tour/attempts/v2`

---

## 0. 한 문단 요약

지시사항 한 줄을 받아 웹 조사를 하고, 인물·피사체·배경을 정의하고, 각 요소의 레퍼런스 보드를 그리고, 그 보드를 보면서 시나리오를 쓰는 데까지 자동으로 돈다. **모듈은 도메인을 모른다.** 자동차 실사와 어린이 애니메이션 두 프로젝트가 같은 코드로 돌았고 바뀐 것은 계약 파일뿐이다.

### 2026-08-25 정리 시 확인된 현행 상태

강아지 배관공 런이 현행 최신 제작물이며 1~3단계를 완료했다. 시트 생성 뒤 계약이 확장되어 2단계 영수증의 전체 digest는 이전 값이지만, 정의·프롬프트·적용 조항·이미지 계획·결과 크기를 현재 계약과 다시 대조했고 사용자가 시트 4장을 최신 산출물로 확인했다. 원래 영수증을 수정하지 않고 `02-sheet/qa/contract-compatibility.json`에 단계 한정 호환 판정을 남겼다.

---

## 1. 단계

```
01-premise      무엇인가        지시사항, 조사, 정의
02-sheet        어떻게 생겼나    레퍼런스 보드
03-scenario     무슨 일이 벌어지나  비트와 길이
04-shot-design  어떻게 찍고 무엇을 더 설명하나  shot/state/H3 + 보조 설명서 명세
05-plate        시작 컷 이미지 + 조건부 상호작용 설명서 보드
06-motion       클립
07-edit         조립
08-review       감사
```

옛 파이프라인은 9~10단계였다. 두 번 합쳤다.

**`01-brief` + `02-research` -> `01-premise`.** 브리프는 약속만 적고, 리서치는 출처 없는 주제 층 파일을 복사만 했다. 무엇을 만드는지 정하는 자리가 비어 있었다.

**`03-concept` + `04-script` -> `03-scenario`.** 무대와 조명이 배경 정의로 올라가면서 컨셉에 흐름만 남았다. 흐름과 비트 길이는 한 번의 결정이다.

**합치지 않은 것.** 시나리오와 샷 디자인은 갈라뒀다. 무슨 일이 벌어지는가와 어느 앵글에서 찍는가는 다른 질문이고, 합치면 앵글이 이야기를 정한다.

---

## 2. 계약이 전부를 정한다

`<attempt>/01-premise/output/contract.json` 하나가 프로젝트를 정의한다. **모듈에는 픽셀 값도 금지 문구도 단계 이름도 없다.**

| 계약 항목 | 정하는 것 | 모듈이 읽는 법 |
|---|---|---|
| `stages` | 역할과 단계 이름 연결 | `contract.stage_for("premise", ...)` |
| `frame` | 판·H3 모션의 네이티브 생성 크기와 fps | `contract.frame` |
| `delivery_frame` | 최종 편집 크기와 명시적 크롭·스케일 | `contract.delivery_frame`, `contract.frame_for_stage(...)` |
| `motion.runtime` | H3 런타임 프로파일과 생성 프레임 출처 | 계약 검증기와 H3 런타임이 함께 검사 |
| `image.roles` | 역할별 이미지 크기와 품질 | `contract.image_plan("plate")` |
| `sheet.kinds` | 시트 종류와 패널 구성 | `contract.sheet_plan("character")` |
| `clauses` | 단계별 금지 문구 | `contract.clause_text(stage, conditions)` |
| `subjects.declared` | 어떤 요소가 필요한가 | `contract.elements_by_kind()` |
| `scenario` | 막 구조와 리듬 | `contract.scenario_structure()` |
| `research` | 조사 질문 상한 | 상한 초과분을 잘라낸다 |

### 왜 이렇게 했나

옛 파이프라인에서 브리프가 네 가지를 금지했는데, 그 네 문장이 도구마다 `FORBIDDEN` 상수로 손으로 복사돼 있었다. 프레임은 러너에 `576, 1024`, 합성기에 `1080, 1920` 으로 따로 박혀 있었고 셋을 잇는 것이 없었다. 영상이 576x1024 로 생성돼 1.875배 확대됐고 **어느 영수증에도 그 숫자가 없었다.**

읽히지 않는 문서는 아무도 구속하지 않는다.

### 검증됨

다른 번호 체계로 실제로 돌려봤다.

```
표준        premise=01-premise    sheet=02-sheet
0부터       premise=00-intake     sheet=01-boards
단계명 다름  premise=A-foundation  sheet=B-visual
```

세 경우 모두 경로가 따라 움직였다. 프레임을 바꾸면 판 크기가 따라오고, 가로 프레임이면 API 주문도 가로로 바뀐다.

---

## 3. 1단계 · `01-premise`

### 인풋

**사람의 지시사항 한 줄.** 들어오는 선이 없다.

```bash
python3 -m ai_video_pipeline.premise direction <attempt> "..." --by user
python3 -m ai_video_pipeline.premise direction <attempt> "..." --by user --add   # 나중에 온 보충
```

`--add` 는 원문을 고치지 않고 시각과 함께 덧붙인다. 지시는 늦게 오는 일이 잦고, 어떤 작업이 어떤 지시보다 앞섰는지가 남아야 한다.

### 아웃풋

```
01-premise/output/
  direction.json      지시사항 원문과 보충
  contract.json       약속
  subjects/*.json     정의. 각각 출처를 달고
  evidence/*.json     조사 기록. 사진 질문은 하위 폴더에 이미지도
```

### 도는 방식

```bash
python3 -m ai_video_pipeline.premise research <attempt>   # 질문도 자동으로 세운다
python3 -m ai_video_pipeline.premise propose <attempt>
python3 -m ai_video_pipeline.premise report  <attempt>
```

**질문을 스스로 세운다.** 요소마다 무엇을 물을지 정하고, 글로 답할 것인지 사진으로 답할 것인지 고른다.

사진 질문이 필요한 이유가 있다. 첫 실행에서 자동차 유튜브 진행자에게 **방송용 핸드헬드 마이크**를 쥐여줬다. 그럴듯하고 실제로는 아무도 안 그런다. 실제 촬영 현장 사진을 받아보니 옷에 다는 무선 라발리에였다. 글로만 물으면 안 잡힌다.

**사진은 근거이지 생성 입력이 아니다.** 받아온 것에는 실존 상표와 인물과 번호판이 들어 있다. 생성에 물리면 결과물이 그것들을 닮는다. 정의에는 말로만 넘어간다.

### 상한

첫 실행이 질문 16개를 세워 검색 100회를 돌고 10분을 썼다. 계약에 상한을 뒀다.

```json
"research": {"max_questions": 6, "max_image_questions": 3, "images_per_question": 3}
```

질문끼리는 서로를 안 보므로 병렬로 돈다.

### 출처가 강제된다

```json
"provenance": {
  "decided_by": "gpt-5.4",
  "decided_at": "...",
  "basis": "3건의 웹 조사 결과 범위 안에서 정함",
  "considered": ["다른 요소가 이 결정을 바꿨다면 그 이유"],
  "approved_by": ""
}
```

`approved_by` 는 사람이 채우기 전까지 비어 있고 **파이프라인은 기다리지 않는다.** `form_ok` 와 `all_approved` 를 따로 보고하므로 형식이 갖춰진 것을 승인된 것으로 착각할 수 없다.

### 요소 사이 경계

인물 정의에 `scene_fit.car_paint_compatibility` 같은 필드가 생긴 적이 있다. **인물이 차를 참조한다.** 그 필드는 인물을 로드하는 모든 뒤 단계로 따라다니고, 다른 차를 요청하는 컷과 싸운다.

지금은 이렇게 갈랐다. 다른 요소를 **읽고 참고하되 기술하지 않는다.** 다른 요소가 실제로 선택을 바꿨으면 `provenance.considered` 에 한 줄 남는다. 요소들은 나중에 컷에서 만난다.

---

## 4. 2단계 · `02-sheet`

### 왜 여기 있나

시트가 옛 파이프라인에서는 5번이었다. 2번으로 올렸다.

**정의와 그림은 같은 결정의 두 반쪽이다.** 얼굴을 글로 적는 것과 그리는 것을 따로 하면 서로 흘러간다. 그리고 시나리오가 실물을 보고 써진다.

### 두 패스

```
설계 명세 + 요소 정의  ->  [텍스트 모델]  ->  영어 이미지 프롬프트
영어 프롬프트          ->  [이미지 모델]  ->  보드
```

**나눈 이유.** 디렉터용 설계 지시는 이미지 프롬프트가 아니다. 빈칸을 채울지 판단하고 고정 레이아웃을 머리에 두는 일이다. 한 패스로 하면 이미지 모델에게 계획과 그리기를 동시에 시키게 되고, 먼저 버려지는 것이 레이아웃이다.

보낸 프롬프트가 `02-sheet/prompts/*.json` 에 남는다. 보드가 틀렸을 때 추측하지 않고 문장을 열어본다.

### Codex 앱·CLI 직접 생성

두 번째 패스는 `--generator api` 또는 `--generator codex`를 선택할 수 있다. Codex 모드는 기존 프롬프트 팩으로 작업 manifest를 준비하고, 프로젝트 스킬 `sheet-imagegen`이 앱 또는 CLI의 내장 `$imagegen`을 호출한 뒤 결과를 확정한다. Python 명령 자체가 모델을 호출하지 않으며 `OPENAI_API_KEY`도 읽지 않는다.

```bash
# Codex가 읽을 작업 manifest 준비
PYTHONDONTWRITEBYTECODE=1 uv run --project . --no-editable \
  ai-video-sheets ATTEMPT --generator codex

# imagegen이 candidate를 만든 뒤 앱/CLI 표면을 구분해 확정
PYTHONDONTWRITEBYTECODE=1 uv run --project . --no-editable \
  ai-video-sheets ATTEMPT --generator codex \
  --finalize-manifest MANIFEST --codex-surface cli
```

앱과 CLI는 `.agents/skills/sheet-imagegen/SKILL.md`를 함께 사용한다. 기존 채택본은 기본적으로 건너뛰고, 명시적인 `--force` 교체 때만 이전 파일을 `rejected/`로 보낸다. 무인 배치·CI는 이 모드의 보장 범위가 아니며 API 모드를 사용한다. 세부 규약은 `docs/design/codex-image-generation.md`에 있다.

### 시트 종류 셋

명세는 `src/ai_video_pipeline/sheet_specs/*.md` 에 있다.

| 종류 | 패널 | 왜 다른가 |
|---|---|---|
| `character` | 턴어라운드 5뷰, 헤드 6뷰, 의상 분해, 재질 4, 노트, 팔레트 8, 소품 3, 표정 연구 | 얼굴을 둘러본다 |
| `subject` | 턴어라운드 5뷰, 디테일 6뷰, 부품 분해, 재질 4, 노트, 팔레트 8, 특징 3, 축척 | 형태를 둘러본다 |
| `setting` | 히어로, 컨셉 스케치, 색·재질, 6뷰, 구조·지형, 소품, 자연, 시간·날씨 6변주, 월드 노트 | **장소는 둘러볼 실루엣이 없다.** 거리를 바꿔가며 본다 |

**종류마다 여러 개가 있을 수 있다.** 배경 둘, 인물 하나, 피사체 하나가 지금 구성이다.

### 보드에는 그 요소만 담는다

캐릭터 보드에서 차와 서킷 노을을 뺐다. **이 보드가 영상 모델에 인물 레퍼런스로 들어가면, 안에 있는 환경이 컷이 요청하는 장소와 경쟁한다.** 여기 있는 노을이 야간 컷에서도 지켜지려 든다.

배경 보드도 마찬가지로 특정 차나 인물을 안 그린다. 익명 스케일 피겨만 허용한다.

### 격리 패널은 밝은 배경

처음에 검정 배경으로 나와서 검정 재킷과 검정 신발이 안 보였다. 턴어라운드, 헤드 스터디, 의상 분해, 재질, 소품은 거의 흰색 배경에 접지 그림자를 둔다. 히어로와 표정 연구는 자기 조명을 유지한다.

### 해상도와 비용

아래 수치는 API 모드에서 같은 프롬프트로 실측한 기록이다. Codex 직접 생성은 일반 Codex 사용량에 포함되고 세부 토큰이 영수증에 노출되지 않으므로 같은 표로 환산하지 않는다.

**API 과금은 크기가 아니라 품질이 정한다.**

| 크기 | 품질 | 출력 토큰 |
|---|---|---:|
| 2048x1152 | low | 157 |
| 2048x1152 | medium | 1,413 |
| 2048x1152 | high | 5,650 |
| 1024x1024 | high | 7,024 |
| 3840x2160 | high | 13,342 |

2048x1152 high 가 1024x1024 high 보다 픽셀은 2.25배인데 토큰이 적다. 계단은 34배 차이다.

현재 운영 규약은 **시트를 Codex에서 관측된 네이티브 `1672×941` landscape 또는 `941×1672` portrait와 high로 요청**한다. Codex 앱·CLI에서는 manifest가 기본 프롬프트 뒤에 계약 래스터/high 요청문을 해시로 결박한다. 응답 원본이 계약보다 작으면 확대하지 않고 확정을 중단한다. 판은 시트 래스터를 상속하지 않으며 영상 `frame`과 유사한 공급자 크기로 요청한 뒤 정확한 프레임으로 축소한다.

API 상한은 긴 변 3840 이다. API 가 직접 알려줬다.

---

## 5. 3단계 · `03-scenario`

```bash
python3 -m ai_video_pipeline.scenario <attempt> [--force]
```

### 시트를 이미지로 물린다

정의는 글로, 보드는 그림으로 들어간다. 텍스트 모델이 보드를 읽는 것을 미리 확인했다. 허스키 보드만 주고 물었더니 실루엣 요소 다섯과 대표색 셋을 정확히 뽑았다.

그래서 시나리오가 보드에 실제로 그려진 물건만 쓴다. 손전등, PTFE 테이프, 파이프 렌치가 비트에 나오는데 셋 다 소품 패널에 그려진 것이다.

### 막 구조는 계약이 정한다

**5단 구조는 보편이 아니다.** 상황·욕구·갈등·변화·결과는 서사물에만 맞는다. 자동차 리뷰에는 욕구도 갈등도 변화도 없다. 숏폼 전체로 보면 튜토리얼, 리스트, 전후 비교, 반응, 몽타주처럼 서사가 아닌 형식이 더 많다.

형식을 enum 으로 열거하면 새 형식마다 코드를 고쳐야 한다. 그래서 계약이 막을 선언한다.

```json
"scenario": {"structure_id": "narrative-5", "why": "..."}
```

`src/ai_video_pipeline/scenario_structures/` 에 시작 세트가 있다.

```
narrative-5      상황 욕구 갈등 변화 결과
kishotenketsu    기 승 전 결
walkthrough      대상 부분 안 작동 수치
problem-fix      문제 진단 처치 확인
```

계약이 `acts` 를 직접 쓰면 템플릿을 안 써도 된다. **도구는 막이 몇 개인지 무슨 이름인지 모른다.**

### 균등 배분을 세 겹으로 막는다

첫 실행이 10비트 전부 6초로 나왔다. 60을 10으로 나눈 것이고 연출이 아니다.

1. **막마다 비트 길이 범위가 다르다.** 갈등 3-4초, 변화 5-7초, 결과 7-10초. 범위가 겹치지 않으면 균등이 애초에 불가능하다. 범위 출처는 `docs/design/shot-grammar.md` 4절이다
2. **리듬 검사.** 길이 3종 이상, 최장 대 최단 1.5배 이상. 몽타주처럼 균등이 옳은 형식은 계약이 이 검사를 끈다
3. **막 비중.** 각 막이 전체에서 차지할 비율을 벗어나면 지적한다

결과가 이렇게 바뀌었다.

```
전  [6,6,6,6,6,6,6,6,6,6]   종류 1종
후  [8,7,4,3,4,6,6,5,7,10]  종류 7종, 최장/최단 3.33배
```

### 길이와 내용 분량을 맞춘다

**가장 자주 깨지는 규칙이다.** 생성 모델은 주어진 시간을 채우려 든다. 옛 파이프라인의 한 컷이 4초 실내 컷인데 가운데 2초가 실외 트랙으로 튀었고, 그 비트에 적힌 것은 "햇빛이 대시를 가른다" 뿐이었다. 아무 일도 안 벌어지는 4초를 요청한 것이다.

그래서 `why_this_long` 이 필수 필드다. **그 길이를 채우는 사건이 무엇인지** 적어야 한다.

### 검사 목록

```
비트 합이 계약 길이와 같은가
선언된 막이 전부 쓰였고 순서가 맞는가
막별 비중이 범위 안인가
비트 길이가 그 막의 범위 안인가
길이 종류와 최장/최단 비율
why_this_long 이 비어 있지 않은가
where/who/objects 가 선언된 요소를 가리키는가
정의했는데 한 컷에도 안 나오는 요소가 있는가
```

마지막 검사가 중요하다. **정의하고 시트까지 만들어놓고 안 쓰면 값을 치른 낭비다.**

---

## 6. 검증 상태

### `runs/sky-village-plumber/attempts/v1-pilot`

어린이 애니메이션. 공중 마을 허스키 배관공. 현행 최신 검증 런이다.

```
지시사항       1줄 + 보충 1건
조사           33건, 사진 17장, 출처 없는 근거 0
정의           4개 (인물 1, 피사체 1, 배경 2), 빈값 0
시트           4장, 전부 2048x1152, 단계 호환 판정 완료
시나리오       10비트 60초, 검사 전부 통과
```

### `archive/runs/supercar-review/attempts/v4-premise`

자동차 실사. 같은 코드로 돌았고 계약만 다르다. 시트 4장까지 나왔다.

**두 프로젝트가 증명하는 것.** 매체가 실사에서 애니메이션으로, 관객이 성인에서 어린이로, 피사체가 기계에서 의인화 동물로 바뀌었는데 모듈은 한 줄도 안 고쳤다.

---

## 7. 4–5단계 구현 결과와 다음에 할 일

### `04-shot-design` 에 구현된 것

카메라 네 조각, 한 컷 한 무브먼트, 연기 타임라인을 옮겼다. 여기에 H3-only 조건화 경로, start/end 상태쌍, 불변/허용 변화, 원자 동작 경고, stage05 이미지 쌍 선발과 H3 best-of-N을 추가했다. 세부 실험은 `docs/research/stage4-object-motion-control-2026-08-26.md`에 있다.

2026-08-26 후속 연구로 production H3는 끝 이미지를 사용하지 않는 `first_only`로 고정했다. 관련된 2단계 승인 시트 전체는 stage05와 H3에 필수로 전달한다. 복잡한 도구·기계·관절 상호작용은 4단계가 보조 설명서 시트의 필요성을 판정하고, 최소 6패널·3시점·3상태와 clean-board 생성 프롬프트, annotated-QA overlay 명세를 산출한다. 5단계는 그 명세를 임의로 바꾸지 않고 생성·검증·사람 승인한다. 세부 근거는 `docs/research/stage4-interaction-manual-and-seedance-review-2026-08-26.md`에 있다.

| 항목 | 근거 |
|---|---|
| 카메라 네 조각과 한 컷 한 무브먼트 | shot compiler와 semantic check가 검사 |
| 시작·끝 상태와 변화 계약 | `states`, `invariants`, `allowed_change`, `plate_acceptance` |
| 원자 동작 | 안전한 경계만 자동 분할하고 나머지는 사람 분할 경고 |
| H3-only 실행 | I2V/FL2VA/guide는 H3 조건화 경로이며 다른 영상 엔진 금지 |
| **연기 기술** | 시간순 action timeline과 주지 않은 행동 금지 |
| 2단계 시트 결속 | 관련 전체 시트를 stage05·H3 입력에 필수로 컴파일; 보조 보드가 대체하지 못함 |
| 상호작용 설명서 | 필요성, 패널·시점·상태, 물리 계약, stage05 이미지 프롬프트와 승인 gate |

마지막 것이 새로 나온 지적이다. Blue Eye Samurai 스토리보드 아티스트가 이렇게 말했다.

> 그리지 않으면 애니메이터가 지어내지 않는다. 준 것만 애니메이션한다.
> 행동을 원하면 행동을 스토리보드에 그려야 한다.

**생성 모델은 애니메이터와 같다.** 지금 비트에 "허스키가 귀를 쫑긋 세우고 듣는다"까지는 있는데 어떤 속도로 어떤 자세인지는 없다. 실사면 넘어가지만 애니메이션은 그게 전부다.

### 다음 작업과 미해결

`generation_harness.py`, `stage5.py`, `pipeline-recovery-harness`, `plate-imagegen` 스킬이 전 단계의 검증·자동 복구와 5단계의 전역 레퍼런스 장벽, 시작판 단일 생성→AI 검증→최대 10회 시도별 변주, 사람 선발, 영수증과 first-only H3 handoff를 실행한다. stale manifest와 생성 파생물 실패는 소유 단계에서 자동 복구하며 중간 확인을 요구하지 않는다.

**시트 3패널 대 다패널.** `shot-grammar.md` 0절의 두 출처가 정반대를 말한다. 우리는 다패널로 갔고 보드 안에서는 도플갱어가 없었다. 다만 그 보드로 만든 컷에서 인물이 유지되는지는 `05-plate` 까지 가야 안다.

**엠블럼.** 계약이 `no-plate` 로 노즈 엠블럼을 금지했는데 이미지 모델이 두 번 어겼다. 프롬프트에는 조항이 들어갔다. 반복되는 실패다.

**격자 정렬.** H3 가 17k+5 프레임 격자에 스냅해서 6초 비트는 6.583초를 만들어 8.9% 를 버린다. 8초는 정확히 격자 위다. 이야기를 기계에 맞추면 안 되므로 권고로만 둘 자리다.

---

## 8. 파일 지도

```
src/ai_video_pipeline/
  contract.py            계약 로더. 프레임, 이미지 역할, 조항, 막 구조
  contract_gate.py       계약이 실제로 지켜졌는지 검사
  premise.py             1단계. 지시, 조사 계획, 정의 제안
  research.py            웹 검색과 이미지 검색. 근거 기록
  subjects.py            정의 검사. 빈값, 검산, 출처, 소비자 대조
  sheets.py              2단계. 두 패스로 보드 생성
  scenario.py            3단계. 보드를 보고 시나리오
  stage5.py              5단계. 설명서·시작판 후보·사람 승인·H3 handoff
  sheet_specs/*.md       시트 설계 명세 3종
  scenario_structures/*.json  막 구조 4종
  run_layout.py          8단계 규약과 검사기
  graph_dashboard.py     단계 그래프 대시보드

docs/design/shot-grammar.md          촬영 문법. 4단계에서 쓸 것
research/short-form-scenario/REPORT.md  숏폼 시나리오 조사

active: runs/luxury-penthouse-tour/attempts/v2  4단계 완료, 5단계 입력 감사 완료·1단계 승인 대기
archive/runs/supercar-review/attempts/v4-premise  2단계까지 · 레거시 보존본
```

테스트 136개. `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v`
