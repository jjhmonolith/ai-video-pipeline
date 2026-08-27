# Codex 앱·CLI 공용 시트 이미지 생성

## 결론

`02-sheet`의 이미지 렌더는 Codex 앱과 Codex CLI에서 같은 프로젝트 스킬과 같은 Python 확정기를 사용한다. 별도 `OPENAI_API_KEY` 없이 내장 이미지 생성 기능을 사용하며, 정식 시트는 실제 반환 파일에서 확인한 가로 `1672×941` 또는 세로 대응값 `941×1672`와 `high`를 계약한다.

공식 OpenAI 문서에 따르면 Codex CLI 대화형 세션에서도 `$imagegen`을 명시적으로 호출할 수 있고, 내장 이미지 생성은 `gpt-image-2`와 일반 Codex 사용량을 사용한다. 대량 생성은 API 사용을 권장한다.

- Codex 이미지 생성: https://learn.chatgpt.com/docs/image-generation
- Codex 스킬 위치와 CLI 호출: https://learn.chatgpt.com/docs/build-skills

## 공용 구성

| 구성 | 역할 |
|---|---|
| `.agents/skills/sheet-imagegen/SKILL.md` | 앱·CLI가 공통으로 읽는 제작 절차 |
| `02-sheet/prompts/*.json` | 이미지 모델에 보낼 확정 프롬프트 |
| `02-sheet/qa/codex/manifests/*.json` | 생성할 대상·크기·해시·경로 작업 명세 |
| `02-sheet/qa/codex/candidates/` | Codex가 반환한 수정 전 원본 |
| `02-sheet/output/sheets/` | 다음 단계가 읽는 채택 시트 |
| `02-sheet/receipt.json` | 공급자 중립 `sheet-receipt.v2` 영수증 |

Python은 manifest 준비와 결과 검증·확정만 한다. 실제 생성 호출은 앱 또는 CLI의 Codex가 수행한다. 그래서 `--generator codex` 명령만 일반 셸에서 실행해도 그림이 저절로 생성되지는 않는다.

프롬프트 팩이 아직 없으면 같은 Codex 경로의 로컬 구조화 컴파일러가 계약·정의·시트 명세·적용 조항을 해시로 결박해 작성한다. 이 작업도 네트워크와 API 키를 사용하지 않는다.

## Codex 앱

프로젝트를 연 상태에서 다음처럼 요청한다.

```text
sheet-imagegen으로 runs/<topic>/attempts/<attempt>의 2단계 시트를 생성해줘.
```

스킬이 자동 선택되지 않으면 앱의 스킬 선택기에서 `sheet-imagegen`을 고른다. 새로 추가한 스킬이 보이지 않으면 프로젝트를 다시 열거나 Codex를 재시작한다.

## Codex CLI

프로젝트 루트에서 대화형 CLI를 열고 스킬을 호출한다.

```text
codex
$sheet-imagegen runs/<topic>/attempts/<attempt>의 2단계 시트를 생성해줘.
```

CLI는 현재 작업 디렉터리부터 상위 루트까지 `.agents/skills`를 탐색하므로 이 프로젝트 루트 또는 그 하위에서 실행한다.

## 수동 준비·확정 명령

스킬이 내부적으로 사용하는 명령은 다음과 같다.

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --project . --no-editable \
  ai-video-sheets runs/<topic>/attempts/<attempt> \
  --generator codex --compose-only
```

위 명령은 `sheet-prompt-pack.v2`를 로컬에서 작성하며 `api_called: false`를 기록한다.

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --project . --no-editable \
  ai-video-sheets runs/<topic>/attempts/<attempt> \
  --generator codex [--only element ...] [--draft]
```

