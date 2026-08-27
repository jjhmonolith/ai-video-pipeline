# AI 영상 제작 운영체계 — 단계별 자동화 도구와 성능개선 폐루프 설계

> 상태: `design-v1; implementation-deferred`  
> 작성일: 2026-08-23  
> 적용 환경: GPT Pro + GPT Image API + 로컬 MiniMax H3 768p + FFmpeg 계열 결정론적 처리  
> 우선순위: **구현 속도보다 설계 완결성, 자동화율보다 결과물 품질**

## 0. 설계 정정

이 프로젝트의 다음 과제는 Python 기능을 빨리 늘리는 것이 아니다. 먼저 다음 세 가지를 완결해야 한다.

1. 제작 단계마다 **무엇을 자동화하고 무엇을 사람이 판단하는지** 고정한다.
2. 자동화 작업을 수행할 **자체 도구의 입력·출력·실패·검증 계약**을 설계한다.
3. 완성본과 제작 기록에서 배우는 **shot → project → cross-project 성능개선 폐루프**를 만든다.

이미 구현한 G1–G10 gate catalog·resolver는 전체 시스템의 작은 계약 검증 spike로 유지한다. 구현 확장의 근거로 삼되, 설계가 끝나기 전에 SQLite·Telegram·H3 adapter를 연속 구현하지 않는다.

---

## 1. 운영체계의 네 층

```text
① Creative Method
   작품 의도, 서사, Look, 연기, 편집, sound, 문화·윤리

② Stage Toolkits
   각 단계의 반복 작업을 수행하고 검증 가능한 artifact를 만드는 자체 도구

③ Production State
   project/shot/asset/attempt/decision/metric/experiment/learning ledger

④ Control Surfaces
   Telegram review, CLI, MCP, scheduler — 본체가 아니라 조작면
```

핵심 원칙:

- 도구는 결과를 직접 “좋다”고 확정하는 대신 **근거와 선택지를 만든다**.
- 모든 단계는 `input artifact → tool work → output artifact → automatic check → human gate/continue` 형태다.
- 도구가 생성한 설명보다 **원본 파일·타임코드·상태 diff·실제 비교본**이 우선한다.
- MCP 도구를 30개 노출하지 않는다. 내부 Stage Toolkit은 세분화하고, 대화형 MCP는 상위 작업 6개 안팎으로 제한한다.
- prompt는 장기 학습 단위가 아니다. `상황 + 변경 변수 + 관찰 결과 + 사람 결정 + 재현 조건`이 학습 단위다.

---

## 2. 전체 제작 단계와 자체 도구 지도

| 단계 | 자동화해야 할 작업 | 자체 Toolkit | 주 출력 | 인간 판단 |
|---|---|---|---|---|
| S0 Intake·Brief | 입력 정규화, 누락·충돌 탐지, 성공기준 초안 | BriefKit | VideoBrief, Quality Charter draft | G1 의도·우선순위 |
| S1 Research·Claims | 주장 수집, 출처 결박, 불확실성·금지표현 | EvidenceKit | Claim Ledger, rights/uncertainty map | 사실·권리·과장 승인 |
| S2 Concept | 서로 다른 방향 생성, trade-off 비교, 중복 제거 | ConceptKit | 2–4 Concept Cards | G1 방향 선택, G10 초기 위험 |
| S3 Script·Story | beat, 인과, reveal, subtext, 낭독시간 검사 | StoryKit | Beat Graph, Script, Subtext Map | G1/G2 의미·subtext |
| S4 Look·World | Look Bible, entity/location/state/reference pack | LookKit | Style/Entity/World Bible | G4/G5 미감·POV·세계 규칙 |
| S5 Shot·Animatic | Shot Intent Card, continuity graph, 저비용 animatic | PrevisKit | Shot Plan, Animatic, Coverage Plan | G1/G4/G7 구조·타이밍 |
| S6 Generation | 요청 compile, GPT Image/H3 job, 자산 수집·provenance | GenerateKit | Candidate assets, attempt receipts | 고비용 예외만 |
| S7 Select·Repair | segment mining, 결함 증거, blind critic, 후보 비교 | SelectKit | Select Board, usable intervals, repair delta | G3/G6 핵심 take·예외 |
| S8 Edit·Coverage | EDL 생성, 결정론적 편집, coverage 부족 탐지 | EditKit | Rough Cut A/B/C, Missing Coverage List | G1/G6/G7 편집 판단 |
| S9 Sound | stem 분리, Sound Map, loudness-matched mix 비교 | SoundKit | DIA/AMB/FOL/SFX/MUS stems, mix options | G8 청각 POV·침묵 |
| S10 Review·Release | 검토 packet, 기계 QA, 권리·문화·공개 체크 | ReviewKit | Judgment Packet, Release Candidate | G9/G10 실제 관객·공개 |
| S11 Distribution | 채널 variant, 제목·썸네일·CTA packet, 게시 전 확인 | ReleaseKit | Distribution Packet | 외부 게시 승인 |
| S12 Measure·Learn | 성과 수집, 실패군집, paired experiment, rule 승격 | LearnKit | Scorecard, Experiment, Learning Rule | creative rule 승격 |

