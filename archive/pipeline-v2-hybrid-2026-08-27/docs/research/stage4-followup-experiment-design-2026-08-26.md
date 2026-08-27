# 4단계 후속 연구 설계 v2

> 설계일: 2026-08-26  
> 상태: L1 18개 사람 블라인드 평가 완료 · M1 24개 진단 블라인드 평가 대기  
> 영상 엔진: MiniMax H3 고정

## 결론부터

첫 실험 결과는 4단계만 고쳐서는 해결되지 않는 문제를 드러냈다. 다음 실험 전에 1–3단계에서 아래 정보를 생산하고 검증해야 한다.

1. 1단계는 상호작용 가능한 사물과 장소의 부품·접촉·고정 관계를 정의한다.
2. 2단계는 전체 보드가 아니라 정체성용 크롭과 동작 가능성용 크롭을 따로 승인한다.
3. 3단계는 복합 문장을 원자 sub-beat로 나누고, 도구·대상·결과 상태와 발화 주체를 구조화한다.
4. 4단계는 카메라 정책과 H3 이미지 앵커 정책을 서로 독립적으로 결정한다.
5. H3 원본 오디오는 실험과 납품에서 제거한다.

후속 연구는 두 연구로 나눈다.

- L1: 인물 이동에서 `카메라 정책 × 끝 이미지` 3×2 비교
- M1: 정밀 도구 작업에서 `동작 레퍼런스 × 끝 이미지` 2×2 비교, 두 원자 행동에 반복

각 셀은 시드 3개로 반복한다. 총 42개 영상이다. 한 시드로 먼저 14개 카나리아를 만들고 입력·프롬프트·블라인드 패킷이 정상인지 확인한 뒤 나머지 28개를 생성한다.

실행은 완료됐다. 14개 카나리아와 추가 28개가 모두 생성됐고, 전 파일이 768×1344·24fps·124프레임 규격을 통과했다. H3 원본 오디오는 별도 기록 후 블라인드 복사본에서 제거했다. AI 평가는 조건 키 없이 14시점 샘플로 봉인했다. 이후 사람의 입력판 검토에서 M1의 모든 배관·커플링이 렌치 용량보다 크고, 렌치를 보여주기 위한 사선 구도가 대상 축과 90°인 실제 작용 관계를 깨뜨렸음이 확인됐다. 따라서 M1은 요인의 일반 효과를 확정하는 실험으로는 부적격이지만, 이미 생성된 24개의 후보 품질과 실패 양상을 비교하는 진단 평가는 계속한다. L1 18개는 사람 평가가 완료됐고 승자는 H다. 실행 기록은 `stage4-followup-experiment-run-2026-08-26.md`에 분리했다.

## 파이프라인 반영 상태

연구 결과 중 추가 실험 없이도 확정할 수 있는 계약 수정은 구현했다. 기존 배관공·펜트하우스 v1의 과거 산출물을 소급해 실패 처리하지는 않고 경고로만 드러낸다. 새 출력은 다음 구조를 생성·검수한다.

- 1단계: `part_id`, affordance, interaction site와 전문 도구의 수치 용량·대상 치수·작용면/축을 요구하는 정의·조사 규칙, H3 원본 오디오 폐기 계약
- 2단계: 패널별 reference role 후보와 part/site 결속 필드, motion-affordance 가독성 및 기계 크기·축 타당성 검수, 전체 보드 H3 입력 금지
- 3단계: 구조화된 원자 sub-beat, 수치 fit/axis/projection을 포함한 interaction contract, 화면 발화/보이스오버/무발화 구분과 검증 경고
- 4단계: 피사체 endpoint/앵커 정책에서 카메라 정책 분리, 이동 shot의 비고정 카메라 허용, 카메라 이동 시 world-space 불변량 사용
- 실험 검수: 블라인드 영상에서 H3 오디오를 무손실 영상 복사 단계에 제거

반대로 `first_only / paired`의 기본 선택과 `natural / soft_follow / locked`의 우열은 최종 정책으로 확정하지 않았다. 현재 컴파일러는 강제 locked를 피하기 위한 연구 기준선으로 이동 shot에 `natural`을 표기하며, 아래 L1 결과로 이를 유지하거나 교체한다.

## 앞 단계 반영 검토

### 1단계 · 방향, 계약, 요소 정의

