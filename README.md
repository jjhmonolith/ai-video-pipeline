# AI Video Pipeline v3

모든 창작 판단을 단계별 LLM 스킬이 작성하고, Python은 누락·형식·파일·해시·픽셀·시간 합계·재시도 순서·상태 전이·권한 경계만 검증하는 영상 제작 파이프라인이다.

## 다운로드와 업데이트

Git으로 설치하는 방식이 전체 스킬과 문서를 유지하면서 업데이트하기 가장 쉽다.

```bash
git clone https://github.com/jjhmonolith/ai-video-pipeline.git
cd ai-video-pipeline
uv sync --frozen
```

기존 checkout은 작업 파일이 깨끗할 때만 안전한 fast-forward 업데이트를 허용한다. `runs/`의 제작물은 Git 대상이 아니므로 보존된다.

```bash
.venv/bin/python scripts/update_from_github.py --check
.venv/bin/python scripts/update_from_github.py --sync
```

Git을 사용하지 않을 컴퓨터는 GitHub Releases의 버전별 portable ZIP을 내려받는다. ZIP은 불변 배포본이므로 새 버전이 필요하면 새 ZIP으로 교체하고, 기존 `runs/`는 별도 위치에서 보존한다. 자세한 설치와 검증 절차는 [`PORTABLE_SETUP.md`](PORTABLE_SETUP.md)에 있다.

## 현재 정본

- 제작 진입점: `.agents/skills/video-pipeline-orchestrator/SKILL.md`
- 공통 회귀 인사이트: `.agents/skills/video-pipeline-orchestrator/references/insights.md`
- 단계별 창작 규약: `.agents/skills/video-stage*/references/authoring.md`
- 상태기계: `src/ai_video_pipeline/v3/orchestrator.py`
- 결정론적 무결성 검사: `src/ai_video_pipeline/v3/integrity.py`
- 운영 문서: `docs/pipeline-v3/`
- v2 보존 기준본: `archive/pipeline-v2-hybrid-2026-08-27/`

새 제작에서 v2의 prompt composer나 stage compiler를 창작 정본으로 호출하지 않는다. `src/ai_video_pipeline/`의 비-v3 모듈은 현재 생성 서비스와의 저수준 호환 어댑터 또는 역사 자료이며, v3 스킬이 작성한 결정을 실행하는 범위에서만 사용한다.

## 구조

```text
사용자 방향
  -> 오케스트레이터 work order
  -> 현재 단계 LLM 스킬이 산출물 1개 작성/생성
  -> Python 무결성 검사
  -> fresh-context LLM 의미·시각 검수
  -> 실패 증거를 반영한 변주 재시도(최대 10회)
  -> receipt 또는 설정된 사람 게이트
  -> 다음 단계
```

| 단계 | LLM이 소유하는 판단 | 핵심 결과 |
|---|---|---|
| `01-premise` | 방향 해석, 런타임, 프레임, 주체, 제작 계약 | premise artifact |
| `02-sheet` | 원문·정본 명세가 결박된 구조화 메타 프롬프트, 16:9 가로 9패널 시트 설계, 이미지 프롬프트와 선발 | reference boards |
| `03-scenario` | 시퀀스·신·사건·드라마 진행·신규 레퍼런스 부채 | scenario |
| `04-shot-design` | 블로킹·커버리지·셋업·샷·카메라·연기·정확한 시간 | shot design |
| `05-plate` | 신규 시트/설명서, 전체 레퍼런스 선검수, 시작판 | references + start plates |
| `05.5-motion-prompt` | 확정판을 실제로 보고 시나리오·연기·카메라·촬영기법·시간을 C01 프롬프트로 보강 | final C01 prompts |
| `06-motion` | 확정 C01 프롬프트 실행, 실패 영상 증거 기반 C02–C10 변주·선발 | motion takes |
| `07-edit` | 트림·리타이밍·전환·사운드·정보 레이어·조립 | master |
| `08-review` | 증거 기반 결함 처분과 내부 릴리스 적합성 | final review |

## 핵심 동작