---

## 3. 공통 Tool Contract

모든 내부 도구는 같은 envelope를 사용한다.

```yaml
tool_id: select.segment_miner
tool_version: 1.0.0
run_id: RUN-...
project_id: P-...
scope_ids: [SHOT-S07]
input_artifacts:
  - asset_id: CAND-S07-B
    sha256: ...
config_snapshot:
  model_or_algorithm: ...
  thresholds: {...}
idempotency_key: sha256(tool_version + inputs + config)
side_effect_class: read_only | local_write | generation_cost | external_publish
outputs:
  - artifact_id: SEG-S07-B-01
    path: ...
    sha256: ...
evidence:
  - time_range: 0.8-2.6
    observation: "reaction begins after stimulus"
metrics:
  wall_time_sec: ...
  compute_sec: ...
  estimated_cost: ...
status: pass | repair | blocked | quarantined
failure:
  category: transient | contract | provenance | quality | permission
  retryable: false
```

### 도구 설계 규칙

1. **입력 hash가 없으면 실행하지 않는다.**
2. 같은 `idempotency_key`는 중복 생성·비용을 막고 기존 결과를 반환한다.
3. 생성 도구와 평가 도구의 context를 분리한다.
4. semantic 평가에는 `finding + exact timecode/frame + confidence`가 필요하다.
5. 한 도구는 한 artifact family만 책임진다.
6. 실패는 project 전체가 아니라 scope별 quarantine/repair로 보낸다.
7. 외부 게시·권리·비가역 생성비 초과는 명시적 승인 없이는 실행하지 않는다.
8. 모든 도구는 CLI와 내부 Python API를 먼저 가진다. MCP는 같은 core의 상위 wrapper다.

---

## 4. Stage Toolkit 상세 설계

## S0. BriefKit — 모호한 요청을 제작 계약으로 바꾼다

### 자동화 작업

- 대화·문서·URL에서 audience, viewer job, single promise, evidence, CTA, channel, duration 추출
- 서로 충돌하는 목표 탐지: 예) “차분함”과 “초고속 바이럴 편집”
- 누락 필드와 확인이 필요한 사실·권리 표시
- `HumanQualityCharter` 초안과 성공/실패 예시 생성

### 내부 도구

- `brief.normalize`: 자유 입력 → VideoBrief
- `brief.conflict_scan`: 목표·채널·길이·브랜드 제약 충돌
- `brief.quality_charter_draft`: 감정 궤적·우선순위·anti-goal 초안
- `brief.acceptance_examples`: 좋은/나쁜 결과의 대조 예시

### 자동검사

- single promise가 한 문장인가
- 성공 지표와 CTA가 서로 연결되는가
- `priority_order`, `anti_goals`, `hard_human_gates`가 비어 있지 않은가

### 사람 판단

G1에서 “무엇을 남길 것인가”와 충돌 시 우선순위를 잠근다. 이 결정 전에는 ConceptKit이 대량 생성하지 않는다.

---

## S1. EvidenceKit — 사실·권리·표현 위험을 생성 전에 잠근다

### 자동화 작업

- script에서 검증 가능한 claim 후보 추출
- claim별 source, exact excerpt, 확인 날짜, 불확실성 결박
- “공식 기능”과 “concept visualization” 분리
- 제품 로고·인물·음원·폰트·장소의 권리 상태 추적

### 내부 도구

- `evidence.claim_extract`
- `evidence.bind_source`
- `evidence.contradiction_scan`
- `evidence.rights_matrix`
- `evidence.copy_safety_lint`

