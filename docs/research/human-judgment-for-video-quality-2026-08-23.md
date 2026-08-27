# AI 영상 품질을 높이는 인간 판단 연구

> 작성일: 2026-08-23  
> 적용 환경: GPT Pro + GPT Image API + 로컬 MiniMax H3, 768p  
> 질문: AI가 현재 무엇을 잘 판단하지 못하며, 결과물의 품질을 높이려면 사람이 어떤 역량과 판단 작업을 맡아야 하는가?

## 0. 결론

현재 AI는 **명시된 기준을 검사하고 후보 차이를 설명하는 일**에는 유용하지만, 다음 네 가지를 스스로 확정하기에는 아직 위험하다.

1. **무엇이 중요한가** — 작품의 의도, 남길 감정, 장면의 존재 이유
2. **무엇이 진짜처럼 느껴지는가** — 연기의 진정성, 말하지 않은 감정, 미세한 어색함
3. **어떤 결함을 감수할 가치가 있는가** — 기술적으로 깨끗한 평범한 장면과 작은 결함이 있지만 강한 장면 사이의 선택
4. **관객이 시간 속에서 무엇을 경험하는가** — 리듬, 지루함, 긴장, 정보량, 여운, 사운드의 정서적 효과

따라서 사람을 단순한 최종 승인자로 두면 늦다. 사람은 다음 역할을 맡아야 한다.

- **의도 설계자:** 무엇을 말하고 무엇을 남길지 결정
- **취향 편집자:** 보기 좋은 것과 이 작품에 맞는 것을 구분
- **연기 감독:** 표정·시선·몸짓의 동기와 진정성 판단
- **리듬 편집자:** 언제 보여주고 언제 자르며 언제 침묵할지 결정
- **맥락 판정자:** 브랜드·문화·사실·윤리·대상 관객에 적합한지 판단
- **결함 예산 관리자:** 무엇은 고치고 무엇은 살려둘지 우선순위 결정

핵심 운영 원칙은 다음 한 문장이다.

> **AI는 결함을 찾고 선택지를 준비하지만, 사람은 작품의 의미와 우선순위를 결정한다.**

---

## 1. 연구 범위

이번 연구는 기존에 전체 transcript를 close-read한 AI 영상 제작 workflow 15편을 품질 판단 관점에서 다시 읽은 결과를 기반으로 한다.

- `신비한 건축사전` 재현·역추론과 집중 workflow 8편
- 2025-08 이후 20분 이상 장시간 실무 workflow 7편, 총 3시간 24분
- 합계 15편

반복해서 확인된 사람의 행동은 다음과 같다.

- AI가 만든 주제 중 영상으로 작동할 것을 고른다.
- AI 대본을 사실성뿐 아니라 흥미·말맛·인간미 기준으로 다시 쓴다.
- 캐릭터·공간이 ‘맞게 생겼는지’가 아니라 역할과 장면에 맞는지 casting한다.
- 기술적으로 성공한 이미지도 생명력이 없거나 브랜드와 맞지 않으면 버린다.
- 같은 shot을 여러 번 생성하고 전체 clip이 아니라 좋은 순간만 고른다.
- 표정·시선·침묵·카메라 timing을 0.5초 단위로 조절한다.
- 편집 중 장면이 아름다워도 이야기에 기능이 없으면 삭제한다.
- 네이티브 생성 음향을 그대로 쓰지 않고 Foley·ambience·음악·침묵을 다시 구성한다.

이는 인간의 역할이 prompt 작성자가 아니라 **판단 기준의 소유자**임을 보여준다.

### 최신 평가 연구가 보여주는 추가 한계

실무 영상에서 관찰한 문제는 최신 멀티모달 평가 연구와도 맞물린다.

