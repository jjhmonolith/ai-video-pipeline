# 영화 전문직의 인간 판단을 AI 영상 human gate로 번역한 연구

> 작성일: 2026-08-23  
> 목적: 기존 AI 영상 workflow 15편 close-read에 **영화교육·전문기관·실무자 자료의 판단 문법**을 결합한다.  
> 범위: 감독, 편집자, 촬영감독, 미술감독/프로덕션 디자이너, 사운드 디자이너 및 문화·윤리·관객 검증.

## 1. 핵심 결론

인간 고유성은 “창의적이다”라는 추상어가 아니다. 아래 판단은 여러 답이 기술적으로 성립하는 상황에서 **작품이 무엇을 의미해야 하는지, 어떤 손실을 감수할지, 누구에게 어떤 책임을 질지**를 정하는 권한이다.

- **감독**은 대사·표정의 표면보다 인물의 objective, obstacle, 관계 변화와 subtext를 잠근다.
- **촬영감독**은 예쁜 렌즈/조명이 아니라 그 감정과 POV를 관객이 어디서, 어떤 거리로, 어떤 순서로 경험할지를 정한다.
- **미술감독/프로덕션 디자이너**는 소품·공간이 단순 장식이 아니라 세계의 인과, 사회관계, 인물 행동을 지지하는지 판정한다.
- **편집자**는 물리적 연속성을 언제 지키고 언제 감정·서사를 위해 깨뜨릴지, 감정이 도착하는 프레임과 떠나야 할 프레임을 고른다.
- **사운드 디자이너**는 소리를 화면의 설명으로 중복할지, 보이지 않는 공간·기억·주관을 열어줄지, 무엇을 침묵시킬지 정한다.
- **문화·윤리·관객 판단자**는 재현의 당사자성, 해악, 신뢰, 실제 이해를 승인한다. 이 권한은 생성 모델의 평균적 선호로 대체하면 안 된다.

따라서 AI의 역할은 **결정**이 아니라 `비교 가능한 증거 준비 → 차이와 위험 설명 → 인간 선택을 delta로 기록 → 영향을 받는 범위만 재실행`이다.

## 2. 근거가 되는 전문 판단 문법

- Yale Film Analysis는 mise-en-scène의 공간·비례·장식·조명이 영화 읽기와 관계·정서를 바꾸며, 연기 양식 자체도 역사·문화별로 다르다고 설명한다.[1]
- Yale의 촬영 교육 자료는 프레이밍을 포함/배제의 선택으로 보고, 초점·심도·앵글·숏 크기·카메라 이동이 관객의 주의, 권력감, 친밀감과 공간 지각을 바꾼다고 정리한다.[2]
- Yale의 편집 자료는 continuity를 screen direction·position·temporal relation의 일관성으로 설명하지만, cheat cut은 물리 공간을 극적 공간에 희생할 수 있음을 함께 보여준다. 또한 cut과 hold 모두 시간 경험을 만드는 적극적 결정이다.[3]
- Yale의 사운드 자료는 sound bridge, offscreen sound, internal diegetic sound, sound perspective가 화면 밖 공간, 장면 연결, 기억·주관, 인물 위치를 구성한다고 설명한다.[4]
- Film Independent의 감독 실무 자료에서 Gina Prince-Bythewood와 Rodrigo García는 배우가 가져온 해석을 먼저 보고, 감독이 꿈꾼 것과 실제 take에서 생긴 것을 함께 관찰하며, 좋은 배우가 만든 예상 밖의 차원을 너무 빨리 지우지 말라고 강조한다.[5]
- Film Independent의 편집 마스터클래스 사례는 같은 장면의 편집 차이가 인물의 취약성·부자 관계를 성립시키거나 무너뜨리고, 음악 없이 작동하지 않는 장면은 음악으로도 구제되지 않는다는 판단을 보여준다.[7]
- DP Jomo Fray는 먼저 인물의 spine/objective/obstacle와 장면의 정서를 분석하고, 그 뒤 렌즈·움직임·카메라 시스템을 선택한다. 실제 테스트도 “몸 안에 있는 느낌인가”, “정서적인가”라는 체감 질문으로 판정했다.[10]
- 프로덕션 디자이너 Alex McDowell은 story를 중심에 놓고 character–environment–POV의 삼각관계에서 세계를 설계하며, 물리 세트와 VFX를 분리하지 않는 연속적 환경 설계를 제안한다.[9]
- Film Independent Documentary Lab 자료는 일정 단계 이후 객관성은 다른 사람에게서만 온다며 소규모 rough-cut screening을 반복하고, 한 장면을 한 아이디어로 환원해 전체 이야기 기능을 검사하는 실무를 소개한다.[11]
- 문화적 진정성 사례에서 *Pachinko* 팀은 한국·일본·재일조선인·미국 등 여러 관점의 역사 전문가를 writers’ room, 촬영 현장, cut review에 배치했다. “한 가지가 크게 틀리면 전체 쇼의 신뢰가 무너진다”는 운영 논리다.[12]
- CMSI의 다큐 윤리 연구는 45명의 장문 인터뷰에서 subject·viewer·artistic vision 사이의 충돌을 확인하고, “do no harm”, “protect the vulnerable”, “honor the viewer’s trust”를 공유 원칙으로 도출했다.[13]
- BFI Diversity Standards는 화면 재현뿐 아니라 창작 리더십, 인력·기회, 관객 개발까지 포함하며, 교차적 경험과 지속적 개선을 요구하는 기준선으로 작동한다.[14]

