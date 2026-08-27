# 인간-AI 공동 제작형 AI 영상 방법론 연구

> 작성일: 2026-08-22  
> 사용자 환경: **GPT Pro 계정 + GPT Image API + 로컬 MiniMax H3**  
> 출력 기준: **768p 허용**  
> 목표: 무인 대량생산이 아니라, AI가 대부분의 제작을 진행하고 **품질을 좌우하는 순간에만 사용자에게 구체적인 선택을 요청**하는 시스템

## 결론

좋은 AI 영상은 `좋은 프롬프트 → 한 번 생성`으로 나오지 않는다. 조사한 실제 제작자들은 공통적으로 다음을 수행했다.

1. 생성 전에 이야기·감정·시각 기준을 고정한다.
2. 캐릭터·공간·상태별 reference를 만든다.
3. 한 번에 긴 완성본을 만들지 않고 shot 단위로 만든다.
4. 같은 shot을 여러 번 생성하고 **전체 clip이 아니라 좋은 0.5–3초 구간까지 건져 쓴다.**
5. 좋은 중간 frame을 캡처해 다음 생성의 start frame으로 되먹인다.
6. 생성 오류를 무조건 재생성하지 않고 trim·cutaway·사운드·속도 조정으로 먼저 고친다.
7. 선택과 실패 이유를 기록해 다음 프로젝트의 판단 기준으로 만든다.

따라서 자동화 대상은 단순한 생성 버튼이 아니라 **감독의 반복 작업**이다. AI는 대안을 준비하고 결함을 분류하며 다음 수정안을 제안한다. 사람은 방향·취향·모호한 미감처럼 AI가 확신하기 어려운 결정만 한다.

## 조사 범위와 증거 수준

연구는 두 묶음이다. 첫째, `신비한 건축사전` 재현·역추론과 집중 workflow 8편의 transcript 전체를 읽었다. 둘째, **2025-08 이후 20분 이상 실무 영상 7편, 총 3시간 24분**을 추가로 전체 전사·close-read했다. 단, `신비한 건축사전` 원 제작자의 공식 메이킹이 아니라 **재현 튜토리얼 또는 시스템 역추론**인 영상은 그 한계를 구분한다.