- **평가 모델은 중립적인 심판이 아니다.** TMLR 2026 연구는 여러 LLM judge에서 style bias가 `0.10–0.76`으로 position bias(`≤0.04`)보다 컸고, 장황함 선호도 모델별로 방향이 달랐다고 보고한다. 즉 더 그럴듯하게 포장된 비평이나 후보가 실제 내용보다 높게 평가될 수 있다.[1]
- **자기 계열 결과를 선호할 수 있다.** 12개 MLLM에서 수집한 129만 caption-score pair 연구는 대표 MLLM judge의 self-preference와 일부 model-family 상호 선호를 보고했다.[2] 텍스트 영역에서도 evaluator가 자기 생성을 알아보고 인간이 동등하게 본 결과보다 높게 평가하는 현상이 확인됐다.[3] 따라서 생성한 GPT가 같은 context로 자기 결과를 최종 승인하면 안 된다.
- **후보 순서와 언어가 판단을 바꾼다.** 다국어 LVLM reward benchmark는 답변 순서를 뒤집어 position bias를 측정했고, 모델·언어에 따라 편향과 분산이 달라졌다.[4] A/B 후보는 순서를 무작위화하고 swap 평가를 해야 한다.
- **긴 영상의 동기·인과·주제는 아직 어렵다.** Video-Holmes는 의도·동기 연결, 비연속 사건의 인과, timeline, physical anomaly, core theme을 함께 묻는데 당시 최고 모델 Gemini-2.5-Pro도 전체 정확도 45%에 머물렀다.[5] NARU도 155편·146.8시간의 일본 장편 영상에서 서사 진화와 문화적 뉘앙스를 별도 평가 대상으로 둔다.[6] 프레임 몇 장의 점수로 전체 리듬과 의미를 확정하면 안 된다.
- **시각적으로 그럴듯해도 문화적으로 틀릴 수 있다.** CultureVidBench는 일반적인 prompt 일치·realism과 문화적 사물·행동·의식·문자·음향의 충실도를 분리한다. 자동 evaluator와 사람의 상관도도 차원별 편차가 크며, 문화적 평가를 일반 visual-quality 점수로 대체할 수 없음을 보여준다.[7]
- **전문 evaluator도 사람을 완전히 대체하지 않는다.** PersonaShot의 기준별 evaluator는 전문가 MOS와 물리 aggregate `ρ=0.75`, cinematic aggregate `ρ=0.73` 수준이었고, eyeline match의 pairwise agreement는 `67.2%`였다. 연구 자체도 10명의 전문가가 25개 multi-shot sequence를 평가해 기준을 검증했다.[8] 좋은 evaluator는 사람 판단을 줄여주는 triage 도구이지 최종 권위가 아니다.

**운영 결론:** AI 점수는 `자동 통과 증명`이 아니라 `사람이 볼 후보와 근거를 줄이는 검색 신호`로 사용한다.

#### 실제로 어느 정도 흔들리는가

| 취약점 | 확인된 수치 | 품질 운영 규칙 |
|---|---:|---|
| 사람과의 불일치 | PersonaShot 전문 evaluator도 pairwise agreement가 physical 75.2%, affective 70.3%, cinematic 72.8%; 얼굴 동역학 64.8%, eyeline 67.2%[8] | hero take·미세 연기·eyeline·최종 cut은 인간 승인 |
| 후보 순서 편향 | MJ-Bench에서 순서를 뒤집자 Qwen-VL-Chat alignment 31.1→73.0, InternVL-chat 75.8→34.8[9] | 중요한 비교는 `AB`와 `BA` 모두 평가; winner가 바뀌면 tie |
| 미세 물리 판단 | WorldReasonBench에서 인간 점수 차가 0.5 이하인 close pair의 일반 VLM judge 정확도 47.5%[10] | 손·접촉·관성·시선·lip-sync는 원속도와 0.5×로 인간 확인 |
| 긴 서사 | NARU 최고 모델도 76.2%, open model은 29.6–39.8%; sequential flow는 8개 중 7개 모델에서 가장 약한 서사 범주[6] | sparse frame만으로 승인 금지; full cut·shot boundary·state ledger 병행 |
| 관객 감정 예측 | 광고 viewer sentiment의 zero-shot GPT-4o clean-label 정확도 21.3%; task-specific 학습 후에도 39.6–40.4%[11] | 감정 라벨을 연기 진정성·관객 반응으로 대체하지 않음 |
| 문화·미학 | CultureVidBench에서 일부 최신 judge의 human correlation이 realism ρ=0.235–0.441, visual quality ρ=0.125–0.440[7] | 문화 특정 장면은 해당 문화·언어의 실제 검토자가 승인 |

2026 자료 대부분은 저자 공개 공식 benchmark이지만 **동료심사 전 arXiv 프리프린트**다. 방향성과 운영상 경고로 사용하되 공급사 성능 보증으로 해석하지 않는다. style/verbosity 연구[1]는 TMLR 게재 논문이며, 영상 미학 자체보다 **영상 후보를 설명·비평·랭킹하는 인터페이스의 구조적 위험**에 적용한다.

---

## 2. AI가 상대적으로 잘 판단하는 것

먼저 사람에게 맡길 필요가 없는 영역을 분리해야 한다.