현재 배관공 정의에는 빨간 도구가 `파이프 렌치`이며 이음부를 푼다고 적혀 있다. 그러나 텍스트 이름만 있고 H3와 4단계가 다시 참조할 안정적인 부품 ID와 물리 관계가 없다. 다음 필드를 상호작용 대상에 요구한다.

```json
{
  "interaction_parts": [
    {
      "part_id": "pipe-wrench.jaws",
      "role": "contact_surface",
      "moves_with": "pipe-wrench.handle"
    }
  ],
  "affordances": [
    {
      "action_id": "grip-threaded-coupling",
      "actor_part_id": "pipe-wrench.jaws",
      "compatible_target_class": "cylindrical-threaded-coupling",
      "canonical_approach": "jaws perpendicular to coupling axis",
      "force_result": "coupling rotates while adjacent pipe remains fixed",
      "forbidden_results": ["valve wheel detaches", "pipe disappears", "water discharges"]
    }
  ]
}
```

장소 정의는 실제 작업 지점에 `interaction_site_id`를 부여한다. 배관공 예시는 `warren-valve-junction.coupling-01`이며 회전 가능한 부품과 고정 부품을 구분한다. 한 요소 정의가 다른 특정 요소를 직접 소유하지는 않는다. 도구는 호환 대상 class를 정의하고, 장소는 해당 class를 가진 target part를 정의한다.

계약에는 다음 오디오 정책을 둔다.

```json
{
  "audio": {
    "h3_native_audio": "discard",
    "target_language": "ko",
    "dialogue_source": "approved_script_only",
    "lip_sync": "only_when_onscreen_speaker_is_explicit"
  }
}
```

1단계 조사 계획은 화면에서 실제 사용되는 전문 도구가 있으면 생김새뿐 아니라 올바른 대상, 접촉 위치, 접근 방향, 고정되는 반작용 부품을 조사한다. 이 정보가 없으면 `unresolved`로 남기고 도구 사용 shot을 만들지 않는다.

### 2단계 · 레퍼런스 시트

현재 panel manifest에는 `safe_for_motion_reference`가 있지만 실제 승인 크롭이 없었다. 첫 실험은 예외적으로 전체 보드를 H3에 넣었고, 이는 정체성 정보와 여러 시점·텍스트·중복 형상을 동시에 조건으로 넣었다.

다음부터 전체 보드는 H3 입력으로 금지한다. 패널 크롭은 아래 역할 중 하나로 승인한다.

- `identity_reference`: 얼굴·의상·대상의 고유 형태
- `environment_geometry_reference`: 장소의 고정 구조와 깊이
- `motion_affordance_reference`: 움직이는 부품, 고정부, 접촉면과 정상 작동 방향

동작 크롭에는 `binds_part_ids` 또는 `binds_interaction_site_ids`가 필요하다. 배관공에서는 파이프 렌치의 턱·손잡이와 작업할 은색 커플링의 근접 크롭이 필요하다. 펜트하우스에서는 호스트의 정체성 크롭과 엘리베이터 문턱–거실 축이 읽히는 공간 크롭만 사용한다.

### 3단계 · 시나리오

첫 배관공 비트는 밸브 돌리기, 렌치 꺼내기, 연결부 풀기, 살피기가 한 문장에 들어 있었다. 펜트하우스도 손짓, 회전, 보행, 다시 손짓하기가 결합됐다. `sub_beats`가 없는 복합 행동은 다음 단계로 넘기지 않는다.

```json
{
  "sub_beats": [
    {
      "id": "B02-a",
      "actor_subject_id": "host-seoa",
      "action": "presenting arm lowers to a natural walking position",
      "target_subject_id": null,
      "target_part_id": null,
      "result_state": "both arms rest naturally",
      "split_after": false
    },
    {
      "id": "B02-b",
      "actor_subject_id": "host-seoa",
      "action": "turns toward the living room and walks three steps",
      "target_subject_id": "skyline-penthouse",
      "target_part_id": "threshold-to-living-axis",
      "result_state": "continues facing away from camera with arms down",
      "split_after": true
    }
  ]
}
```

도구 사용 비트에는 `interaction_contract`가 필요하다. 이것은 `sub_beat_id`에 결속되며 어느 도구를 어느 대상 부품에 사용해 무엇이 변하고 무엇이 고정되는지를 고른다. 접근 각도와 화면 좌표는 촬영 결정이므로 4단계가 2단계 크롭과 시작판을 보고 구체화한다.

