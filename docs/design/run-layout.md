# 현행 런 폴더 규약

`src/ai_video_pipeline/run_layout.py`가 실행 가능한 기준이며 이 문서는 그 규약을 설명한다.

## 구조

```text
runs/<topic>/
  TOPIC.md
  attempts/<attempt>/
    ATTEMPT.md
    VERSION.json             선택 사항. fork·snapshot을 쓸 때 생성
    tools/                   해당 attempt에서만 쓰는 얇은 실행 도구
    01-premise/
    02-sheet/
    03-scenario/
    04-shot-design/
    05-plate/
    05.5-motion-prompt/
    06-motion/
    07-edit/
    08-review/
      NOTES.md
      prompts/
      output/
      rejected/
      qa/
      receipt.json
```

각 단계의 공통 하위 폴더 의미:

- `prompts/`: 모델이나 외부 도구에 실제로 보낸 요청
- `output/`: 다음 단계가 읽는 채택 산출물
- `rejected/`: 탈락 후보, 대체된 판본, 재시도 결과
- `qa/`: 측정, 콘택트시트, 검사 결과, 실행 진단 로그
- `receipt.json`: 생성 모드·실행 표면·모델·파라미터·입력 해시·계약 digest·결과 경로. 2단계는 `contracts/schemas/sheet-receipt.v2.schema.json`을 따른다.
- `NOTES.md`: 재시도와 되돌림을 포함한 단계별 판단 기록

## 규칙

1. 한 attempt의 파일은 그 attempt 안에 둔다. 다른 attempt의 산출물을 공유 경로로 직접 읽지 않는다.
2. 산출물은 만든 단계가 소유한다. 다른 단계가 필요하면 복사하지 않고 경로로 참조한다.
3. 다음 단계가 읽는 채택본만 `output/`에 둔다. 비교 후보와 폐기본은 `rejected/`에 둔다.
4. 같은 방법의 반복은 같은 단계에 남긴다. 가정이나 방법이 달라지면 새 attempt로 fork한다.
5. 단계 번호는 실행 순서이지 완료율이 아니다. 되돌아간 사실은 `NOTES.md`와 영수증에 남긴다.
6. 의미 있는 프롬프트·영수증·판정·결과물은 삭제하지 않는다. 끝난 attempt 전체를 `archive/runs/`로 옮긴다.
7. `.DS_Store`, `__pycache__`, `.pytest_cache`처럼 재생성 가능한 캐시는 보존하지 않는다.

## 현행과 레거시

현행은 Stage 05와 06 사이의 `05.5-motion-prompt`를 포함한 9단계다. 과거 attempt의 9~10단계 이름은 아카이브 안에서 그대로 유지한다. 과거 폴더를 현행 이름으로 일괄 변경하면 당시 도구·프롬프트·문서의 경로 증거가 깨지므로 마이그레이션하지 않는다.

현행 attempt 안에는 현행 단계만 허용한다. 검사:

```bash
PYTHONPATH=src python3 -m ai_video_pipeline.run_layout runs/sky-village-plumber
```

## 임시 출력

루트 `renders/`는 런타임 연결 시험에만 쓴다. 채택할 파일은 즉시 해당 attempt의 단계 `output/` 또는 `rejected/`로 옮기고 영수증에서 참조한다. 루트 임시물은 다음 정리 때 아카이브하거나 제거할 수 있다.
