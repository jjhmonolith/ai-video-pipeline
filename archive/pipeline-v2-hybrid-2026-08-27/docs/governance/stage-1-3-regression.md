# 공통 1–3단계 회귀 계약

`sky-village-plumber/v1-pilot`와 `luxury-penthouse-tour/v1-pilot`은 신·구 버전이 아니라 서로 다른 장르의 동등한 회귀 fixture다. 어느 한쪽의 창작 내용도 다른 쪽의 레퍼런스로 쓰지 않는다.

## 상태 수명주기

- `form_ok`: 파일·근거·정의 형식이 유효하다.
- `human_approved`: 모든 정의가 현재 definition digest로 사람 승인을 받았다. 승인 후 본문이 바뀌면 digest가 달라져 자동 무효화된다.
- `release_eligible`: `form_ok && human_approved`이고 미해결 direction impact가 없다.
- 2·3단계 draft는 미승인 상태에서도 만들 수 있지만 `draft_unapproved`를 유지한다. 공개·final 판단은 `release_eligible=false`인 입력을 수용해서는 안 된다.

Direction supplement가 들어오면 `01-premise/qa/direction-impact.json`이 subject, sheet, scenario의 기록 시각을 비교한다. 이전 산출물은 자동 호환으로 추측하지 않고 `revalidation_required`가 된다. 내용 충돌을 사람이 확인한 경우에만 `compatible`, 실제 재생성이 필요한 경우 `regeneration_required`로 별도 compatibility record에 기록한다.

## 조사와 정의

`research-plan.json`의 question 수가 계약 상한의 기준이다. 검색 호출 수와 evidence result 수는 별도 수치다. 정의의 `decisions`는 중요한 필드에 `user_mandated`, `evidence_supported`, `creative_choice`, `inferred`, `unresolved` 중 하나를 기록한다. `evidence_supported`만 직접 관련 evidence ID를 요구한다. 배관공의 과거 33개 일괄 목록은 삭제하지 않고 `evidence_context_legacy`로 이동했으며, 채택 근거로 인정하지 않는다.

## 시트

픽셀·해시 통과는 생성 완료일 뿐 semantic pass가 아니다. `panel-manifest.json`의 crop과 안전성 값은 사람이 실제 보드를 확인하기 전에는 `null`이고 `semantic-review.json`은 `human_review_required`다. Stage 3 이후는 승인된 crop만 identity/motion reference로 선택해야 한다. setting의 작은 무명 scale figure 같은 예외는 element 계약에 명시한다.

정의 digest는 두 층으로 기록한다. `definition_sha256`는 승인·근거·결정 이력까지 포함한 전체 기록 무결성이고, `definition_content_sha256`는 실제 이미지에 영향을 주는 시각 정의다. 관리 메타데이터만 보강됐을 때는 이미 맞는 프롬프트를 거짓 stale로 만들지 않지만, 외형·소품·공간 topology 같은 시각 내용이 바뀌면 반드시 재작성한다. 프롬프트는 자신의 element/kind에 적용되는 계약 조항만 포함해야 하며 다른 kind 전용 조항의 누출도 게이트 실패다.

## 시나리오

새 beat는 `primary_action`, `primary_visible_change`, `sub_beats`, `where_subject_id`, `sublocation_id`, `transition_requirement`, 명시적 `dialogue`, `cast_presence`, `visual_focus`, `object_roles`를 사용한다. 검증기는 보수적 한국어 발화 시간, 행동 시간, 호흡, 이동 여유를 분리해 계산한다. 카메라·렌즈·구도는 여전히 4단계 책임이다. `lesson`은 선택 사항이며 일반 형식은 `takeaway`, `viewer_promise`, `closing_intent`를 쓴다. 새 시나리오 생성은 `semantic-review.json`이 통과된 뒤 element별 `approved`·`safe_for_identity_reference=true`인 실제 crop만 입력한다. 검수 전 전체 보드를 이미지 입력으로 보내는 것은 금지하며 `--audit-only`는 기존 시나리오를 읽기만 한다.

## 기존 산출물 처리

과거 receipt의 digest는 바꾸지 않는다. 현재 계약과 다르면 stage별 `contract-compatibility.json`이 `accepted`, `revalidation_required`, `regeneration_required` 중 실제 상태를 기록한다. 기존 시나리오는 `--audit-only`로 receipt를 건드리지 않고 `semantic-check.json`만 갱신한다. 기존 시트도 이미지를 재생성하지 않고 `--audit-references`로 선택 계약과 review queue만 갱신한다.