### 출력

```yaml
claim_id: CLM-08
text: "최대 2일 배터리"
status: verified | conditional | unverified | forbidden
source_id: ...
exact_evidence: ...
conditions: ...
allowed_visualization: literal | concept_labeled | do_not_show
```

### 사람 판단

사실·권리·민감 표현은 자동 승인하지 않는다. 확인되지 않은 claim은 Shot Card로 전파되지 못한다.

---

## S2. ConceptKit — 평균안이 아니라 의미 있게 다른 방향을 만든다

### 자동화 작업

- 2–4개 concept 방향 생성
- 이름만 다른 유사 concept 제거
- 각 방향의 promise, hook, emotional route, visual grammar, risks, expected production cost 비교
- AI 추천과 반대 논거를 같이 제공

### 내부 도구

- `concept.generate_divergent`
- `concept.semantic_dedup`
- `concept.tradeoff_matrix`
- `concept.review_packet`

### 품질 조건

각 후보는 최소 두 축에서 달라야 한다: `story engine / emotional stance / visual POV / evidence order / audience action`.

### 사람 판단

G1이 방향과 손실을 선택한다. G10은 문화·권리 위험이 큰 방향을 조기에 차단한다.

---

## S3. StoryKit — 대본을 문장 목록이 아니라 시간축 인과로 만든다

### 자동화 작업

- hook → setup → change → proof → payoff → CTA beat graph
- `audience_knows / character_knows / audience_should_infer` 추적
- 낭독시간·정보밀도·중복 claim·설명 과잉 검사
- spoken intent와 hidden intent 분리
- 장면 삭제 시 정보·감정 손실 시뮬레이션

### 내부 도구

- `story.beat_graph_compile`
- `story.duration_simulate`
- `story.knowledge_state_track`
- `story.subtext_map`
- `story.scene_ablation`

### 사람 판단

- G1: 장면 기능·reveal 시점
- G2: subtext를 지금 읽히게 할지 나중에 재해석하게 할지

---

## S4. LookKit — 예쁜 이미지가 아니라 지속 가능한 세계를 만든다

### 자동화 작업

- style vocabulary를 렌즈·광원·palette·재료·texture·금지 look으로 compile
- product/character/location/prop의 multi-view·state sheet 생성
- reference 간 충돌, 시대착오, 제품 형태 drift 탐지
- delivery crop에서 gaze path·핵심 관계 보존 확인

### 내부 도구

- `look.style_bible_compile`
- `look.entity_sheet_build`
- `look.world_state_graph`
- `look.reference_conflict_scan`
- `look.crop_preview`

### 사람 판단

- G4: 보기 좋은 것과 맞는 POV 중 선택
- G5: 화려함과 세계 인과·생활감 중 선택

GPT Image API는 이 Toolkit의 reference generator다. LookKit 자체는 GPT Image를 호출하는 것보다 **무엇을 생성하고 어떤 상태로 승인했는지 관리하는 도구**다.

---

## S5. PrevisKit — 비싼 생성 전에 구조를 틀리게 만든다

### 자동화 작업

- Beat Graph → Shot Intent Cards compile
- shot별 start/end state, must-show, must-not-show, performance, camera, audio intent 생성
- 180°/eyeline/소품·감정 state continuity graph
- still + scratch VO + 임시 sound로 animatic 생성
- coverage gap과 너무 비싼 shot 탐지

### 내부 도구

- `previs.shot_contract_compile`
- `previs.continuity_graph_build`
- `previs.animatic_render`
- `previs.coverage_preflight`
- `previs.cost_risk_estimate`

### 사람 판단

G1/G4/G7이 sequence 의미·POV·타이밍을 승인한다. Animatic에서 고칠 수 있는 문제를 H3 생성 뒤에 고치지 않는다.

---

## S6. GenerateKit — 생성 모델을 통제 가능한 job worker로 만든다

### 자동화 작업

- 승인된 reference와 Shot Intent Card를 GPT Image/H3 request로 compile
- 모델별 payload·reference·seed·duration·aspect·audio 설정 snapshot
- idempotent submit, 상태 추적, 중복 submit 방지
- 결과 즉시 content-addressed asset store에 저장
- 실패 유형별 retry/quarantine

### 내부 도구