| 영역 | AI·코드가 잘하는 판단 | 운영 방식 |
|---|---|---|
| 파일·출력 | 해상도, fps, codec, 길이, 누락, 손상 | 결정론적 코드로 자동 차단 |
| 음향 기술 | clipping, 무음, loudness, 대사 구간, sync 후보 | 자동 검사 후 repair |
| 명시적 연속성 | 의상 색, 소품 유무, 화면 방향, 시작·종료 상태 | reference와 비교해 위반 후보 표시 |
| 형태 결함 | 손·얼굴·문자·로고·중복 개체·큰 flicker | 자동 탈락 후보 생성 |
| 계약 준수 | Shot Contract에 요구한 대상·행동·카메라가 존재하는가 | hard constraint 검사 |
| 후보 요약 | A/B/C의 차이와 발견된 결함 설명 | 사람이 비교하기 쉬운 packet 생성 |
| 저위험 편집 | 블랙·무음·중복 프레임 제거, 포맷 변환 | 자동 처리, 되돌리기 가능하게 기록 |

단, 여기서도 AI의 판정은 **후보 탐지**다. 작은 오류가 의도된 표현인지, 장면 전체의 힘보다 중요한지는 사람이 결정할 수 있다.

---

## 3. AI가 현재 잘 판단하지 못하는 10가지

### 3.1 작품의 진짜 성공 기준

**AI의 약점**  
AI는 주어진 brief와의 일치를 평가할 수 있지만, 어떤 brief가 이 작품과 관객에게 가치 있는지는 스스로 알지 못한다. ‘정보 전달’, ‘감정’, ‘브랜드 기억’, ‘새로움’이 충돌하면 평균적인 타협안을 선호하기 쉽다.

**사람이 보는 신호**
- 영상이 끝난 뒤 관객에게 남아야 할 한 문장과 감정
- 이번 작품이 다른 비슷한 AI 영상과 달라야 하는 이유
- 조회수보다 더 중요한 브랜드·신뢰·작품 목표

**필요한 역량**: Creative direction, 문제 정의, 우선순위 판단

**사람의 결정**
- 무엇을 가장 먼저 지킬 것인가
- 무엇을 희생해도 되는가
- 어떤 감정·주장·이미지는 절대 바꾸지 않을 것인가

**AI가 준비할 자료**: 서로 실제로 다른 방향 3개, 각 방향의 기대 효과·손실·생성 위험

**질문 예시**  
“정보 이해가 빠른 A와 감정의 여운이 강한 B 중 이번 영상의 1순위는 무엇입니까?”

**생략 시 위험**: 기술적으로 매끈하지만 아무 말도 하지 않는 영상

---

### 3.2 ‘예쁜 것’과 ‘맞는 것’의 구분

**AI의 약점**  
AI evaluator는 선명도, 구도, 조명, 디테일처럼 쉽게 언어화되는 미적 신호를 높게 평가하기 쉽다. 그러나 고급스럽지만 차갑거나, 시네마틱하지만 주제를 가리거나, 멋있지만 익숙한 AI look일 수 있다.

**사람이 보는 신호**
- 이미지가 작품의 세계관과 정서에 속하는가
- 조명·렌즈·색이 메시지를 돕는가, 자신만 과시하는가
- 의도된 절제와 단순한 밋밋함의 차이
- 흠이 있어도 기억에 남는가

**필요한 역량**: Art direction, visual taste, 비교·선별 능력

**사람의 결정**: Hero frame, palette, lens grammar, 질감, intentional imperfection

**AI가 준비할 자료**: 같은 내용의 look A/B/C, 무보정 contact sheet, 스타일 차이와 cliché 위험

**질문 예시**  
“A는 완성도가 높지만 광고처럼 보이고, B는 거칠지만 다큐멘터리의 진정성이 있습니다. 어느 쪽을 지킬까요?”

**생략 시 위험**: 평균적으로 보기 좋지만 브랜드와 작품의 고유성이 사라짐

---

### 3.3 서브텍스트와 연기의 진정성

**AI의 약점**  
표정이 ‘슬픔’으로 분류된다고 해서 인물이 정말 슬퍼 보이는 것은 아니다. 감정은 시선 회피, 호흡, 망설임, 말과 몸짓의 불일치, 상대에게 반응하는 timing처럼 장면 전체의 동기에서 나온다. AI는 과장된 표정을 감정 전달 성공으로 오인하거나, 미세하지만 결정적인 어색함을 지나칠 수 있다.

**사람이 보는 신호**
- 인물이 왜 지금 이 행동을 하는지 느껴지는가
- 말한 감정과 몸이 보여주는 감정이 의도적으로 일치·충돌하는가
- 상대의 행동을 실제로 듣고 반응하는 것처럼 보이는가
- 작은 eye movement·호흡·pause가 살아 있는가

**필요한 역량**: Performance direction, 배우 관찰, 인간 행동의 미세한 인과 감지

**사람의 결정**: 감정 강도, 시선, pause, gesture, take 선택

**AI가 준비할 자료**: 동일 대사의 연기 강도 3단계, 표정·시선·호흡·대사 timing 비교

