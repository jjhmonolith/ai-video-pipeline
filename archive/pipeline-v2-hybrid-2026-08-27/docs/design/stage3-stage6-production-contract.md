# 3–6단계 제작 계약

이 문서는 `narrative-design.v3`와 `shot-design.v2`의 단계 경계를 설명한다.
기존 `beats[].seconds` 시나리오는 읽고 감사할 수 있지만 신규 생성의 정본은 아니다.

## 시간의 소유권

| 단계 | 시간 결정 |
|---|---|
| 1 | 작품의 총 편집 길이: `runtime_contract`의 fixed/range/open |
| 3 | 신별 추정 범위, 페이싱, 시간 연출 후보와 극적 이유 |
| 4 | LLM이 shot별 정확한 편집 기여도, 허용 오차, head/tail handle, 시간 기법과 실행 방식을 결정 |
| 4 compiler | 위 결정을 H3 frame grid, 생성 길이, trim/retime 계획으로 변환 |
| 6 | 실제 생성 영상 길이와 take 기록 |
| 7 | handle trim, retime, timeline 포함 여부를 실제 편집에 적용 |

`행동 수 × 고정 초`, 컷 목적별 고정 범위, 45초·60초의 도구 기본값은 신규
설계에 사용하지 않는다. `total_planned_capture_seconds`는 coverage와 handle 때문에
`total_edit_seconds`보다 길 수 있다.

## 3단계: sequence → scene → event

3단계는 촬영 전 이야기 설계다. 각 신은 다음을 먼저 확정한다.

- 신의 intent와 narrative role
- POV owner와 dramatic question
- entry/exit state
- 장소, 사건, 인물·사물 역할
- `estimated_edit_range_seconds`, pacing 이유, temporal intent
- 새로 필요해진 제작 요소와 reference debt

카메라, 렌즈, 앵글, shot 분할, 정확한 shot 초수는 3단계에 쓰지 않는다.

시나리오가 필요하면 1–2단계에 없던 소품·장소 세부·상호작용을 발명할 수 있다.
중요하거나 반복되거나 접촉하는 새 요소는 `NEW-` id로 등록하고 아래처럼 분류한다.

| asset class | 5단계 처리 |
|---|---|
| `recurring_canonical_asset` | full sheet |
| `scene_only_hero_prop` | scene reference |
| `interaction_target` | action/mechanical reference |
| `sublocation_detail` | location reference |
| `background_dressing` | prompt-only |
| `offscreen_only` | image 없음 |

## 4단계: treatment → setup → shot → take

4단계의 첫 레이어는 LLM directorial plan이다. 신별 treatment에서 intent, POV,
blocking, coverage logic을 쓰고, 실제 촬영처럼 setup과 shot을 나눈다. 두 번째
레이어인 deterministic compiler는 이 선택을 검증하고 프롬프트·H3 입력·QA 계약으로
변환한다. 컴파일러가 예술적 shot 길이나 카메라를 대신 결정하지 않는다.

shot timing은 다음을 가진다.

- `edit_target_seconds`, `tolerance_seconds`
- `head_handle_seconds`, `tail_handle_seconds`
- `temporal_mode`, `dramatic_reason`, `execution_method`
- subject/world/camera time domain
- normalized action phases, speed curve, camera time
- `capability_debt`

지원 temporal mode는 real time, slow/extreme slow motion, speed ramp, time freeze,
bullet-time orbit, timelapse, hyperlapse, compressed montage, elliptical time, reverse,
loop, subjective time, simultaneous split time다. H3가 확정적으로 수행할 수 없는 조합은
다른 기법으로 몰래 바꾸지 않고 `capability_debt`로 생성 차단한다.

두 사람이 보이는 shot은 투샷 또는 명시적인 오버 더 숄더다. `C01..C10`은 같은
shot의 take/retry다. 다른 앵글이나 역할은 별도 shot id를 갖는다.

## 5단계: reference first, plate second

5A는 3–4단계가 만든 reference debt와 interaction manual을 먼저 한 장씩 생성·검수한다.
그 뒤 모든 기존 시트와 새 reference를 한꺼번에 global reference preflight한다.
전부 통과한 다음에만 5B 시작판을 생성한다. 시작판도 한 장 생성 → AI 검수 → 실패한
경우 한 장 재생성 순서이며 최대 10회다.

## 6단계: one take then retry

각 shot은 C01 한 개만 manifest에 준비한다. 검수 실패가 기록된 경우에만 C02 한 개를
추가하고, 다시 검수한다. 각 재시도는 공통 `adaptive-generation-harness.v1`의 서로
다른 전략을 쓰며 최대 C10이다. normal mode의 최종 채택은 사람, 명시적 fast-track은
AI가 수행한다.