발화는 `onscreen_spoken / voiceover / none`을 구분하고 언어·립싱크 필요 여부를 기록한다. H3 프롬프트에는 승인된 대사를 넣지 않으며 원본 오디오도 사용하지 않는다. 비발화 shot은 입이 말하듯 움직이지 않는 것을 검수한다.

### 4단계 이후의 책임

카메라 정책은 H3 앵커 수와 분리한다.

- `natural`: 모델이 피사체 동작에 동기화된 작은 움직임을 선택할 수 있음
- `soft_follow`: 보행 피사체를 부드럽게 추종
- `locked`: 기계 접촉과 화면상 고정부 비교가 중요한 인서트
- `directed`: 하나의 명시적 팬·틸트·달리·줌

카메라가 움직이는 shot에서는 `camera viewpoint`를 불변량으로 두지 않는다. 세계 공간의 건축·가구·조명 정체성은 고정하고, 투영 변화와 새로 드러난 배경만 허용한다.

끝 이미지는 정확 동작의 영구 기본값으로 확정하지 않는다. 현재 과거 호환 컴파일러는 end state를 계속 기술하지만, 실제 H3 conditioning의 `first_only / paired` 선택은 별도 정책이며 다음 연구 결과로 용도를 제한한다.

## L1 · 인물 이동 카메라–앵커 실험

### 질문

1. 자연스러운 보행에는 locked, natural, soft-follow 중 무엇이 가장 안정적인가?
2. 검수된 끝 이미지도 회전·보행을 되돌리거나 마지막 포즈를 강제하는가?
3. soft-follow가 배경 구조 변화와 환각을 늘리는가?

### 고정 장면

펜트하우스 문턱 shot을 사용한다. 행동은 하나의 연속 동작으로 제한한다.

> 호스트가 들고 있던 팔을 내리고, 발·골반·몸통을 거실 방향으로 돌린 뒤 자연스럽게 세 걸음 걸어간다. 계속 실내를 향하고 팔은 내린 상태다. 다시 카메라를 향하거나 손을 들지 않는다.

5초, 동일 첫 이미지, 동일 정체성·공간 크롭, 동일 행동 프롬프트, 동일 시드 세트를 쓴다. 대사와 H3 오디오는 없다.

### 독립 변수

| 축 | 수준 |
|---|---|
| camera_policy | `natural`, `soft_follow`, `locked` |
| last_frame | `absent`, `present` |
| seed | 3개 반복 |

총 `3 × 2 × 3 = 18`개다. 각 camera policy 안에서 last-frame 쌍은 프롬프트·시드·첫 이미지·레퍼런스가 같고 끝 이미지 유무만 다르다. paired 끝판은 팔을 내리고 실내를 향한 상태여야 하며, camera policy별 예상 최종 구도와 일치하는지 사전 승인한다.

### 평가

- 올바른 회전과 깊이 방향
- 보행 중 팔 내림과 자연스러운 보폭
- 되돌아보기·역주행·재제스처 발생
- 카메라 추종의 동기와 부드러움
- 건축·가구 생성/삭제, 촬영 인력·장비 환각
- 조명 깜빡임과 프레임 간 노출 펌핑
- 인물 정체성과 신체 관통

1차 판정은 전체 영상을 본 사람의 pairwise 선택이다. AI는 고밀도 시간축 샘플로 별도 봉인 평가하며 사람 판정 전 공개하지 않는다.

### 채택 기준

- 한 camera policy가 3개 시드 중 2개 이상에서 같은 anchor 조건의 상대 정책보다 선호되고 치명 오류율도 낮아야 한다.
- paired는 first-only보다 끝 상태 도달을 높이면서 되돌림·재제스처·배경 변형을 증가시키지 않을 때만 허용한다.
- 예상상 `soft_follow + first_only`가 유력하지만 연구 전 기본값으로 확정하지 않는다.

## M1 · 기계 접촉 레퍼런스–앵커 실험

### 질문

1. 동작 가능성용 크롭이 정확한 도구·대상·접촉 각도를 개선하는가?
2. 시작판에 올바른 접촉 기하가 있어도 끝 이미지가 고정부·배관을 변형하는가?
3. 접근과 회전을 분리하면 물 분출·도구 소실·팔 관통이 줄어드는가?

### 고정 장면과 두 원자 행동