- 기본은 `normal` 모드다. 1·5·6·7·8단계 뒤 사람 게이트가 있다. 5.5단계는 새 사람 게이트 없이 6단계로 이어진다.
- 사용자가 해당 attempt에 `fast_track`을 명시하면 내부 승인 중단 없이 8단계까지 진행한다. 외부 게시·업로드·구매·메시지·계정 권한은 포함하지 않는다.
- 4단계를 통과하면 별도 사전 승인 없이 5단계 레퍼런스/시작판 제작에 바로 진입한다.
- 후보를 세 장 선생성하지 않는다. 한 장 또는 한 take를 만들고 실제 결과를 검수하며, 실패한 경우에만 서로 다른 전략으로 최대 10회 재시도한다.
- fast-track의 10회차에는 비안전 품질 결함만 증거와 함께 `accepted_defect`로 남길 수 있다. 안전·권한·계약 실패는 자동 통과하지 않는다.
- 독립 이미지/샷 작업은 서브에이전트로 병렬화할 수 있지만, 개별 작업의 재시도는 순차이며 최종 artifact·receipt·상태 전이는 주 에이전트가 담당한다.
- 시트와 판의 공급자 픽셀이 요청값에서 축별 `max(1px, min(16px, 1%))` 이내로 어긋나면 경고로 수용한다. 방향 오류나 큰 축소는 실패다.
- Stage 02 시트는 영상 프레임 비율을 따르지 않는다. 세로·정사각 영상도 `1672x941` 16:9 가로 레퍼런스 보드로 만들며, character·subject·setting별 정본의 9개 정보 패널과 내부 세부 뷰 수를 유지한다.

## 단계 간 주요 경계

Stage 01이 전체 런타임 계약을 정하며 45초는 기본값이 아니다. Stage 03은 촬영법보다 시퀀스·신·사건을 먼저 설계하고, 장면 사건량의 현실적인 편집 범위만 추정한다. 이야기상 필요한 새 소품과 상태를 만들 수 있으며 `NEW-*` 레퍼런스 부채로 기록한다.

Stage 04가 실제 촬영 방법론으로 신을 블로킹·커버리지·셋업·샷으로 분할한다. 카메라 이동/고정, 구도, 연기 단계, 샷 길이는 LLM이 장면 의도에 따라 결정한다. 슬로모션·시간정지·오비트/불릿타임·타임랩스 등은 주체·세계·카메라의 시간 영역을 따로 기록한다. 두 사람이 보이는 프레임을 `single`로 표기하지 않는다.

Stage 05는 Stage 02 레퍼런스와 Stage 03의 새 부채를 모두 검수한 뒤에만 의존 시작판을 만든다. 각 판 검수에는 실제 바인딩 레퍼런스 이미지를 함께 사용하며, 판 반려와 재생성은 Stage 05만 담당한다. Stage 05.5는 채택판과 바인딩 레퍼런스를 실제로 보고 Stage 03–04 의도를 그 픽셀에서 실행 가능한 최종 C01 프롬프트로 번역한다. 허용 결론은 `ready`와 `ready_with_adaptation`뿐이며 이미지를 다시 만들지 않는다. Stage 06은 그 프롬프트를 C01에 그대로 사용하고, 직전 영상 후보 실패가 기록된 경우에만 C02 이후 프롬프트를 새로 쓴다.

## 시작

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m ai_video_pipeline.v3.cli \
  init runs/<production>/attempts/<attempt> \
  --direction "<사용자 방향 원문>" --mode normal --by user --reason "new production"

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m ai_video_pipeline.v3.cli \
  work runs/<production>/attempts/<attempt>
```

실제 제작은 CLI 단독으로 창작물을 자동 작성하는 방식이 아니다. `work`가 지정한 단계 스킬을 Codex가 읽어 artifact/media를 작성하고, CLI가 그것을 검증·승격한다. 자세한 루프는 `docs/pipeline-v3/operations.md`에 있다.

다른 컴퓨터로 옮길 때는 실행 환경이나 비밀정보를 통째로 복사하지 말고, 허용 목록과 SHA-256 매니페스트를 사용하는 휴대용 번들을 만든다.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/package_v3_portable.py
```

설치·무결성 검사와 컴퓨터별 이미지/영상 생성 환경 연결 범위는 [`PORTABLE_SETUP.md`](PORTABLE_SETUP.md)에 정리되어 있다.

## 영상 역설계: 완성 영상 → 생성 가능한 시나리오·컷 계약

완성 MP4를 숏별로 분해하고 Hermes 멀티모달 분석을 결합해 `scenario-and-cut-design.md`, `shot-contracts.json`, 모바일 HTML을 생성한다.

```bash
PYTHONPATH=src .venv/bin/python -m ai_video_pipeline.reverse.cli analyze input.mp4 --out runs/reverse/example
PYTHONPATH=src .venv/bin/python -m ai_video_pipeline.reverse.cli semantic runs/reverse/example --mode auto
PYTHONPATH=src .venv/bin/python -m ai_video_pipeline.reverse.cli compile runs/reverse/example
PYTHONPATH=src .venv/bin/python -m ai_video_pipeline.reverse.cli validate runs/reverse/example --require-semantic
```

자세한 사용법과 정확도 경계는 [`docs/video-reverse-engineering.md`](docs/video-reverse-engineering.md)를 본다.

## 확인

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m unittest \
  tests.test_v3_integrity tests.test_v3_orchestrator -v
```

기존 v2 소스·테스트·계약·문서·스킬은 아카이브에 원형으로 보존했고, 기존 `runs/` 및 미디어는 수정하지 않았다.