## 3. Human gate 설계 원칙

1. **Gate는 취향 투표가 아니라 권한 경계다.** 의미·핵심 연기·문화/윤리·공개는 사람만 승인한다.
2. **각 gate는 한 가지 결정만 묻는다.** “어떤가요?” 대신 손실이 다른 A/B/C를 묻는다.
3. **항상 시간축 증거를 준다.** frame, 0.5초 구간, 전후 shot, 소리 on/off를 함께 제공한다.
4. **AI recommendation은 있어도 자동 통과는 없다.** 추천 이유, confidence, critic disagreement, collateral risk를 표시한다.
5. **선택은 delta로 저장한다.** `keep/change/forbid/priority/accepted_defect/regeneration_scope`로 변환한다.
6. **전문가의 의도적 위반을 허용한다.** continuity·노출·구도 규칙은 법칙이 아니라 관객 효과를 위한 수단이다.[2][3]
7. **실제 관객과 당사자는 AI critic의 대리물이 아니다.** comprehension과 문화적 진정성은 해당 집단의 반응으로 교정한다.[11][12]

---

## 4. 구체적 human gates

### G1. 의도·장면 기능 Gate — 감독/스토리 편집자

**사람이 보는 신호**
- 이 장면 전후로 인물의 `want / obstacle / tactic / relationship` 중 무엇이 바뀌는가.
- 관객이 새로 알아야 하는 것, 아직 몰라야 하는 것, 끝에 느껴야 하는 감정이 무엇인가.
- 멋진 shot이 장면의 단일 아이디어를 강화하는가, 이미 아는 내용을 반복하는가.
- 시각 선택이 이야기에서 자라났는가, “cinematic” 표면이 뒤늦게 접착되었는가. Jomo Fray가 미학보다 인물·정서 분석을 먼저 두는 이유다.[10]

**사람이 내리는 결정**
- 장면의 한 문장 기능과 감정 변화 승인.
- 유지/삭제/재배치, reveal의 시점, ambiguity를 의도로 유지할지 설명 부족으로 고칠지 결정.
- `priority_order`: story clarity vs emotional residue vs visual spectacle.

**생략 시 위험**
- 각각은 아름답지만 서로 인과가 없는 montage.
- 같은 정보 반복, payoff 전 노출, 장면 끝의 감정이 다음 장면으로 이어지지 않음.
- AI가 쉽게 점수화하는 선명도·규모가 장면 기능을 압도.

**AI가 준비할 비교자료**
- 현재 cut과 해당 shot 삭제 cut.
- beat별 `audience_knows / audience_inferrs / character_knows` 표.
- 각 shot의 기능 라벨과 중복 경고.
- 기능은 같지만 정서 우선순위가 다른 A/B.

**질문 예시**
> “S04를 빼면 정보 손실은 없고 장면이 2.1초 빨라집니다. 다만 주인공의 망설임이 사라집니다. 속도 A / 망설임 B 중 이 장면의 약속은 무엇입니까?”

**Gate 출력**
`scene_promise`, `beat_change`, `reveal_policy`, `required_shots`, `deletable_shots`, `priority_order`.

---

### G2. Subtext Gate — 감독/배우 디렉터

**사람이 보는 신호**
- 말하는 내용과 실제로 원하는 것이 같은가, 의도적으로 어긋나는가.
- 대사보다 먼저/늦게 오는 시선, 회피, 호흡, 멈춤, 손의 행동이 숨은 objective를 드러내는가.
- 상대의 행동이 take 안에서 실제로 새 정보를 만든 것처럼 반응하는가, 미리 정해진 표정을 재생하는가.
- 배우/생성 후보가 감독의 계획보다 더 풍부한 해석을 가져왔는가. 전문 감독은 이런 예상 밖의 take를 먼저 관찰하고 너무 빨리 수정하지 않는다.[5]
- `moment before`, contrary expectation, 상대에게서 얻고 싶은 구체적 scene want가 현재 행동에 압력을 만드는가. Film Independent의 실무 toolkit은 감독을 배우의 “첫 번째이자 최선의 관객”으로 규정하고, 지시보다 실제 반응을 관찰하는 일을 앞세운다.[6]