**질문 예시**  
“B는 표정이 더 강하지만 연기한 티가 납니다. A의 절제된 표정을 유지하고 마지막 시선만 B처럼 바꿀까요?”

**생략 시 위험**: 감정은 보이지만 믿기지 않는 ‘AI 연기’

---

### 3.4 장면의 서사적 기능

**AI의 약점**  
각 shot을 개별적으로 평가하면 아름다운 shot이 높은 점수를 받는다. 하지만 전체 이야기 안에서는 이미 아는 정보를 반복하거나, 긴장을 끊거나, 중요한 reveal을 너무 일찍 보여줄 수 있다.

**사람이 보는 신호**
- 이 shot이 새 정보·감정·관계를 추가하는가
- 이 shot을 빼면 무엇이 사라지는가
- 관객이 알아야 할 것과 아직 몰라야 할 것이 구분되는가
- ambiguity가 의도된 것인지 설명 부족인지

**필요한 역량**: Story editing, causal reasoning, information architecture

**사람의 결정**: 유지·삭제·순서 변경·reveal timing·missing coverage

**AI가 준비할 자료**: 각 shot의 기능 라벨, 삭제 전후 story graph, 관객이 아는 정보의 시간표

**질문 예시**  
“S04는 아름답지만 새 정보를 주지 않습니다. 삭제해 리듬을 빠르게 할까요, 분위기를 위해 1.2초만 남길까요?”

**생략 시 위험**: 멋진 장면의 나열이지만 이야기는 느리거나 불명확함

---

### 3.5 편집 리듬과 관객의 체감 시간

**AI의 약점**  
리듬은 평균 shot 길이만으로 결정되지 않는다. 같은 3초도 정보가 많으면 짧고, 감정이 끝났는데 유지하면 길다. 긴장·이완·예상·보상은 실제로 처음부터 끝까지 보며 체감해야 한다.

**사람이 보는 신호**
- 시선이 화면을 읽을 시간을 얻었는가
- 감정이 도착하기 전에 잘렸거나 끝난 뒤에도 늘어지는가
- 반복이 의도적 motif인지 단순 중복인지
- 침묵이 긴장인지 공백인지

**필요한 역량**: Film editing, temporal attention, 관객 대리 시청

**사람의 결정**: frame-accurate cut point, hold length, montage density, pause

**AI가 준비할 자료**: 빠른 cut A·중간 B·여운 C, 정보 밀도·발화 경계·감정 peak 표시

**질문 예시**  
“A는 이해가 빠르고 B는 표정이 0.8초 더 남아 여운이 큽니다. 이번 장면은 속도와 여운 중 무엇을 우선할까요?”

**생략 시 위험**: 모든 shot은 괜찮지만 전체가 지루하거나 숨 돌릴 틈이 없음

---

### 3.6 사운드의 정서적 기능

**AI의 약점**  
AI는 음량·sync·대사 명료도를 검사할 수 있지만, 음악이 감정을 너무 설명하는지, 침묵이 더 강한지, 화면과 반대로 흐르는 사운드가 더 의미 있는지는 확정하기 어렵다.

**사람이 보는 신호**
- 사운드가 이미 보이는 감정을 중복 설명하는가
- 공간음과 Foley가 화면에 물성을 주는가
- 음악 진입이 관객의 감정을 조작하는 티가 나는가
- silence가 의도적 긴장으로 유지되는가

**필요한 역량**: Sound direction, 청각적 감정 설계, 음악적 절제

**사람의 결정**: music/no music, 진입 시점, 강도, Foley 강조, counterpoint

**AI가 준비할 자료**: 무음 A·환경음 B·음악 C, loudness 정규화된 blind 비교

**질문 예시**  
“B는 감정을 명확히 하지만 다소 설명적입니다. 음악을 빼고 호흡과 공간음만 남길까요?”

**생략 시 위험**: 영상은 좋아도 값싼 광고처럼 느껴지거나 감정이 과잉 지시됨

---

### 3.7 문화·브랜드·관객 맥락

**AI의 약점**  
학습 데이터의 일반적 패턴은 특정 시청자 집단의 기억, 금기, 유머, 언어의 온도, 브랜드 역사와 다를 수 있다. ‘안전함’과 ‘적합함’도 같지 않다.

**사람이 보는 신호**
- 특정 표현이 대상 관객에게 촌스럽거나 모욕적이지 않은가
- 장면이 브랜드의 기존 태도와 충돌하지 않는가
- 유머와 감정이 번역될 때 의미가 달라지지 않는가
- 실제 사람·장소·역사를 소비 가능한 이미지로만 다루지 않는가

**필요한 역량**: Cultural literacy, audience empathy, brand stewardship

**사람의 결정**: 표현 허용·수정·제외, 대상 관객별 version, 공개 범위

