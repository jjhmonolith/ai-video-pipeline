# Archive Index

공개 Git 저장소에는 재현에 필요한 `pipeline-v2-hybrid-2026-08-27/` 기준본만 포함한다. 아래의 과거 production run, 미디어, 일회성 보고서·코드·조사 자료는 원본 작업 폴더에는 그대로 보존하지만 용량·개인 경로·미디어 권리 문제로 Git 배포에서는 제외한다.

## 2026-08-27 v2 hybrid snapshot

`pipeline-v2-hybrid-2026-08-27/`은 LLM 창작형 v3 재구축 직전에 보존한
소스·테스트·계약·문서·예제·프로젝트 스킬·README·프로젝트 메타데이터의
읽기 전용 기준본이다. 범위, 루트 해시, 제외 항목, 복원법은 그 안의
`ARCHIVE.md`에 기록했다. 기존 production run과 미디어는 복제하거나
변경하지 않았다.

2026-08-25에 현행 8단계 파이프라인과 분리한 보존 자료다. 의미 있는 제작물은 삭제하지 않았고 원래 내부 구조를 유지했다.

| 경로 | 크기 | 상태 | 보존 이유 |
|---|---:|---|---|
| `runs/1971-election/` | 약 604MB | 레거시 제작 런 | 인간 게이트·결정론적 오버레이·H3 모션 실험과 실패 기록 |
| `runs/supercar-review/` | 약 485MB | 레거시 제작 런 | 시트 미연결, 단계 분리, 상태쌍 등 v2 구조의 근거 |
| `runs/dry-run-pre-generation-v1/` | 약 120KB | 레거시 dry run | S0–S5 계약·프롬프트 초기안 |
| `runs/even-g2/` | 약 2.9MB | 초기 기획 자료 | 최초 브리프·샷리스트·공식 참고 이미지 |
| `reports/` | 약 248KB | 과거 감사 보고서 | 8월 22~24일 설계·프로세스 감사 |
| `docs/` | 약 72KB | 과거 설계·intake | S0–S12/9단계 시기의 문서 |
| `code/` | 약 20KB | 레거시 보조 코드 | 일회성 레이아웃 이관, 프로젝트별 어휘 검사 |
| `loose-artifacts/` | 약 480KB | 루트 임시 산출물 | 런에 귀속되지 않았던 그래프 이미지와 H3 시험 렌더 |

## 읽는 방법

- 당시 사실과 실패 원인은 각 run의 `TOPIC.md`, `ATTEMPT.md`, `NOTES.md`, `receipt.json`에서 찾는다.
- 내부의 절대경로와 상호 링크는 이동 전 위치를 기록한 역사적 증거일 수 있다. 재실행하려면 `archive/runs/...` 기준으로 경로를 조정한다.
- 레거시 단계 이름을 현행 이름으로 바꾸지 않는다. 이름 자체가 당시 실행 구조의 일부다.
- 현행 규약은 루트 `AGENTS.md`, `README.md`, `docs/pipeline-v3/`,
  `.agents/skills/video-pipeline-orchestrator/`, `src/ai_video_pipeline/v3/`를 따른다.