**사람이 내리는 결정**
- 각 beat의 `spoken_intent`와 `hidden_intent`.
- 관객이 subtext를 즉시 알아야 하는지, 나중에 재해석해야 하는지.
- 표정이 아니라 playable action: 달래기, 숨기기, 시험하기, 밀어내기 등.

**생략 시 위험**
- 대사와 얼굴이 같은 감정을 반복하는 설명적 연기.
- 모든 감정이 큰 표정으로 번역되어 반전·관계의 긴장이 사라짐.
- 기술적으로 정확한 lip-sync지만 인물이 상대를 듣지 않는 느낌.

**AI가 준비할 비교자료**
- 같은 대사의 `literal`, `concealing`, `testing` 3개 take.
- eye-line, blink, breath, pause, gesture 시작 시간을 나란히 표시.
- 대사 없는 반응 shot만 따로 loop.
- AI가 추정한 subtext와 이를 뒷받침/반박하는 frame 증거.

**질문 예시**
> “A는 ‘괜찮아’와 미소가 일치합니다. B는 미소 전 0.6초 시선 회피가 있어 숨기는 감정이 생깁니다. 관객이 지금 눈치채야 합니까, 다음 장면에서만 이해해야 합니까?”

**Gate 출력**
`objective`, `obstacle`, `tactic`, `hidden_intent`, `reveal_to_audience_at`, `performance_delta`.

---

### G3. Performance authenticity Gate — 감독/편집자

**사람이 보는 신호**
- 감정 “종류”가 맞는가보다 행동의 원인이 take 안에서 읽히는가.
- 자극 → 인지 → 억제/반응의 순서가 살아 있는가.
- 얼굴·목·어깨·호흡·손이 서로 같은 강도로 과장되지 않는가.
- 반복 take가 너무 매끈해 우발성·발견의 느낌을 잃지 않았는가.
- 더 큰 표정과 더 믿기는 take가 다를 때 어느 쪽이 장면의 진실인가.

**사람이 내리는 결정**
- hero take 또는 서로 다른 take의 최소 조합.
- 감정 강도, reaction latency, pause 길이, 시선 목적지.
- 작은 형태 결함을 trim으로 감수하고 강한 연기를 살릴지, 재생성할지.

**생략 시 위험**
- 감정 분류는 맞지만 “연기한 티”가 나는 AI performance.
- 편집 때마다 반응 강도가 바뀌어 인물의 내적 연속성이 붕괴.
- 손/얼굴 결함을 없애려다 가장 살아 있는 순간을 버림.

**AI가 준비할 비교자료**
- 동일 크기·동일 음량의 blind A/B/C.
- 자극 시점 기준 2초 전/후 synchronized split screen.
- 얼굴 close-up뿐 아니라 전신 body tension과 상대 reaction.
- 후보별 `strongest_interval`, `unusable_interval`, `repair_risk`.

**질문 예시**
> “B가 가장 믿기지만 끝 0.3초 손 결함이 있습니다. B를 0.3초 trim해 살릴까요, 표정의 자발성을 잃을 수 있는 재생성을 할까요?”

**Gate 출력**
`selected_take`, `usable_interval`, `reaction_latency`, `performance_keep`, `accepted_defect`, `repair_method`.

---

### G4. Composition·POV Gate — 촬영감독/감독

**사람이 보는 신호**
- 프레임이 무엇을 포함하고 배제하여 누구의 경험을 우선하는가. 프레이밍은 단순 배치가 아니라 선택이다.[2]
- 관객 시선이 첫 1초에 어디에 가고, 그 다음 무엇을 발견하는가.
- shot size, height, angle, foreground/background, negative space가 권력·친밀감·고립을 어떻게 만든다.
- shallow focus가 중요한 맥락까지 지우지 않는가; camera move가 인물의 감정 변화보다 먼저 “효과”를 발표하지 않는가.
- 모바일 crop에서도 핵심 관계와 gaze path가 유지되는가.

**사람이 내리는 결정**
- 관객의 vantage point, shot size, lens/depth grammar, camera height/movement.
- “보기 좋은” A와 인물의 몸/정서를 느끼게 하는 B 중 선택.
- 의도적으로 불편한 off-center, occlusion, distortion을 허용할지.

**생략 시 위험**
- 모든 장면이 중앙 대칭·얕은 심도·slow push-in으로 수렴.
- 배경의 사회·공간 정보가 blur로 사라지고, scale 관계가 없음.
- 카메라가 인물보다 감정을 먼저 설명해 연기가 약해짐.

