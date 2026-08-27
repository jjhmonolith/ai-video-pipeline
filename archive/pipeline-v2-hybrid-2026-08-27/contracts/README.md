# 계약 안내

## 실행 계약

- `human-gates.v1.json`: G1–G10 판단 경로, Judgment Packet, Feedback Delta 규약. CLI와 테스트가 읽는다.
- `<attempt>/01-premise/output/contract.json`: 이 폴더 밖의 각 attempt에 있으며 해당 제작을 직접 구속한다.

## 산출물 영수증 스키마

- `schemas/sheet-receipt.v2.schema.json`: API와 Codex 앱·CLI 생성물을 같은 구조로 기록하는 2단계 시트 영수증 규격

`generator.mode`은 `api`, `codex`, `reuse`를 구분한다. Codex 직접 생성은 `generator.surface`에 `desktop`, `cli`, `ide`, `cloud` 중 실제 표면을 기록하고, 노출되지 않는 API 토큰 수치를 추정하지 않는다.

## 참고 계약

`reference/`의 두 파일은 `status: design-only`, `implementation_authority: none`인 설계 자료다.

- `reference/stage-tool-catalog.v1.json`: 과거 S0–S12 도구 카탈로그
- `reference/performance-learning-loop.v1.json`: 향후 학습 원장·승격 정책 참고안

참고 계약은 현행 8단계 레이아웃을 구속하지 않는다. 구현에 사용할 때는 현행 역할과 단계에 맞춘 새 버전을 만들고 검증 코드를 연결해야 한다.