**AI가 준비할 자료**: 위험 표현과 이유, 이해관계자 관점, 대체 표현 2–3개

**질문 예시**  
“이 장면은 강렬하지만 실제 재난 이미지를 연상시킬 수 있습니다. 직접 표현·완곡 표현·삭제 중 어느 쪽이 맞습니까?”

**생략 시 위험**: 기술적으로 안전하지만 맥락상 부적절하거나 브랜드 신뢰를 훼손

---

### 3.8 새로움과 cliché

**AI의 약점**  
생성·평가 모델 모두 학습 데이터에서 자주 본 표현을 유창하고 ‘완성된’ 것으로 선호할 수 있다. 그래서 lens flare, slow push-in, 과도한 shallow depth, 웅장한 riser처럼 익숙한 AI 영상 문법이 반복된다.

**사람이 보는 신호**
- 다른 AI 영상과 구분되는가
- 효과가 이야기 때문에 존재하는가
- 낯섦이 단순 오류인지 새로운 언어인지
- 익숙함을 의도적으로 쓸 이유가 있는가

**필요한 역량**: Originality judgment, reference literacy, cliché detection

**사람의 결정**: cliché 허용·반전·제거, 시각·편집·음향 규칙의 차별화

**AI가 준비할 자료**: reference 유사성, 흔한 표현 목록, cliché를 제거한 대안

**질문 예시**  
“A는 안정적이지만 전형적인 AI 광고 문법입니다. B의 낯선 고정 구도를 유지할까요?”

**생략 시 위험**: 품질은 높아 보이지만 기억에 남지 않고 생성형 콘텐츠 티가 남

---

### 3.9 결함의 우선순위와 trade-off

**AI의 약점**  
점수 합산은 작은 여러 결함이 하나의 강력한 장점을 압도하거나, 반대로 치명적인 정체성 오류가 평균에 묻히게 한다. 작품에서는 결함의 수보다 의미와 영향이 중요하다.

**사람이 보는 신호**
- 관객이 실제로 알아챌 결함인가
- 알아채면 신뢰·감정·정보를 무너뜨리는가
- 강한 연기나 구도를 잃지 않고 고칠 수 있는가
- 수정 비용과 새로운 오류 위험이 얼마인가

**필요한 역량**: Editorial judgment, quality triage, risk–reward 판단

**사람의 결정**: accept / trim / repair / regenerate / abandon

**AI가 준비할 자료**: 결함 위치, 관객 노출 시간, 최소 수정, 부작용, 재생성 비용

**질문 예시**  
“B는 최고의 연기지만 끝 0.4초 손 오류가 있습니다. 그 구간만 자를까요, 연기까지 잃을 위험을 감수하고 재생성할까요?”

**생략 시 위험**: 완벽주의로 좋은 take를 버리거나, 치명적 오류를 평균 점수로 통과시킴

---

### 3.10 최종 관객 반응

**AI의 약점**  
AI critic은 관객을 흉내 낼 수 있지만 실제 관객의 주의, 이해, 감정, 기억을 측정하지 않는다. 같은 모델로 만들고 평가하면 같은 맹점을 공유할 가능성도 있다.

**사람이 보는 신호**
- 처음 본 사람이 핵심을 자신의 말로 설명하는가
- 어디서 지루해하거나 오해하는가
- 무엇을 기억하고 무엇을 놓치는가
- 의도한 감정과 실제 감정이 일치하는가

**필요한 역량**: Audience research, 관찰, 피드백 해석

**사람의 결정**: 실제 공개 전 수정, target별 버전, 성공 기준 보정

**AI가 준비할 자료**: blind test 질문, 응답 요약, 이탈·재시청·오해 지점

**질문 예시**  
“5명 중 3명이 반전을 이해하지 못했습니다. 설명 shot을 추가할까요, 현재의 모호함을 작품 의도로 유지할까요?”

**생략 시 위험**: 내부 평가에서는 높은 점수지만 실제 관객에게 작동하지 않음

---

## 4. 필요한 인간 역량 지도