**AI가 준비할 비교자료**
- 동일 beat의 wide/medium/close, static/move, deep/shallow focus contact sheet.
- gaze heatmap 추정과 첫 시선 도착 시간.
- theatrical 16:9와 실제 delivery crop overlay.
- 각 옵션의 `emotional_effect`, `lost_context`, `continuity_cost`.

**질문 예시**
> “A는 close-up이라 감정은 즉시 읽히지만 권력 관계가 사라집니다. B는 문틀 foreground가 인물을 가두지만 표정은 작습니다. 이 beat의 1순위는 감정 명료성입니까, 갇힘의 체감입니까?”

**Gate 출력**
`vantage_point`, `gaze_order`, `shot_scale`, `lens_depth_rule`, `movement_motivation`, `crop_safe_area`.

---

### G5. Production design·세계 일관성 Gate — 미술감독/프로덕션 디자이너

**사람이 보는 신호**
- 공간·소품·재료가 인물의 계급, 습관, 역사, 제약을 말하는가. Yale 자료처럼 décor와 공간 비례는 정서와 사회관계를 바꾼다.[1]
- 세트가 “스타일 프롬프트”의 결과인가, 이 세계에서 사용되고 닳고 수리된 흔적이 있는가.
- 인물이 환경 때문에 특정 행동을 하게 되는가; 환경은 플롯의 가능/불가능을 만든다.
- 물리 세트, 생성 배경, VFX, 소리의 세계 규칙이 하나로 이어지는가. McDowell은 이 분리를 없앤 전체 환경 설계를 강조한다.[9]

**사람이 내리는 결정**
- world rules, material/age/patina, socioeconomic logic, prop biography.
- hero location과 반복 가능한 spatial map.
- 미술적 매력 때문에 세계 인과를 깨는 요소를 제거할지.

**생략 시 위험**
- 장면마다 예쁘지만 같은 세계처럼 보이지 않음.
- 시대·지역·계층과 맞지 않는 소품이 문화적 신뢰까지 붕괴.
- door/window/furniture 위치가 바뀌어 blocking·continuity·sound perspective 동시 실패.

**AI가 준비할 비교자료**
- location plan + 4방향 view + material/prop board.
- `character × environment × POV` 매트릭스.
- 각 소품의 주인, 사용 이유, 상태 변화, 전후 shot 위치.
- 물리/생성/VFX 경계가 보이는 composite test와 sound mock.

**질문 예시**
> “A의 공간은 더 화려하지만 인물의 경제상태와 충돌합니다. B는 덜 화려하나 수리 흔적과 동선이 인물의 생활사를 지지합니다. 세계 규칙을 위해 B를 잠글까요?”

**Gate 출력**
`world_rules`, `spatial_map`, `material_palette`, `prop_biographies`, `state_variants`, `forbidden_anachronisms`.

---

### G6. Continuity·의도적 불연속 Gate — 편집자/스크립트 수퍼바이저

**사람이 보는 신호**
- identity, wardrobe, prop, damage, lighting, eyeline, screen direction, action phase, sound bed가 shot 경계에서 이어지는가.
- 180°와 match-on-action이 관객의 공간 이해를 돕는가. continuity는 방향·위치·시간 관계를 통해 명료성을 만든다.[3]
- mismatch가 관객을 실제로 혼란시키는가, 아니면 dramatic space·emotion을 위해 허용할 수 있는 cheat인가. 물리 공간을 극적 공간에 희생한 cheat cut도 영화 문법의 일부다.[3]
- jump/elliptical cut이 의도된 정신상태·압축인가, 단순 생성 실패 은폐인가.

**사람이 내리는 결정**
- hard continuity와 soft continuity 분리.
- 오류 수정/trim/cutaway/의도적 위반 승인.
- 공간이 잠시 헷갈려도 감정적 match를 살릴지.

**생략 시 위험**
- 모든 pixel mismatch를 고치다 더 강한 감정·구도 손실.
- 반대로 eye-line·screen direction 오류가 관계와 동선을 뒤집음.
- 오디오 room tone 단절이 보이지 않는 cut까지 드러냄.

**AI가 준비할 비교자료**
- shot exit/entry frame onion-skin, state diff, spatial diagram.
- action/eyeline/sound waveform 동기 비교.
- 오류 노출 시간과 첫 시청 탐지 가능성.
- `fix`, `hide`, `accept_as_expressive` 세 옵션과 부작용.

**질문 예시**
> “S08→S09에서 컵 위치는 틀리지만 eye-line과 감정 상승은 맞습니다. 컵을 고치면 표정이 약해질 위험이 큽니다. 물리 오류를 허용하고 감정 continuity를 우선할까요?”

**Gate 출력**
`hard_continuity`, `soft_continuity`, `approved_cheats`, `bridge_method`, `state_patch`.

---

### G7. Pacing·cut point Gate — 편집자

