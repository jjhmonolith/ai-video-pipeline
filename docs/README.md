# 문서 안내

현행 제작 정본은 `pipeline-v3/`와 `video-pipeline-orchestrator` 스킬이다.
아래 `design/`, `governance/`, `research/`, `pipeline-v2-handoff.md`는 보존된
v2 설계 또는 연구 근거이며 v3 work order·receipt·stage skill·integrity
코드를 덮어쓰지 않는다.

- `pipeline-v3/README.md`: LLM 창작/결정론적 무결성 분리 구조
- `pipeline-v3/operations.md`: v3 상태기계 실행·게이트·모드 명령

- `project-overview.md`: 목적, 현재 구현 범위, 다음 단계
- `pipeline-v2-handoff.md`: 이전 beat 기반 1~4단계 구현의 보존 인수인계
- `governance/operating-rules.md`: 계약·승인·보존 규정
- `design/run-layout.md`: 현행 디스크 레이아웃
- `design/codex-image-generation.md`: Codex 앱·CLI 공용 2단계 이미지 생성 절차
- `design/shot-grammar.md`: 샷 설계 입력 자료
- `design/stage3-stage6-production-contract.md`: scene→shot, 시간, 신규 reference, 순차 take의 현행 계약
- `design/stage5-production.md`: 5A reference fulfillment과 5B start plate 실행
- `research/`: 규약의 근거가 된 조사

재구축 직전 전체 v2 스냅샷은
`archive/pipeline-v2-hybrid-2026-08-27/`에 있다.