| 인간 역할 | 고유 역량 | 핵심 판단 작업 | 시스템에서의 위치 |
|---|---|---|---|
| Creative Director | 목적·취향·우선순위 | 한 문장 약속, 감정, anti-goal 잠금 | 생성 전 Direction Gate |
| Story Editor | 인과·정보 공개·subtext | shot 기능, reveal, ambiguity | storyboard·rough cut |
| Art Director | 세계관·구도·색·질감 | hero frame, look bible, casting | GPT Image 생성 후 |
| Performance Director | 인간 행동·동기 관찰 | 표정·시선·호흡·gesture·take | H3 후보 선택 |
| Continuity Supervisor | 상태·공간·행동 기억 | 정체성·소품·광원·동선 | shot 전후 자동검사+예외 |
| Film Editor | 체감 시간·생략·리듬 | frame-accurate cut, hold, montage | rough cut A/B |
| Sound Director | 청각적 감정·물성 | music, Foley, ambience, silence | picture lock 전후 |
| Cultural/Brand Editor | 맥락·대상 관객·책임 | 어조, 금기, 사실·브랜드 적합성 | 기획·최종 공개 |
| Quality Triage Lead | trade-off·수정비용 | 살릴 결함과 버릴 결함 | candidate board·revision |
| Audience Researcher | 실제 반응 관찰 | 이해·감정·기억·이탈 분석 | 파일럿·최종 평가 |

한 사람이 여러 역할을 맡을 수 있다. 중요한 것은 사람 수가 아니라 **판단 렌즈를 구분하는 것**이다.

### 4.1 영화 전문직의 판단을 G1–G10으로 구현한다

Yale Film Analysis와 Film Independent의 실무 인터뷰·마스터클래스를 조사해 감독·촬영·편집·연기 판단을 gate로 번역했다.[12][13]

문화·윤리·책임 경계에는 CMSI 다큐 윤리 연구와 BFI Diversity Standards를 사용했다.[14][15] 전체 전문 출처는 세부 연구 문서에 14개가 정리돼 있다.

| Gate | 인간이 판단하는 핵심 | AI가 준비해야 할 비교자료 |
|---|---|---|
| G1 의도·장면 기능 | 무엇이 바뀌며, 무엇을 언제 공개할 것인가 | 현재 cut vs shot 삭제 cut, audience-knowledge 표 |
| G2 Subtext | 말과 숨은 목적의 간극을 언제 관객이 알아야 하는가 | literal/concealing/testing take, 시선·호흡·pause 타임라인 |
| G3 Performance | 자극→인지→억제/반응이 실제처럼 살아 있는가 | 동기화 blind A/B/C, strongest/unusable interval |
| G4 Composition·POV | 누구의 경험을 어떤 거리·순서로 보게 할 것인가 | wide/medium/close, static/move, crop overlay |
| G5 Production design | 공간·재료·소품이 인물의 역사와 세계 인과를 지지하는가 | location plan, material/prop board, state variants |
| G6 Continuity·의도적 위반 | 물리 오류를 고칠지, 감정 continuity를 위해 허용할지 | exit/entry frame diff, fix/hide/accept 옵션 |
| G7 Pacing·cut point | 감정이 도착하는 frame과 떠나야 할 frame은 어디인가 | fast/balanced/linger blind cut, music-off pass |
| G8 Sound meaning | 누구의 귀로 듣고, 무엇을 의도적으로 들리지 않게 할 것인가 | dry/world/subjective/music-led loudness-matched mix |
| G9 Audience comprehension | 처음 본 관객이 실제로 무엇을 이해·기억·오해했는가 | unaided recall, confusion/boredom timecode, mismatch map |
| G10 Culture·ethics | 누구에게 어떤 책임을 지며 공개해도 되는가 | 당사자 관점, consent 범위, harm/benefit, disclosure 옵션 |

중요한 차이는 **continuity도 무조건 맞추는 규칙이 아니라는 것**이다. 전문 편집자는 공간 정확성을 감정·극적 공간을 위해 깨뜨릴 수 있고, 감독은 더 매끈한 take보다 우발성과 진실성이 살아 있는 take를 선택할 수 있다.[12][13] 사람은 규칙 검사자가 아니라 **어떤 규칙을 왜 깨도 되는지 승인하는 사람**이다.

세부 신호·질문·출력 필드는 [[projects/ai-video-production-pipeline/professional-human-gates-research-2026-08-23|영화 전문직 판단→AI 영상 human gate 연구]]에 정리했다.

---

## 5. AI 판단을 신뢰하는 수준

### 자동 실행 가능

- 명확하고 기계적인 규칙
- 가역적이며 수정 비용이 낮은 결정
- 기존에 사용자가 잠근 Creative Charter로 답이 명확한 결정
- 결과와 근거를 사후 복구할 수 있는 결정

### AI 추천 + 사람은 예외만 확인

- 연속성·형태·화면/대사 일치
- B-roll·연결 shot 선택
- 작은 trim·crop·속도 조정
- 여러 critic이 같은 결론이고 영향 범위가 작을 때

### 반드시 사람이 결정

- 작품의 방향과 성공 기준
- Hero shot·인물 casting·핵심 연기
- 스토리 의미를 바꾸는 삭제·순서 변경
- 음악 정체성·감정 강도·침묵
- 문화·브랜드·사실·권리
- 높은 점수 후보 사이의 미학적 선택
- 결함을 감수할지 작품의 강점을 버릴지
- 최종 공개