**사람이 보는 신호**
- shot 길이가 아니라 정보·감정이 도착한 순간: 관객이 읽기 전 잘렸는가, 다 읽은 뒤 남아 있는가.
- reaction을 action 전/후 어디에 붙일 때 원인과 의미가 바뀌는가.
- 반복이 motif를 쌓는가, 이미 이해한 것을 재설명하는가.
- 전체 sequence의 긴장–이완–예상–보상, 침묵과 음악의 호흡.
- cut하지 않는 결정도 cut만큼 적극적이다. Yale은 shot 연장과 rhythm이 관객의 시간 경험을 바꾼다고 설명한다.[3]

**사람이 내리는 결정**
- frame-accurate in/out, hold, overlap, ellipsis, reaction placement.
- 관계를 성립시키는 insert/rewrite/reshoot 필요 여부. 편집실에서 인물 관계가 작동하지 않아 장면을 다시 구성한 Film Independent 사례처럼 이는 기술 trim이 아니라 의미 수정이다.[7]

**생략 시 위험**
- 평균 shot 길이를 맞췄지만 감정이 늘 늦거나 급함.
- 음악 beat에만 맞춘 기계적 montage.
- 개별 shot 평가에서는 높은데 전체는 지루하거나 숨 쉴 틈이 없음.

**AI가 준비할 비교자료**
- `fast`, `balanced`, `linger` 3개 cut을 같은 음량으로 blind 제공.
- speech boundary, gaze arrival, action apex, emotion shift marker.
- music 없는 picture-only pass.
- 1회 시청과 반복 분석을 분리한 평가.

**질문 예시**
> “A는 12프레임 빨리 잘라 정보는 선명하지만 상대의 상처가 도착하지 않습니다. B는 여운이 있으나 sequence가 0.5초 느려집니다. 이 순간은 이해와 상처 중 무엇을 우선합니까?”

**Gate 출력**
`cut_in`, `cut_out`, `hold_reason`, `ellipsis`, `reaction_order`, `music_independent_pass`.

---

### G8. Sound meaning·청각 POV Gate — 사운드 디자이너/편집자

**사람이 보는 신호**
- 대사 명료도뿐 아니라 누구의 귀로 듣는가: 객관 공간, 인물 내부, 기억, 위협 중 무엇인가.
- 화면에 없는 인물·공간이 offscreen sound로 살아 있는가. 소리의 거리·음색·방향은 보이지 않는 공간 관계를 만든다.[4]
- sound bridge가 장면을 연결하는가, 다음 장면을 너무 일찍 설명하는가.
- Foley가 물성과 행동을 주는가, 모든 움직임을 과잉 강조하는가.
- 음악이 장면의 감정을 중복 지시하는가. 전문 편집자는 음악 없이 작동하지 않는 장면을 음악으로 구제하지 말라고 경고한다.[7]
- 침묵이 실제 무음이 아니라 선택된 소리의 희소성으로 긴장을 만드는가.[11]
- 보이는 대상을 문자 그대로 들려주는 대신 sonic perspective가 인물의 체감과 일치하는가. 실무 사운드 디자이너는 “see a dog, hear a dog”식 대응보다 무엇을 들리지 않게 할지를 포함한 청각 POV를 강조한다.[8]

**사람이 내리는 결정**
- DIA/AMB/FOL/SFX/MUS 중 narrative carrier.
- subjective/objective perspective 전환, music/no music, silence density.
- native generated audio를 timing reference로만 쓸지 final layer로 승인할지.

**생략 시 위험**
- sync는 맞지만 공간 크기·거리·몸의 무게가 없음.
- 음악이 감정을 대신해 값싼 광고처럼 들림.
- room tone·reverb·오프스크린 방향이 cut마다 바뀌어 continuity 붕괴.

**AI가 준비할 비교자료**
- 동일 loudness의 `dry`, `world-only`, `subjective`, `music-led` 4개 mix.
- 화면을 가린 audio-only pass와 음소거 picture-only pass.
- layer별 stem, sound-source map, transition waveform.
- 각 소리가 추가하는 정보/정서와 중복 여부.

**질문 예시**
> “B의 음악은 슬픔을 즉시 읽히지만 표정과 같은 정보를 반복합니다. C는 호흡·먼 기차·실내 creak만 남겨 고립을 만듭니다. 감정 명료성 B / 인물 내부 체감 C 중 어느 쪽입니까?”

**Gate 출력**
`sound_pov`, `narrative_carrier`, `stem_policy`, `music_entry`, `silence_rule`, `sound_continuity_anchor`.

---

### G9. Audience comprehension Gate — 감독/편집자/실제 관객