명령이 출력한 manifest를 Codex가 읽고 각 job의 `imagegen_prompt`를 그대로 `$imagegen`에 전달한다. 이 문자열은 `prompt_path`의 원문과 계약에서 계산한 래스터/high 출력 지시를 결합한 실제 생성 프롬프트이며 `imagegen_prompt_sha256`으로 결박된다. 반환 PNG를 각 `candidate_path`에 저장한 뒤 확정한다.

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --project . --no-editable \
  ai-video-sheets runs/<topic>/attempts/<attempt> \
  --generator codex \
  --finalize-manifest <manifest.json> \
  --codex-surface desktop   # CLI는 cli
```

## 덮어쓰기와 재시도

- 채택 시트가 있으면 준비 단계가 기본적으로 `output-exists`로 건너뛴다.
- 사용자가 교체를 명시했을 때만 `--force`를 사용한다.
- 확정기는 기존 채택본을 `02-sheet/rejected/superseded-<manifest-id>/`로 옮긴 뒤 새 후보를 채택한다.
- manifest 뒤 계약·프롬프트·요소 정의가 바뀌면 stale manifest를 버리고 공식 composer로 새 manifest를 만든 뒤 같은 하네스 시도를 계속한다.
- 후보의 실제 픽셀이 허용오차보다 작으면 후보를 `qa/codex/candidates/`에 증거로 남기고 다음 변주 시도를 생성한다. 확대하지 않으며 전체 10회 실패 때만 마지막 후보를 semantic review로 넘긴다.
- 각 재시도는 구조화 prompt와 계약 raster/high 요청을 보존하고 직전 실패 기준을 서로 다른 `variation_strategy`로 보정한다.
- 실패한 후보를 채택본 경로에 직접 복사하지 않는다.

## 영수증 v2

정식 규격은 `contracts/schemas/sheet-receipt.v2.schema.json`이다.

Codex 기록의 핵심 필드:

```json
{
  "schema_version": "sheet-receipt.v2",
  "generator_modes": ["codex"],
  "sheets": [{
    "generator": {
      "mode": "codex",
      "invocation": "interactive-imagegen-skill",
      "surface": "desktop",
      "model": "gpt-image-2",
      "usage_accounting": "codex-general-usage",
      "token_detail": "not-exposed"
    },
    "requested": [1672, 941],
    "source_dimensions": [1672, 941],
    "quality": "high",
    "prompt_sha256": "...",
    "imagegen_prompt_sha256": "...",
    "definition_sha256": "...",
    "definition_content_sha256": "...",
    "definition_record_sha256_current": "...",
    "contract_sha256": "...",
    "source_sha256": "...",
    "sha256": "..."
  }]
}
```

API 토큰 수치를 임의로 환산하지 않는다. 대신 어느 표면에서 어떤 방식으로 생성했고 어떤 프롬프트·정의·계약·파일에 묶였는지를 남긴다. `definition_sha256`는 프롬프트 팩이 작성될 당시 전체 정의 기록, `definition_content_sha256`는 시각 내용, `definition_record_sha256_current`는 생성 확정 시점의 전체 기록이다. 근거·승인 같은 관리 메타데이터만 추가된 경우에는 시각 프롬프트를 거짓 stale로 만들지 않되, 최종 receipt에는 현재 기록 digest를 남긴다.

`high`는 요청 품질이지 실제 해상도의 증명이 아니다. 실제 해상도는 `source_dimensions`로 판정한다. 판은 이 시트 규칙을 사용하지 않고 `contract.image_plan("plate")`가 계산한 영상 프레임 인접 크기를 사용한다.

## 보장 범위

지원:

- Codex 앱의 대화형 이미지 생성
- Codex CLI의 대화형 `$imagegen`
- Codex IDE의 대화형 이미지 생성
- API 키 없는 개별 시트 생성과 소규모 반복

별도 API 경로가 필요한 경우:

- 무인 `codex exec` 또는 CI에서 확정적 배치 실행
- 대량 생성
- API 요청 ID·토큰 사용량·과금 정보를 반드시 수집해야 하는 실행