---

## 6. 인간에게 물어야 할 순간

단순히 AI confidence가 낮을 때만 묻지 않는다. 다음 값을 함께 본다.

```text
HUMAN_REVIEW_PRIORITY =
  작품 영향도
× 판단의 모호성
× 뒤늦게 고칠 비용
× 기존 인간 결정과 충돌 정도
× 실제 관객·브랜드 위험
```

다음 중 하나면 사람을 호출한다.

1. critic끼리 결론이 다르다.
2. hard rule은 통과했지만 미학적 우열이 근접하다.
3. 인물·제품·브랜드의 정체성이 바뀐다.
4. 장면 삭제가 이야기의 의미를 바꾼다.
5. 연기·감정·유머·문화처럼 맥락 의존성이 높다.
6. 수정하면 이미 좋은 요소를 잃을 위험이 있다.
7. 이후 여러 shot의 기준이 되는 비가역 결정이다.
8. 실제 관객 반응이 AI 예상과 다르다.

질문은 생성 실패 후가 아니라 **비싼 후속 작업 전에** 한다.

---

## 7. 좋은 인간 질문의 형식

나쁜 질문:

- “괜찮나요?”
- “어떤가요?”
- “다시 만들까요?”

좋은 질문은 7개 요소를 가진다.

1. 장면의 목적
2. 잠긴 기준
3. 선택지 A/B/C
4. 각 선택지의 강점
5. 각 선택지의 손실
6. AI 추천과 확신
7. 다음 작업에 미치는 영향

```text
[S07 연기 선택]

목적: 주인공이 처음으로 구조의 위험을 깨닫는 순간
잠긴 기준: 과장 금지, 대사보다 시선과 호흡 우선

A — 표정은 절제됨 / 시선 전환이 늦음
B — 감정은 명확함 / 연기한 티가 남
C — A의 표정 / B의 빠른 시선 전환

AI 추천: C
이유: 장면 목적과 절제 규칙을 함께 만족
불확실성: ‘절제’와 ‘명료함’ 중 취향 선택이 남음

선택: A / B / C / “A에서 시선만 0.3초 빠르게”
```

---

## 8. 사람의 판단을 다음 생성에 반영하는 계약

사람의 자유 텍스트를 그대로 prompt에 덧붙이면 기준이 흔들린다. 다음 구조로 번역한다.

```yaml
decision_id: HD-S07-03
scope: shot            # shot | scene | project | series
human_intent: "표정은 절제하되 깨달음은 더 빨리 읽혀야 함"
keep:
  - identity
  - subdued_expression
  - lighting
change:
  eye_shift_start_sec: -0.3
  camera_move: locked_off
forbid:
  - exaggerated_frown
  - dramatic_push_in
priority_order:
  - performance_authenticity
  - narrative_clarity
  - visual_polish
accepted_defects:
  - "끝 0.2초 손가락 결함은 trim 전제 허용"
regeneration_scope: S07_only
verification_question: "시선 이동이 빨라졌지만 절제된 표정은 유지됐는가?"
```

중요한 필드는 `accepted_defects`와 `priority_order`다. AI는 무엇을 바꿀지만 아니라 **무엇을 지키고 어떤 결함을 감수하는지** 알아야 한다.

---

## 9. 품질 중심 평가 방법

### 9.1 AI 점수 하나를 금지

다음 축을 분리한다.

- Intent fidelity
- Narrative function
- Performance authenticity
- Visual authorship
- Continuity
- Edit rhythm
- Sound function
- Cultural/brand fit
- Audience comprehension
- Memorability

평균 점수로 hard failure를 숨기지 않는다. `정체성·사실·권리·핵심 의미`는 별도 차단 조건이다.

### 9.2 평가자에게 생성 과정을 숨긴다

생성 agent가 자기 결과를 평가하면 자기합리화가 생길 수 있다. 비평 pass에는 다음만 제공한다.

- 잠긴 brief
- 후보 결과
- reference
- 평가 rubric

prompt 작성 과정과 생성 agent의 변명은 제공하지 않는다.

### 9.3 Pairwise blind review

숫자 점수보다 A/B 비교를 우선한다.

- 후보 순서를 무작위화
- 모델·seed·생성 횟수 숨김
- loudness와 화면 크기 정규화
- “어느 것이 더 예쁜가” 대신 목적별 질문
- 한 번 본 반응과 반복 시청 판단을 구분

### 9.4 실제 관객 검증

최소 5명에게 다음을 묻는다.