| 영상 | 날짜 / 길이 | 증거 성격 | 핵심 학습 |
|---|---:|---|---|
| [구글 플로우로 신비한 건축사전 만들기](https://youtu.be/6FYfDgr-EIo) | 2026-08-13 / 14:37 | 재현 튜토리얼 | 3개 주제 중 선택, 사람의 대본 수정, 음성 전수 청취, style 재선택, 움직임 부족 시 prompt repair, 마지막 frame 연쇄 |
| [신비한 건축사전의 진짜 노하우](https://youtu.be/81qhGfVXy7k) | 2026-07-31 / 14:25 | 제작 시스템 역추론; 실제 내부 공정은 미확인 | 원문 기반 claim 검증, 반대 근거 탐색, frame-level script alignment, deterministic QA, 실패 허용 기준의 축적 |
| [신비한 건축사전 30분 따라 만들기](https://youtu.be/ObvCtB1ATnA) | 2026-07-14 / 22:27 | 재현 제작 화면 | reference 작품의 story grammar 분석, hook·반전 구조, 팩트체크, 18개×8초 생성 후 약 3초씩 salvage, 편집 여유분, 말의 끝에서 cut |
| [신비한 건축사전 쇼츠 따라 만들기](https://youtu.be/ReUyaMDGj9o) | 2026-05-24 / 12:48 | 재현 제작 화면 | 2개 후보씩 생성, 좋은 부분만 절취, voice 3개 audition, 자막 오타 수동 검수, 720p도 모바일에 충분 |
| [How to Create Professional AI Animations](https://youtu.be/aVfawxDj6uw) | 2026-04-07 / 19:42 | 전문 제작 workflow | story 우선, character development, rough audio cut, spreadsheet shot list, storyboard cut, shot당 약 12회 탐색, ADR·proxy edit |
| [AI Filmmaking in 2026](https://youtu.be/ZghLm9MXVIY) | 2026-04-06 / 19:25 | 실제 단편 제작 breakdown | 상태별 character sheet, timeline prompting, 4개 생성본을 한 장면으로 stitch, 4–7회 재생성, 좋은 frame을 새 start frame으로 사용 |
| [Prompting AI Video the RIGHT Way](https://youtu.be/cGTBzed4S4w) | 2026-04-01 / 8:09 | prompt iteration 방법 | 모델 공식 문서를 GPT 지식으로 사용, 사람은 의도·감정을 말하고 AI가 모델 문법으로 번역, screenshot과 실패 설명을 prompt repair에 사용 |
| [Long Video with Consistent Characters](https://youtu.be/i_KlptBTdck) | 2025-12-24 / 18:31 | 장면 연장·편집 workflow | 첫 clip에서 연장, frame을 asset화, speech 길이 제한, scene builder 후에도 외부 편집·사운드·trim이 필요 |

### 추가 장시간 실무 close-read — 7편, 총 3시간 24분

| 영상 | 날짜 / 길이 | 사람이 실제 판단한 것 |
|---|---:|---|
| [Seedance 2.5 — Full Cinematic AI Film Workflow](https://www.youtube.com/watch?v=MY6f9xnYOwU) | 2026-08-08 / 26:47 | 핵심 메시지·코미디 timing, 0.5초 단위 연기, character/location sheet, 30초 후보 3개의 좋은 구간 채굴, 음악·grain·color finish |
| [Complete AI Filmmaking Workflow: Concept to Film](https://www.youtube.com/watch?v=8FD8M7jhX20) | 2026-01-25 / 45:01 | 브랜드 보이스와 아이디어를 분리 평가, 완성 스타일 안에서 casting, camera/lens/film stock/lighting/grain style bible, 여러 voice performance 합성, micro-cut·Foley·whisper |
| [5-Step Ultra-Realistic AI Short Film Workflow](https://www.youtube.com/watch?v=HSON-SoFz7s) | 2026-07-02 / 33:20 | character/location/prop 자산 분리, 반사·그림자·행동 semantics·버튼 위치 진단, reference 위 화살표 annotation, 다음 shot과 마지막 frame 연결 |
| [The Complete AI Short Film Workflow Everyone’s Missing](https://www.youtube.com/watch?v=tW40b122Rbs) | 2026-03-13 / 26:24 | prompt보다 관객 감정에서 시작, setup–midpoint–climax, 작은 눈동자 움직임까지 연기 판정, b-roll과 radio interruption의 서사 기능, missing coverage 재생성 |
| [Complete AI Short Film — Behind the Scenes](https://www.youtube.com/watch?v=1U0_vZpCnGo) | 2026-04-21 / 24:59 | label·angle·description이 있는 shot list, 4-panel style reference, 빈 세트와 복수 각도, storyboard 이미지 수정, Foley·theme·riser·drone·hit, disclosure·credit QA |
| [Master AI Filmmaking in 30 Minutes](https://www.youtube.com/watch?v=e9ZupmL9BcM) | 2026-06-25 / 31:17 | prop state와 사라진 TV 같은 continuity 오류, 아이디어 팽창 억제, 저해상도 probe 후 최종 생성, 여러 후보 segment 조합, voice identity와 배경 동작 검사 |
| [Hyperrealistic Consistent AI Characters](https://www.youtube.com/watch?v=PhiPASFYBmk) | 2025-10-07 / 24:17 | turnaround·표정·pose·의상 자산 선별, 이상·중복 이미지 제거, 최신 checkpoint가 아닌 중간 checkpoint 선택, identity와 realism trade-off |

이 장시간 자료가 추가한 결론은 다섯 가지다.

1. **Style Bible은 ‘시네마틱’ 같은 형용사가 아니다.** camera body, lens family, focal length, film stock, 광원 방향, 온도, contrast, grain, 금지 look을 저장한다.
2. **Casting은 얼굴 유사도만으로 하지 않는다.** 실제 완성 style과 scene에 배우 후보를 합성해 역할의 정서와 장면 적합성을 본다.
3. **Reference는 설명뿐 아니라 annotation도 쓴다.** 작은 버튼·동작 위치·시선 대상은 이미지 위 화살표와 mask로 표시한다.
4. **편집 중 missing coverage 발견은 실패가 아니라 정상 loop다.** insert·reaction·bridge·establishing shot이 부족하면 해당 coverage만 다시 생성한다.
5. **H3 네이티브 음향은 timing 후보이지 자동 최종 mix가 아니다.** cut 길이가 바뀌면 대사·Foley·ambience·music·silence를 별도 Sound Map으로 다시 구성한다.

## 발견 1 — 작품의 핵심은 도구가 아니라 “판단 사슬”이다

`신비한 건축사전`류 재현에서 반복된 판단은 다음과 같다.

- **주제:** 영상으로 보여주기 쉬우며 반전·문제 해결 구조가 있는가?
- **대본:** 3초 hook이 상식을 뒤집는가? 사실과 표현 강도가 근거에 맞는가?
- **시각화:** narration이 말하는 구조·시대·대상이 frame에 실제로 보이는가?
- **움직임:** 단순 zoom이 아니라 정보나 감정을 전진시키는가?
- **편집:** 긴 생성 clip의 좋은 조각만 남겼는가? 발화 경계와 cut이 맞는가?
- **허용 오차:** 모바일에서 순간적으로 지나가는 경미한 오류인가, 신뢰를 무너뜨리는 오류인가?

이 판단 사슬을 schema와 evaluator로 만들지 않으면 모델이 좋아져도 일관된 품질이 나오지 않는다.

## 발견 2 — 생성 단위와 편집 단위는 다르다

제작자들은 8–10초 clip을 만들더라도 실제로는 약 0.5–3초 구간만 사용했다.

- `ZghLm9MXVIY`: 네 개의 생성본에서 좋은 부분만 골라 하나의 장면으로 stitch.
- `ObvCtB1ATnA`: 8초짜리 18개를 생성하지만 완성본에는 각 clip의 좋은 약 3초만 사용.
- `aVfawxDj6uw`: 원하는 take를 얻는 데 shot당 약 12회가 걸릴 수 있다고 보고.

따라서 시스템은 `candidate 승인/폐기` 2분법이 아니라 **candidate 안의 usable segment**를 기록해야 한다.

```text
H3 candidate
  ├─ 0.0–1.2초: 사용 가능
  ├─ 1.2–3.8초: 손/물리 오류
  └─ 3.8–5.0초: 다음 shot의 start frame으로 재사용
```

## 발견 3 — reference는 고정된 한 장이 아니라 상태 기계다

캐릭터·건축물·제품은 시간이 지나며 상태가 변한다.

- 정면·측면·후면 character/location sheet
- 의상·소품·날씨·손상 상태별 variant
- 장면 직전의 마지막 frame
- 장면 후 도달해야 할 end frame

`ZghLm9MXVIY`는 헬멧 착용 상태가 달라질 때 character sheet를 따로 만들고, 상태 변화가 생길 때마다 sheet를 갱신해야 한다고 설명한다. 시스템에는 `entity_state`와 `continuity_transition`이 필요하다.

## 발견 4 — 좋은 수정은 prompt 전체 재작성보다 결함별 delta다

제작자가 실제로 준 수정은 작고 구체적이었다.

- “화면을 3단 분할하지 말 것”
- “움직임을 더 역동적으로”
- “카메라는 고정”
- “인물 표정을 유지하고 마지막에 대상을 볼 것”
- “헬멧의 반사 없이 얼굴이 보이게”
- “배경에 물과 전경을 더 보여줄 것”

따라서 사용자 피드백은 전체 prompt를 지우고 다시 쓰는 것이 아니라 다음처럼 저장한다.

```json
{
  "keep": ["character identity", "lighting", "first 1.2 seconds"],
  "change": ["static camera", "stronger lateral motion"],
  "forbid": ["split screen", "duplicate character"],
  "priority": "motion clarity"
}
```

## 재제안 — AI 감독실 파이프라인

### A. 사전제작: 생성 전에 값싼 오류를 잡는다

1. **Creative Constitution**
   - 시청자, 한 문장 약속, 원하는 감정, 금지 요소, 사실성 수준, 시각 어휘를 고정한다.
2. **Reference Deconstructor**
   - 좋아하는 영상에서 겉모습이 아니라 hook, beat, shot density, cut rhythm, 정보 공개 순서를 추출한다.
3. **Research & Claim Ledger**
   - 지식·건축·역사 영상이면 각 대본 문장을 exact source와 연결하고, 반대 설명과 표현 강도를 검사한다.
4. **Concept Tournament**
   - AI가 3개 방향과 장단점·권장안을 제시한다. 사용자는 하나를 고르거나 조합한다.
5. **Script Workshop**
   - hook→질문→오해→원인→발상 전환→보상 구조를 만들고, 낭독 시간과 발화 리듬을 검증한다.
6. **Look Bible**
   - GPT Image API로 style frame, entity sheet, state variant, location map, first/last frame을 만든다.
7. **Animatic Gate**
   - H3를 쓰기 전에 still+scratch audio로 저비용 animatic을 만들어 이야기·순서·시간을 먼저 승인한다.

### B. 제작: H3를 shot 공장으로 쓰되 AI가 감독한다

8. **Shot Intent Card**
   - 목적, 감정, 화면 정보, 카메라, 동작, 시작/종료 상태, 대사/음향, 실패 금지조건을 구조화한다.
9. **H3 Prompt Compiler**
   - Shot Card와 H3 공식 능력(FL2VA/Ref2VA)에 맞춰 prompt/reference package를 자동 생성한다.
10. **Adaptive Candidate Generator**
    - 1차 4개 → 자동 평가 → 차이가 부족하면 prompt delta 후 2차 4개.
    - 8회 후에도 불명확하면 사람에게 묻고, hard cap 12회에서 중단한다.
11. **Segment Miner**
    - 각 clip을 frame·audio 기준으로 분석해 usable segment와 reusable frame을 표시한다.
12. **Critic Council**
    - 의미/사실, continuity, motion/physics, performance/emotion, sound-sync, editability를 분리 평가한다.
    - 미감은 AI가 순위와 이유만 제시하고 최종 결정은 사람이 한다.
13. **Prompt Repair Agent**
    - 결함 taxonomy에 따라 `keep/change/forbid` delta를 만들고, 문제 shot만 재생성한다.

### C. 후반작업: 생성 결함을 무조건 재생성하지 않는다

14. **Edit Builder**
    - 승인 segment를 narration beat에 맞춰 배치하고, 발화 경계에서 cut한다.
15. **Traditional Fix Router**
    - trim, speed, cutaway, crop, sound effect, volume, subtitle로 해결 가능하면 H3를 다시 돌리지 않는다.
16. **Rough-cut Critic**
    - hook 이탈, 반복, 정보 과밀, 감정 단절, 장면 사이 discontinuity를 전체 맥락에서 검사한다.
17. **Final QA**
    - codec/768p/길이/음량/무음/자막은 코드로 검사하고, 의미·미감은 멀티모달 평가+사람 승인으로 분리한다.
18. **Learning Ledger**
    - 채택/거절 이유, salvaged 구간, repair 효과, 사용자 취향, 실제 성과를 다음 제작 규칙으로 환류한다.

## 사용자 피드백은 언제 요청할 것인가

단계마다 별도 메시지를 보내지 않는다. **AI의 확신이 낮거나 방향 전환 비용이 큰 순간**만 묻고, 인접 게이트를 한 packet으로 묶는다.

### Interaction Budget

- 한 영상의 예정된 Telegram packet: 최대 4회 — `Direction+Script / Look+Animatic / Selects+Edit / Release`
- 시간당 비긴급 요청: 최대 2회
- 한 packet에 결정: 최대 3개
- 5분 안에 생긴 질문은 한 packet으로 합친다.
- 같은 결정을 다시 묻지 않는다. 새 증거가 생긴 경우에만 재질문한다.
- 답변 대기 중에도 가역적·저위험 작업은 계속한다.
- 미응답 시 가역적·저위험 결정은 AI 추천안으로 진행하고, 방향·권리·사실·공개는 정지한다.
- 질문 여부는 `예상 재작업비용 × 답변이 결정을 바꿀 확률 - 응답부담 - 중단비용`이 양수일 때만 허용한다.

| Packet | 사용자에게 보여줄 것 | 좋은 질문 예시 | 묻지 않아도 되는 것 |
|---|---|---|---|
| P1 방향+대본 | 콘셉트 3개, AI 권장안, 대본·claim 경고 | “정보 전달 A와 감정 몰입 B 중 어느 쪽을 우선할까요?” | 파일명·코덱 |
| P2 Look+Animatic | style/캐릭터/공간 A·B·C와 저비용 전체 animatic | “A의 구도와 B의 조명을 결합할까요?” | 해상도 변환 |
| P3 Selects+Edit | 문제 shot 후보, usable interval, rough cut A/B | “2번의 표정을 유지하고 카메라만 고정할까요?” | 자동 PASS shot |
| P4 Release | master, 사실·권리·기술 QA | “게시 승인/특정 shot 수정/전체 보류” | 임시 파일 정리 |

목소리 정체성·음악 감정·브랜드 사운드가 새로 갈리는 경우만 P3에 Sound Direction 결정을 추가한다.

### Telegram feedback packet 계약

```text
[SHOT S07 — 결정 필요]
목적: 주인공이 구조의 원리를 처음 이해하는 순간
AI 추천: B (표정·시선은 가장 좋고, 손 오류는 0.4초 cut으로 제거 가능)
A: 움직임 자연스러움 / 감정 약함
B: 감정 우수 / 끝부분 손 오류
C: 구도 우수 / 인물 외형 흔들림

선택: B 그대로 / B에서 카메라만 느리게 / A+B 결합 / 직접 지시
```

한 번에 질문 하나만 보내고, 가능한 경우 AI 권장안을 함께 준다. 여러 shot의 동일 문제는 한 묶음으로 배치한다.

## 시스템 역할

- **Showrunner:** Creative Constitution과 전체 품질 목표 유지
- **Research Editor:** source와 claim 관계·반대 근거 검사
- **Story Editor:** hook·beat·정보 공개 순서·낭독 리듬
- **Visual Director:** Look Bible과 GPT Image 생성
- **Continuity Supervisor:** entity state와 shot 사이 연속성
- **H3 Cinematographer:** FL2VA/Ref2VA package와 카메라·동작 설계
- **Performance & Motion Critic:** 표정·연기·물리·동작 오류
- **Editor & Sound Critic:** salvage, cut rhythm, speech, H3 동시 음향
- **Producer:** 상태·GPU·재시도·승인·비용·파일 provenance
- **Feedback Translator:** 사용자 선택을 구조화된 prompt delta로 변환

역할은 항상 별도 모델 프로세스일 필요가 없다. 한 오케스트레이터가 필요한 순간에 rubric별로 역할을 전환하는 것이 기본이다.

## 구현 아키텍처

```text
Telegram / GPT 대화
        │
        ▼
Director Orchestrator
  ├─ Creative/Research/Story agents
  ├─ Approval & Feedback Manager
  └─ Critic rubrics
        │
        ▼
SQLite Production Ledger
brief ─ script ─ look bible ─ shot card ─ candidate ─ segment ─ decision
        │
        ├─ GPT Image API adapter
        ├─ Local MiniMax H3 runtime adapter
        └─ FFmpeg deterministic edit/QA
        │
        ▼
Review packets → 사용자 선택 → delta → 문제 범위만 재실행
```

### MCP·CLI 판정

- **파이프라인 본체:** Python + SQLite. 상태, 재시도, provenance, partial rerun을 담당한다.
- **CLI:** 개발·복구·batch·테스트에 필수다.
- **MCP:** GPT/Claude 대화에서 `프로젝트 생성`, `후보 요청`, `승인 기록`을 호출하는 얇은 리모컨이다. 품질 방법론 자체가 아니다.
- **Telegram:** 사용자의 실제 승인 UI로 가장 적합하다. 미리보기와 선택지를 보내고 답변을 ledger에 기록한다.

외부 생성 중계 provider는 이 사용자 구성에 필요하지 않으며 active 설계에서 제외한다.

## 성능 점검

모델 점수 하나로 품질을 판정하지 않는다. 프로젝트 3편 이상에서 다음을 함께 측정한다.

### 작품 품질

- Story clarity: hook·전개·보상 이해율
- Intent fidelity: shot intent가 화면에 구현된 비율
- Continuity: 인물·제품·공간·상태 오류/shot
- Motion quality: 물리·팔다리·카메라 결함/초
- Edit rhythm: 사용자 또는 blind reviewer의 리듬 선호
- Sound: 대사 명료도·화면/소리 의미 일치
- Human preference: 전체 blind A/B 승률

### 제작 효율

- 최초 합격 후보 비율
- shot당 생성 횟수
- 생성 clip 대비 실제 사용 초 비율(`salvage yield`)
- 문제 shot만 고친 비율
- 사용자에게 물은 횟수와 응답당 수정 성공률
- 사용자 개입 분/완성분
- H3 GPU 분/실사용 완성초
- restart 후 중복 생성 0건

### 피드백 시스템 품질

- 질문이 실제 결정을 바꾼 비율
- 사용자가 AI 권장안을 채택한 비율
- 같은 취향을 반복 질문한 횟수
- 사용자 답변을 prompt delta로 잘못 번역한 비율
- 불필요한 질문 때문에 중단된 시간

## 권장 MVP

외부 provider 비교가 아니라 **30–60초 실제 영상 한 편**을 end-to-end로 만든다.

1. G1 콘셉트 선택
2. source-backed script와 G2 승인
3. GPT Image Look Bible A/B/C와 G3 승인
4. still animatic과 G4 승인
5. 8–12개 Shot Card
6. 각 shot H3 후보 4개, 자동 평가·segment salvage
7. uncertainty가 큰 shot만 G5로 묶어 질문
8. FFmpeg rough cut A/B와 G6 승인
9. 자동 QA 후 G7 게시 승인
10. 전체 decision/feedback ledger를 다음 영상에 재사용

MVP의 성공은 “한 편이 나왔다”가 아니라 다음 네 조건이다.

- 같은 승인 자산에서 문제 shot만 재실행할 수 있다.
- 사용자가 무엇을 왜 선택했는지 기록된다.
- 후보의 좋은 구간을 폐기하지 않고 재사용한다.
- 두 번째 영상에서 같은 질문과 실패가 실제로 줄어든다.

## 관련 문서

- [[projects/ai-video-production-pipeline/README|AI 영상 제작 파이프라인]]
- [[projects/ai-video-production-pipeline/pipeline-schema|파이프라인 스키마]]
- [[projects/ai-video-production-pipeline/mvp-build-queue|MVP 구축 큐]]
- [[projects/ai-video-production-pipeline/productux-design-brief|ProductUX 설계 브리프]]
- [[topics/ai-creative-production-workflow|AI creative production workflow]]