- `generate.request_compile`
- `generate.gpt_image_reference`
- `generate.h3_submit`
- `generate.h3_reconcile`
- `generate.asset_ingest`
- `generate.failure_classify`

### 기본 정책

- 첫 batch 4개
- critic·segment mining 후 repair batch 최대 4개
- hard cap 12개
- 한 iteration에서 원인 변수 하나만 변경

H3의 실제 실행 방식(ComfyUI/SGLang/vLLM/diffusers/독립 API)은 adapter discovery에서 확인한다. 개념 설계가 runtime을 추측해서는 안 된다.

---

## S7. SelectKit — 전체 후보가 아니라 쓸 수 있는 순간을 찾는다

### 자동화 작업

- candidate를 shot boundary·motion peak·reaction 구간으로 분할
- 좋은 0.5–4초와 reusable intermediate frame 추출
- identity·continuity·motion·physics·performance·audio·editability 결함 분리
- 생성 context를 숨긴 blind critic 실행
- AB/BA 순서 교차, close pair·critic disagreement 탐지
- 최소 수정과 부작용 제안

### 내부 도구

- `select.segment_mine`
- `select.frame_salvage`
- `select.defect_evidence_build`
- `select.blind_critic`
- `select.order_swap_check`
- `select.repair_delta_propose`

### 사람 판단

- G3: 더 믿기는 take와 더 깨끗한 take
- G6: 물리 continuity와 감정 continuity

AI margin `<=0.5/5`, AB/BA winner flip, hero take, 복수의 정당한 미학 해석은 강제 human gate다.

---

## S8. EditKit — 생성보다 먼저 편집으로 해결한다

### 자동화 작업

- selected segment → EDL
- trim, cutaway, crop, retime, speed ramp, hold, subtitle placement
- fast/balanced/linger rough cut 생성
- music-off picture pass
- missing reaction/insert/bridge/establishing coverage 탐지
- 영향받는 shot만 regeneration request로 반환

### 내부 도구

- `edit.edl_compile`
- `edit.roughcut_variants`
- `edit.deterministic_render`
- `edit.traditional_fix_route`
- `edit.missing_coverage_detect`
- `edit.partial_rerun_plan`

### 사람 판단

G7이 감정이 도착하는 frame과 떠나야 할 frame을 고른다. G6이 continuity cheat를 승인한다.

---

## S9. SoundKit — H3 네이티브 음향을 최종 믹스로 오해하지 않는다

### 자동화 작업

- H3 audio에서 유용한 timing·Foley·ambience 후보 추출
- DIA/AMB/FOL/SFX/MUS stem map
- room tone·거리·reverb·방향 continuity 검사
- 동일 loudness의 dry/world/subjective/music-led mix 생성
- picture-only와 audio-only review pass

### 내부 도구

- `sound.stem_classify`
- `sound.map_compile`
- `sound.continuity_check`
- `sound.mix_variants`
- `sound.loudness_normalize`
- `sound.review_pass_build`

### 사람 판단

G8이 누구의 귀로 들을지, 음악이 필요한지, 무엇을 들리지 않게 할지를 결정한다.

---

## S10. ReviewKit — 사람의 시간을 품질 레버리지로 바꾼다

### 자동화 작업

- G1–G10 trigger resolution
- 필요한 evidence asset 자동 수집
- 후보 차이, 장점, 손실, 결함, downstream cost 요약
- AI 추천·critic disagreement·불확실성 표시
- Telegram용 preview/contact sheet/clip packet 생성
- 답변을 Feedback Delta로 번역하고 사용자 원문 보존

### 내부 도구

- `review.gate_resolve`
- `review.evidence_bundle`
- `review.packet_compose`
- `review.telegram_format`
- `review.feedback_translate`
- `review.decision_verify`

### Interaction Budget

한 작품의 planned packet은 최대 4개로 묶는다.

1. Direction + Script
2. Look + Animatic
3. Selects + Rough Cut + 필요한 Sound
4. Release

G10 문화·윤리·권리·공개는 interaction budget과 무관하게 hard gate다.

---

## S11. ReleaseKit — 파생본과 외부 게시를 분리한다

### 자동화 작업

- 9:16/16:9/1:1 variant render
- subtitle safe area, loudness, codec, duration, black/frozen frame 검사
- title/thumbnail/description/CTA 후보
- claim·rights·disclosure·distribution scope 최종 checklist
- 게시 가능한 packet 생성