1. 영상의 핵심을 한 문장으로 말해달라.
2. 가장 기억나는 장면은 무엇인가.
3. 지루하거나 혼란스러운 지점은 어디인가.
4. 어떤 감정을 느꼈는가.
5. 무엇이 AI 생성처럼 어색했는가.

AI 예상과 실제 응답의 차이를 `critic calibration error`로 기록한다.

### 9.5 품질 개선 지표

- 인간 blind A/B 승률
- 의도한 감정 일치율
- 핵심 메시지 회상률
- 연기 어색함 지적/분
- 기능 없는 shot 비율
- continuity hard error
- 최종본까지 살아남은 hero take 비율
- accepted defect가 실제 관객에게 발견된 비율
- 늦게 발견된 고비용 방향 수정 횟수
- 같은 인간 판단을 다시 물은 비율

---

## 10. 권장 파일럿

동일한 30–60초 brief로 세 정책을 비교한다.

| 정책 | 설명 |
|---|---|
| AI-only | AI critic과 점수만으로 선택 |
| Fixed gates | 방향·Look·편집·공개에서 사람 승인 |
| Quality-risk gated | 고정 gate + 연기·미학·trade-off·critic 충돌 시 동적 질문 |

### 통제 조건

- 같은 script, reference, H3 설정, 후보 예산
- 후보 순서 무작위
- 평가자는 정책을 모름
- 동일한 화면·음량 조건
- 사람 판단 시간과 GPU 비용 모두 기록

### 성공 판정

`Quality-risk gated`가 다음을 만족해야 한다.

- AI-only보다 blind 품질 선호가 높다.
- Fixed gates보다 사람 시간은 적거나 비슷하다.
- 연기·리듬·의도·문화 오류가 줄어든다.
- 늦은 전체 재작업이 줄어든다.
- 같은 질문이 두 번째 영상에서 감소한다.

---

## 11. 최종 권고

이 프로젝트에서 가장 먼저 구현할 것은 더 강한 자동 evaluator가 아니다.

1. **Human Quality Charter** — 사람이 지키려는 의미·감정·취향·금지조건
2. **Judgment Packet** — 사람이 비교 가능한 A/B/C와 trade-off
3. **Decision Delta** — 선택을 `keep/change/forbid/priority/accepted_defects`로 변환
4. **Independent Critic Pass** — 생성 agent와 분리된 비평
5. **Audience Calibration** — 실제 사람 반응과 AI 판단의 차이 기록

좋은 결과를 만드는 인간의 핵심 역량은 ‘AI보다 프롬프트를 잘 쓰는 것’이 아니다.

> **무엇을 느껴야 하는지 정하고, 미묘한 어색함을 감지하고, 여러 장단점 중 무엇을 지킬지 선택하며, 그 판단을 다음 제작 규칙으로 만드는 능력이다.**

## Sources

[1] https://arxiv.org/abs/2604.23178 — Judging the Judges
[2] https://arxiv.org/abs/2604.11589 — MLLM-as-a-Judge Exhibits Model Preference Bias
[3] https://arxiv.org/abs/2404.13076 — LLM Evaluators Recognize and Favor Their Own Generations
[4] https://arxiv.org/abs/2604.19405 — Lost in Translation: Do LVLM Judges Generalize Across Languages?
[5] https://arxiv.org/abs/2505.21374 — Video-Holmes
[6] https://arxiv.org/abs/2608.13210 — NARU
[7] https://arxiv.org/abs/2608.01942 — CultureVidBench
[8] https://arxiv.org/abs/2608.16717 — PersonaShot
[9] https://arxiv.org/abs/2407.04842 — MJ-Bench
[10] https://arxiv.org/abs/2605.10434 — WorldReasonBench
[11] https://arxiv.org/abs/2606.16198 — GRACE viewer sentiment
[12] https://filmanalysis.yale.edu/editing — Yale Film Analysis: Editing
[13] https://www.filmindependent.org/blog/how-to-get-great-performances-out-of-actors-a-directors-toolkit — Film Independent: Director's Toolkit
[14] https://cmsimpact.org/resource/honest-truths-documentary-filmmakers-on-ethical-challenges-in-their-work — CMSI: Documentary Ethics
[15] https://www.bfi.org.uk/inclusion-film-industry/bfi-diversity-standards — BFI Diversity Standards

## 관련 문서

- [[projects/ai-video-production-pipeline/human-ai-video-methodology-2026-08-22|인간-AI 공동 제작형 AI 영상 방법론]]
- [[projects/ai-video-production-pipeline/professional-human-gates-research-2026-08-23|영화 전문직 판단→AI 영상 human gate 연구]]
- [[projects/ai-video-production-pipeline/pipeline-schema|파이프라인 스키마]]
- [[projects/ai-video-production-pipeline/mvp-build-queue|MVP 구축 큐]]