**사람이 보는 신호**
- 처음 본 관객이 핵심을 자기 말로 재진술하는가, 제작자의 표현을 따라 말하는가.
- confusion, boredom, disbelief가 발생한 정확한 timecode.
- 의도한 ambiguity와 기본 인과를 놓친 혼란의 차이.
- 기억된 장면이 작품의 약속과 일치하는가, 단지 가장 화려한 shot인가.
- feedback의 해법보다 반복되는 증상에 주목하는가.

**사람이 내리는 결정**
- 오해를 설명 shot으로 고칠지, 순서/hold/reaction만 바꿀지, 모호함을 유지할지.
- target cohort별 version이 필요한지.
- 소수의 강한 반응과 다수의 평균 이해 중 작품의 위험 허용치.

**생략 시 위험**
- 생성 모델과 critic이 같은 맹점을 공유한 채 내부 점수만 높음.
- 제작팀은 이미 맥락을 알아 문제를 보지 못함.
- 관객이 제시한 해법을 그대로 넣어 영화가 설명적으로 변함.

**AI가 준비할 비교자료**
- 6–8명 소규모 blind rough-cut screening packet. Film Independent 사례도 반복 소규모 상영으로 외부 객관성을 얻는다.[11]
- unaided message recall, confusion/boredom timecode, remembered image, felt emotion.
- 반응을 `symptom / proposed_fix / cohort / confidence`로 분리.
- 제작자 의도와 관객 해석의 mismatch map.

**질문 예시**
> “8명 중 5명이 관계 변화는 느꼈지만 원인을 반대로 이해했습니다. 대사 설명을 추가하기 전에 reaction 순서만 바꾼 B를 시험할까요, 이 오독을 의도된 ambiguity로 유지할까요?”

**Gate 출력**
`cohort`, `unaided_recall`, `confusion_timecodes`, `intended_ambiguity`, `revision_hypothesis`, `retest_required`.

---

### G10. Cultural·ethical judgment Gate — 당사자 검토자/문화 자문/제작 책임자

**사람이 보는 신호**
- 누가 말할 권한과 lived experience를 갖고 있으며, 누가 대상화되는가.
- 시대·언어·의상·음식·의례의 한 오류가 전체 신뢰를 무너뜨릴 정도의 anchor인가.
- 여러 이해당사자 관점이 실제로 충돌할 때 무엇을 숨기지 않고 드러낼 것인가.
- 동의가 촬영/생성/편집/배포/2차 학습까지 구체적인가; 취약한 주체가 철회하거나 예상 가능한 결과를 이해했는가.
- 사실을 압축·재배치·합성한 것이 viewer trust를 깨는가. CMSI 연구는 subject 보호, viewer 신뢰, artistic vision의 충돌을 사례별로 숙고해야 함을 보여준다.[13]
- 화면 representation뿐 아니라 누가 창작·검토·고용·관객 개발에 참여했는가. BFI 기준은 이 전체 구조를 본다.[14]

**사람이 내리는 결정**
- proceed / consult / revise / contextualize / withhold / do-not-publish.
- 문화 자문의 구성: 단일 토큰 자문이 아니라 갈등 당사자의 복수 관점.
- 합성·재연·archival manipulation 표기, 민감 이미지의 노출 강도와 공개 범위.
- 법적으로 가능해도 윤리적으로 사용하지 않을 선택.

**생략 시 위험**
- 디테일 하나의 오류가 세계 전체를 fantasy로 보이게 함. *Pachinko*는 여러 진영의 전문가를 집필·현장·cut review까지 배치했다.[12]
- 고정관념, 문화 혼합, 실제 고통의 미학화, 취약 주체 재피해.
- consent가 있었어도 사용 맥락이 달라져 신뢰·브랜드·법적 위험 발생.

**AI가 준비할 비교자료**
- claim/depiction별 source, uncertainty, consulted perspective, unresolved disagreement.
- 당사자에게 보여줄 context 포함 cut; 민감 이미지 on/off 대안.
- 예상 benefit/harm, affected groups, reversibility, distribution scope.
- stereotype/cultural conflation 후보는 “정답”이 아니라 인간 검토 queue로 표시.

**질문 예시**
> “이 합성 장면은 사실 관계는 맞지만 실제 피해자의 얼굴·공간을 연상시키며 재연 표기가 없습니다. 표기 추가 A / 비식별화 B / 삭제 C 중 어느 수준의 책임을 택합니까?”

**Gate 출력**
`affected_groups`, `consultants`, `consent_scope`, `representation_risks`, `disclosure`, `distribution_limits`, `release_authority`.

---

## 5. 직군별 gate ownership