### 내부 도구

- `release.variant_render`
- `release.mechanical_qa`
- `release.claim_rights_check`
- `release.metadata_draft`
- `release.publish_packet`

외부 게시 도구는 별도이며 기본 disabled다. `publish_approved`가 있어도 채널 credential과 목적지가 일치하는지 다시 확인한다.

---

## S12. LearnKit — 성과 데이터를 “더 자극적으로”가 아니라 “더 정확하게” 배우게 한다

### 자동화 작업

- 제작 이벤트·사람 결정·실제 관객 반응·채널 성과 수집
- 반복 실패와 성공 조건을 scope별 군집화
- 다음에 바꿀 변수 하나를 `ChangeHypothesis`로 생성
- baseline/variant paired experiment 구성
- blind human 결과와 효율 지표 비교
- project/series/global learning rule 후보 승격 또는 quarantine

### 내부 도구

- `learn.event_collect`
- `learn.failure_cluster`
- `learn.hypothesis_propose`
- `learn.paired_trial_build`
- `learn.scorecard_compute`
- `learn.rule_adjudicate`
- `learn.regression_suite_build`

---

## 5. 성능개선 폐루프 — 세 개의 시간축

## Loop A. Shot Repair Loop — 분 단위

```text
candidate 생성
→ 자동 결함·segment 분석
→ usable 구간 보존
→ 최소 repair delta
→ 영향 범위만 재생성/편집
→ 이전 승인 요소 회귀검사
```

목표:

- 전체 clip 재생성 감소
- `generated seconds / used seconds` 개선
- 좋은 연기·구도 손실 방지
- repair 한 번이 다른 승인 요소를 망가뜨리지 않게 함

종료 조건:

- 선택 가능한 usable interval 확보
- 전통 편집으로 해결 가능
- hard cap 도달 후 사람 판단
- provenance/권리/permission hard block

## Loop B. Project Editorial Loop — 시간·일 단위

```text
animatic
→ low-cost human direction
→ shot generation/select
→ rough cut A/B/C
→ actual first-viewer screening
→ missing coverage/meaning 진단
→ 필요한 scene만 수정
→ release candidate
```

목표:

- 개별 shot의 평균 점수가 아니라 전체 작품의 의미·리듬·감정 개선
- 제작자가 이미 아는 맥락 때문에 보지 못하는 혼란 탐지
- AI critic 예측과 실제 관객 반응의 차이 측정

필수 기록:

- unaided message recall
- remembered moments
- confusion/boredom timecodes
- felt emotion
- AI-like moments
- `critic_calibration_error`

## Loop C. Cross-Project Learning Loop — 작품 누적 단위

```text
project receipts
→ reusable observation 후보
→ project/series/global scope 분리
→ frozen baseline + paired variant
→ blind review + deterministic QA
→ promotion / project-only / unresolved / reject
→ 다음 작품 regression monitoring
```

목표:

- 한 작품의 우연을 전역 규칙으로 과잉학습하지 않기
- 모델 버전·장르·브랜드에 따라 갈리는 조건을 보존
- 품질을 유지하면서 사람 시간·생성비·재작업을 줄이기

---

## 6. Learning Unit과 승격 단계

### ChangeHypothesis

```yaml
hypothesis_id: HYP-PERF-012
scope: project | series | global
situation:
  stage: generation
  shot_type: reaction_closeup
problem:
  observed: "표정은 맞지만 반응이 자극보다 먼저 시작됨"
  evidence_ids: [OBS-...]
change_variable:
  name: reaction_latency
  baseline: 0.0-0.2s
  variant: 0.4-0.8s
locked_variables:
  - identity_reference
  - lens
  - lighting
  - dialogue
expected_effect:
  primary: performance_authenticity
  guardrails: [identity, continuity, editability]
trial_plan:
  representative_shots: 12
  candidates_per_lane: 4
  blind_order: crossed
promotion_gate: ...
```

### 규칙의 생애

| 상태 | 의미 | 사용 범위 |
|---|---|---|
| observation | 한 번 관찰된 현상 | 해당 shot 진단만 |
| project_preference | 동일 프로젝트에서 반복된 사람 선택 | 그 프로젝트만 |
| series_candidate | 같은 시리즈에서 재현된 가설 | paired trial 입력 |
| series_rule | blind 비교와 guardrail 통과 | 해당 시리즈 default |
| global_candidate | 장르·제품을 넘어 재현 가능성 | 새 holdout 필요 |
| global_rule | 독립 holdout에서도 품질·효율 통과 | 공통 default |
| quarantined | 조건 불명·상충·회귀 발생 | 자동 적용 금지 |