> 2026-08-26 해석 제한: 기존 입력판의 배관·커플링 외경이 렌치 턱이 물 수 있는 범위를 넘고, 렌치가 대상 축과 90°가 아니라 도구를 보여주기 위한 사선으로 배치됐다. 아래 설계의 독립 변수보다 먼저 고정되어야 할 입력 조건이 실패했으므로 24개의 점수·승자는 이 패킷 안의 후보 비교와 실패 분석에는 사용하되, 요인의 일반 효과를 확정하는 근거로 단독 사용하지 않는다.

카메라는 locked 인서트로 고정한다. 배경과 도구가방은 빼고 손·렌치·커플링·인접 고정 배관만 보이게 한다.

1. `seat_wrench`: 손에 든 렌치의 턱을 은색 커플링 외주에 맞추고 완전히 안착한다. 회전하지 않는다.
2. `turn_coupling`: 렌치가 이미 안착된 상태에서 손잡이를 아래로 작은 각도만큼 당겨 커플링만 약 15도 회전시킨다.

밸브 휠 돌리기와 가방에서 렌치 꺼내기는 별도 shot으로 남기며 이 실험에 섞지 않는다.

### 독립 변수

| 축 | 수준 |
|---|---|
| reference_pack | `identity_only`, `identity_plus_affordance` |
| last_frame | `absent`, `present` |
| task | `seat_wrench`, `turn_coupling` |
| seed | 3개 반복 |

총 `2 × 2 × 2 × 3 = 24`개다. affordance 조건만 파이프 렌치 턱·손잡이와 coupling-01의 motion-safe 크롭을 추가한다. 전체 보드는 어느 조건에도 넣지 않는다.

### 평가

- 올바른 도구 정체성과 단일 개수
- 지정 target part에만 접촉
- 렌치 턱·커플링 축·손잡이 방향의 물리적 정렬
- 손–도구와 도구–배관 관통 여부
- 커플링만 움직이고 인접 관·밸브 허브는 고정되는가
- 도구·마개·배관의 생성, 소실, 변형
- 금지한 물 분출 또는 캐릭터의 무반응

### 채택 기준

- affordance pack은 6개 비교 단위 중 4개 이상에서 target/contact 성공을 높이고 새 객체·형상 오류를 늘리지 않아야 한다.
- paired는 같은 reference 조건에서 first-only보다 기계 상태 성공을 높이면서 고정부 변형률을 늘리지 않을 때만 사용한다.
- 두 task 중 하나라도 원자 행동 성공률이 50% 미만이면 프롬프트를 늘리지 않고 시작판의 접촉 가시성과 2단계 motion crop을 다시 만든다.

### 재실험 전 기하 게이트

- `tool_capacity_mm / target_extent_mm >= 1.15`
- 안착 전 턱과 대상 사이의 여유 공간이 이미지에서 보여야 한다.
- 안착 후 두 접촉면이 대상의 반대편을 실제로 물어야 한다.
- 렌치 작용면과 커플링·배관 축은 `90° ± 5°`여야 한다.
- 이 정렬 때문에 렌치가 덜 잘 보이더라도 사선의 3/4 도구 과시 구도로 바꾸지 않는다. 도구 정체성은 별도 identity crop이 담당한다.

## 실행 순서

1. 1단계 상호작용 정의와 오디오 정책 작성
2. 2단계 motion-safe 선택 크롭 생성·사람 승인
3. 3단계 원자 sub-beat와 interaction contract 승인
4. 5단계 시작판 후보 3개 생성 후 한 장 선택
5. paired 셀에만 같은 시작판을 편집한 끝판 후보 3개 생성·쌍 승인
6. 한 시드로 14개 카나리아 생성
7. 입력 해시·영상 규격·블라인드 누출 확인
8. 나머지 두 시드 28개 생성
9. H3 원본 오디오 제거 후 블라인드 패킷 작성
10. AI 봉인 평가와 사람 전체재생 평가
11. 조건표 공개, pairwise 결과와 치명 오류율 분석

## 이번 연구에서 바로 채택하지 않는 것

- 한 번 이긴 후보를 4단계 기본 방식으로 승격하지 않는다.
- 모든 정확 동작에 끝 이미지를 요구하지 않는다.
- 모든 카메라를 locked로 만들지 않는다.
- 전체 레퍼런스 보드를 H3에 넣지 않는다.
- H3 생성 음성의 언어·대사·립싱크를 신뢰하지 않는다.
- 전체 프레임 픽셀 차이를 의미적 성공 점수로 사용하지 않는다.