| 직군 | 1차 소유 gate | 같이 봐야 하는 인접 gate | 인간이 최종 승인해야 하는 이유 |
|---|---|---|---|
| 감독 | G1 의도, G2 subtext, G3 performance | G4 POV, G7 pacing, G9 이해 | 장면 의미와 인물의 숨은 행동을 통합하는 권한 |
| 편집자 | G6 continuity, G7 pacing | G1 기능, G3 take, G8 sound, G9 이해 | 물리적 정확성보다 감정·서사를 우선할 예외 판단 |
| 촬영감독 | G4 composition/POV | G1 의도, G3 performance, G5 world | 기술 설정을 감정·몸·시선 경험으로 번역 |
| 미술감독/프로덕션 디자이너 | G5 world | G4 frame, G6 state, G10 culture | 환경의 사회·역사·인과를 전체 세계 규칙으로 유지 |
| 사운드 디자이너 | G8 sound meaning | G2 subtext, G6 continuity, G7 pacing | 들리는 것과 숨길 것, 객관/주관 청취 위치 선택 |
| 문화 자문/윤리 책임자 | G10 culture/ethics | G1 의도, G5 world, G9 audience | 당사자성·해악·신뢰·공개 권한은 모델 선호가 소유할 수 없음 |
| 실제 관객 패널 | G9 comprehension | G1, G7, G8 | 관객 경험은 예측치가 아니라 관찰값으로 검증해야 함 |

한 사람이 여러 직군을 겸할 수 있지만 렌즈는 합치지 않는다. 예를 들어 감독이 “의도한 모호함”이라고 말해도 G9의 실제 오독과 G10의 해악 가능성을 별도로 기록한다.

## 6. 파이프라인 삽입 위치

```text
Creative Constitution
  → G1 의도/장면 기능 + G10 초기 권리·문화
Script / Animatic
  → G2 subtext + G4 POV + G5 world rules
Reference / Candidate generation
  → 자동 hard QA
  → G3 performance + G4 composition + G6 continuity exception
Rough cut A/B/C
  → G7 pacing + G8 sound meaning
Blind screening
  → G9 audience comprehension
Release candidate
  → G10 문화·윤리·공개 승인
  → decision delta와 학습 ledger 저장
```

### 자동 검사와 human gate를 혼동하지 않는 기준

- `codec/fps/resolution/clipping/lip-sync/file corruption` → 자동 차단.
- `prop/wardrobe/eyeline mismatch 후보` → AI가 표시, G6에서 표현적 예외 승인.
- `표정 감정 분류/shot aesthetics score` → 참고값일 뿐 G2–G4 대체 금지.
- `toxicity/stereotype detector` → G10 queue 생성용; 문화적 적합성 승인 금지.
- `AI audience simulation` → G9 질문 초안용; 실제 screening 대체 금지.

## 7. 표준 HumanJudgmentPacket

```yaml
gate_id: G7-PACING-S12
owner_role: editor
scope: scene_12
purpose: "관객이 배신을 인지한 뒤 주인공의 억제를 느끼게 한다"
locked_rules:
  - "반전 전에는 상대의 의도를 확정하지 않는다"
  - "melodramatic music 금지"
options:
  - id: A
    preview: s12_fast.mp4
    strength: "인과가 빠르게 읽힘"
    loss: "주인공의 상처가 도착하기 전에 cut"
  - id: B
    preview: s12_linger.mp4
    strength: "반응이 12프레임 더 남아 subtext가 보임"
    loss: "sequence가 0.5초 느려짐"
ai_recommendation: B
critic_disagreement:
  story_critic: A
  performance_critic: B
why_human_needed: "이해 속도와 감정 잔상의 우선순위는 미학적 권한"
one_question: "이 장면의 1순위는 즉시 이해 A입니까, 늦게 도착하는 상처 B입니까?"
answer_modes: [A, B, combine, free_text]
```

응답은 반드시 다음으로 번역한다.

```yaml
keep: [subdued_expression, no_music]
change: [cut_out_plus_12_frames]
forbid: [expository_insert]
priority_order: [performance_authenticity, comprehension, pace]
accepted_defects: ["background hand mismatch 0.2 sec"]
regeneration_scope: none
verification_question: "12프레임 hold가 과장 없이 상처를 읽히게 하는가?"
```

## 8. 15편 close-read와 결합할 때의 분석 코딩

기존 15편에서 관찰한 인간 행동을 아래 코드로 재분류하면 “도구 사용”이 아니라 “판단 기능”으로 합칠 수 있다.

| close-read 관찰 | 전문 gate 코드 | 기록할 추가 정보 |
|---|---|---|
| 여러 생성 후보 중 한 take 선택 | G3 | 선택된 micro-behavior, 버린 후보의 과장/부자연 이유 |
| hero frame/렌즈/조명 선택 | G4 | 감정·POV·gaze order, 단순 미감과 구분 |
| 캐릭터/공간 reference 수정 | G5/G6 | world rule, state transition, prop/spatial continuity |
| 전체 clip 대신 0.8초 salvage | G3/G7 | 감정 도착 프레임, cut 이유, accepted defect |
| 추가 insert/reaction 생성 | G1/G7/G9 | 어떤 인과·관계·이해 실패를 보완했는지 |
| 음악/Foley/침묵 재구성 | G8 | sound POV, narrative carrier, 중복 설명 제거 |
| 역사·브랜드·권리 확인 | G10 | 당사자 관점, disclosure, release authority |
| 사용자 A/B 질문 | 해당 G | option 간 실제 손실, 질문이 path를 바꿨는지 |