사람의 취향은 자동으로 global rule이 되지 않는다. 모델 버전이 바뀌면 관련 generation rule은 `revalidation_required`로 전환한다.

---

## 7. 품질·효율 Scorecard

### 결과물 품질 — 최우선

| 차원 | 측정 방법 | 자동화 권한 |
|---|---|---|
| Intent fidelity | locked promise·Shot Intent와 전체 cut 비교 | AI evidence + 인간 승인 |
| Narrative/payoff | 첫 시청 recall·인과·reveal 이해 | 실제 관객 필수 |
| Performance | blind A/B, reaction latency·시선·호흡 | 인간 최종 |
| Composition/POV | gaze order·lost context·crop test | AI 보조 + 인간 최종 |
| World/continuity | state diff + approved cheat | 자동 탐지, 예외는 인간 |
| Rhythm | fast/balanced/linger whole-cut 비교 | 인간 최종 |
| Sound meaning | loudness-matched mix, audio-only/picture-only | 인간 최종 |
| Culture/ethics | affected-group review, consent/disclosure | 인간 hard gate |
| Mechanical quality | codec, fps, duration, clipping, subtitle | 자동 결정 |

### 제작 효율 — 품질 guardrail 뒤에서만

- first-pass usable rate
- salvage yield = 사용한 초 / 생성한 초
- candidates per accepted shot
- partial-fix rate
- human minutes per finished minute
- compute minutes and cost per accepted second
- repeated question rate
- feedback translation correction rate
- retry·orphan·duplicate job rate

### 도구 자체 성능

각 Toolkit은 다음을 별도로 측정한다.

- artifact completeness
- deterministic validator pass rate
- human correction rate
- false-negative/false-positive defect rate
- downstream rework caused
- p50/p95 latency
- cost/compute
- version별 regression

도구가 더 빨라도 human correction과 downstream rework가 늘면 개선이 아니다.

---

## 8. Paired Improvement Trial

### 동결할 것

- 동일한 실제 shot identity와 input hash
- 동일한 model/runtime version
- 동일한 reference·duration·aspect·audio 조건
- 변경 변수 하나
- 동일한 후보 수와 retry budget
- blind review 순서와 scorecard
- no external publish

### 두 lane

```text
Lane A = 현재 승인된 제작 rule
Lane B = ChangeHypothesis 한 가지 적용
```

### 최소 초기 승격 기준 — 조정 가능한 설계값

**Project preference**

- 동일 방향의 사람 선택 3회 이상
- critical defect 0
- 프로젝트 밖 자동 적용 금지

**Series rule candidate**

- 대표 shot decision 12개 이상
- blind pairwise preference 60% 이상
- intent/performance/narrative 핵심 차원에서 하락 없음
- dimension score 하락이 0.25/5를 넘는 항목 0
- 효율 개선을 주장하려면 accepted-second 기준 시간·비용 15% 이상 개선

**Global rule candidate**

- 최소 2개 다른 프로젝트, 총 20개 이상 holdout shot decision
- 각 프로젝트에서 효과 방향이 일치
- 문화·브랜드·장르 특화 preference를 제거 또는 조건화
- 모델 버전·runtime을 manifest에 결박

작은 표본에서 단순 60%만으로 확정하지 않는다. 12-shot은 candidate gate이며, global 승격은 별도 unseen holdout이 필요하다.

### 실패 처리

- 품질 열화: reject 또는 scope 축소
- 결과 혼재: branch condition 추가
- critic과 사람 불일치: evaluator calibration issue
- 생성 성공률·비용만 악화: runtime/tool issue
- provenance·권리·공개 문제: hard block

---

## 9. 자동으로 바꿀 수 있는 것과 사람 승격이 필요한 것

### 자동 승격 가능

- 명백한 mechanical QA threshold
- 파일 누락·중복 submit·stale job recovery
- 결정론적 subtitle/audio/crop repair
- 결과를 바꾸지 않는 cache·batch·parallelism 개선

단, regression suite가 통과해야 한다.

### 사람 승인 후에만 승격

- prompt style·camera grammar·performance rule
- 후보 수·선택 방식
- story/reveal/edit rhythm
- music/silence policy
- defect acceptance policy
- critic threshold와 질문 축소
- series/global creative default

### 자동 승격 금지

- 문화·윤리·권리·공개 판단
- 실제 관객 반응을 AI simulation으로 대체
- 좋아요·CTR만을 이유로 작품 의도 변경
- 한 번 성공한 prompt를 global best practice로 등록

---

## 10. 필요한 데이터·artifact 저장 구조

```text
project/
├── brief/
│   ├── video-brief.json
│   └── quality-charter.json
├── evidence/
│   ├── claim-ledger.jsonl
│   └── rights-matrix.json
├── concepts/
├── story/
│   ├── beat-graph.json
│   └── subtext-map.json
├── look/
│   ├── style-bible.json
│   └── entity-state-manifest.json
├── shots/<shot-id>/
│   ├── intent-card.json
│   ├── attempts/<attempt-id>/
│   ├── segments.jsonl
│   ├── critiques.jsonl
│   └── decisions.jsonl
├── edits/<edit-id>/
│   ├── edl.json
│   ├── render-manifest.json
│   └── coverage-gaps.json
├── sound/
├── reviews/
├── release/
├── metrics/
└── learning/
    ├── observations.jsonl
    ├── hypotheses.jsonl
    ├── experiments/<experiment-id>/
    └── rules.jsonl
```

asset binary는 이 구조와 분리된 content-addressed store에 저장하고 SHA로 연결한다.

---

## 11. 도구를 만드는 순서 — 구현이 아니라 설계 의존성 기준

### Design Gate A — Creative contracts

- VideoBrief, HumanQualityCharter
- Claim Ledger
- Beat Graph/Subtext Map
- Look/World Bible
- Shot Intent Card
- G1–G10 outputs

### Design Gate B — Tool contracts

- 13개 Toolkit별 input/output/failure/side-effect contract
- idempotency와 artifact identity
- 자동 validator와 human authority
- fake/sample artifacts

### Design Gate C — Learning contracts

- event taxonomy
- scorecard
- ChangeHypothesis
- paired trial
- rule scope/promotion/revalidation

### Design Gate D — Runtime choices

- 실제 H3 local runtime discovery
- SQLite/event store schema
- Telegram media constraints
- FFmpeg/HyperFrames boundary
- CLI/MCP exposure

### 그 뒤 구현 순서

1. BriefKit + PrevisKit의 artifact compiler
2. GenerateKit adapter discovery/fake runtime
3. SelectKit evidence builder
4. ReviewKit packet/feedback loop
5. EditKit deterministic rough cut
6. SoundKit
7. LearnKit paired experiment manager
8. ReleaseKit
9. 얇은 MCP

이 순서는 “많이 구현된 시스템”보다 **한 shot이 의도→후보→사람 판단→부분 수정→학습까지 완주하는 vertical slice**를 먼저 만든다.

---

## 12. 설계 완료 조건

구현에 본격 진입하기 전에 다음이 모두 있어야 한다.

- S0–S12의 13개 stage 각각 자동화 작업·도구·입력·출력·검증·human gate 정의
- 13개 Toolkit의 tool inventory와 side-effect class
- 모든 canonical artifact의 schema 초안
- G1–G10의 실제 stage mapping
- H3 runtime discovery checklist
- sample project 1개의 artifact chain
- Shot/Project/Cross-project 3개 learning loop
- paired experiment와 rule 승격·rollback 계약
- 품질·효율·도구 성능 scorecard
- 외부 게시와 credential 경계

이 조건을 통과한 뒤에만 구현 큐를 확장한다.

## 관련 문서

- [[projects/ai-video-production-pipeline/pipeline-schema|파이프라인 스키마]]
- [[projects/ai-video-production-pipeline/professional-human-gates-research-2026-08-23|영화 전문직 판단→Human Gate 연구]]
- [[projects/ai-video-production-pipeline/human-judgment-for-video-quality-2026-08-23|AI가 취약한 품질 판단 연구]]
- [[projects/ai-video-production-pipeline/human-ai-video-methodology-2026-08-22|인간-AI 공동 제작 방법론]]
- [[projects/ai-video-production-pipeline/mcp-cli-pipeline-research-2026-08-22|MCP·CLI·파이프라인 연구]]