최종 합성의 유효한 결론은 “사람이 많이 손봤다”가 아니라 다음 형식이어야 한다.

> **[상황]** subtext-critical reaction shot에서  
> **[사람이 본 신호]** 대사 전 시선 회피와 호흡 지연을 보고  
> **[결정]** 더 큰 표정 대신 절제된 take의 0.8–2.6초를 선택했으며  
> **[AI 준비물]** synchronized blind A/B와 micro-timing 표가 있었고  
> **[학습 delta]** `keep=subdued_face`, `change=eye_shift -0.3s`, `forbid=dramatic_push`로 저장했다.

## 9. 검증 기준

이 연구를 실제 시스템으로 옮겼다고 말하려면 다음을 확인한다.

- 10개 gate 각각 `사람이 보는 신호 / 결정 / 생략 위험 / AI 비교자료 / 한 질문 / 구조화 출력`이 구현돼 있다.
- 자동 QA와 human authority가 분리돼 있다.
- G3는 whole-clip accept/reject가 아니라 usable interval을 저장한다.
- G6는 continuity violation뿐 아니라 승인된 expressive cheat를 저장한다.
- G8은 mix를 loudness-normalized blind 비교하고 stem을 보존한다.
- G9는 실제 처음 보는 관객의 unaided recall과 timecode를 수집한다.
- G10은 단일 모델 판정이 아니라 affected group·복수 자문·consent/disclosure/release authority를 기록한다.
- 모든 인간 결정은 원문 응답과 delta를 함께 보존하며, 승인된 요소를 재생성에서 잠근다.

## 관련 문서

- [[projects/ai-video-production-pipeline/human-judgment-for-video-quality-2026-08-23|AI 영상 품질을 높이는 인간 판단 연구]]
- [[projects/ai-video-production-pipeline/pipeline-schema|AI 영상 제작 파이프라인 스키마]]
- [[projects/ai-video-production-pipeline/human-ai-video-methodology-2026-08-22|인간-AI 공동 제작형 AI 영상 방법론]]

## Sources

[1] https://filmanalysis.yale.edu/mise-en-scene — Yale Film Analysis: Mise-en-scène
[2] https://filmanalysis.yale.edu/cinematography — Yale Film Analysis: Cinematography
[3] https://filmanalysis.yale.edu/editing — Yale Film Analysis: Editing
[4] https://filmanalysis.yale.edu/sound — Yale Film Analysis: Sound
[5] https://www.filmindependent.org/blog/14-lessons-rodrigo-garcia-and-gina-prince-bythewood-taught-us-about-working-with-actors — Film Independent: 14 Lessons on Working with Actors
[6] https://www.filmindependent.org/blog/how-to-get-great-performances-out-of-actors-a-directors-toolkit — Film Independent: Directors Toolkit for Great Performances
[7] https://www.filmindependent.org/blog/j-j-abrams-long-time-editors-reveal-how-to-help-develop-characters-in-the-editing-room — Film Independent: Editors Develop Characters in the Editing Room
[8] https://www.filmindependent.org/blog/guest-post-using-subjective-sound-design-to-create-emotion-and-interiority — Film Independent: Subjective Sound Design
[9] https://www.filmindependent.org/blog/world-building-genesis-story-mind-blowing-hour-production-designer-alex-mcdowell — Film Independent: Alex McDowell on World Building
[10] https://www.filmindependent.org/blog/detail-oriented-nickel-boys-dp-jomo-fray-on-emotion-informing-images-his-time-with-project-involve — Film Independent: DP Jomo Fray on Emotion Informing Images
[11] https://www.filmindependent.org/blog/five-lessons-learned-at-the-film-independent-documentary-lab — Film Independent Documentary Lab: Five Lessons
[12] https://www.filmindependent.org/blog/forum-2022-day-3-forging-your-path-unparalleled-authenticity-in-pachinko-and-diversity-in-storytelling — Film Independent: Pachinko Authenticity and Diversity in Storytelling
[13] https://cmsimpact.org/resource/honest-truths-documentary-filmmakers-on-ethical-challenges-in-their-work — CMSI: Honest Truths — Documentary Ethics
[14] https://www.bfi.org.uk/inclusion-film-industry/bfi-diversity-standards — BFI Diversity Standards
