# 영상 → 시나리오·컷 설계 역설계 도구

`ai-video-reverse`는 완성 영상을 기계적으로 측정한 뒤 Hermes의 멀티모달 분석을 결합하여 영상 생성 AI가 사용할 수 있는 시나리오와 Shot Contract로 변환한다.

## 책임 분리

```text
원본 영상
  → ffprobe 기술 정보
  → FFmpeg 장면 점수 기반 숏 경계 후보
  → 숏별 MP4 + 시작/중간/끝 프레임 + 6프레임 콘택트시트
  → Hermes native video analysis 시도
  → 영상 전달이 실제 시각 증거를 노출하지 않으면 콘택트시트 vision fallback
  → semantic.json (LLM 저작)
  → scenario-and-cut-design.md + shot-contracts.json + report.html
```

Python은 시간·파일·해시·숏 후보·증거 추출·형식·렌더링만 담당한다. 이야기 기능, 행동, 촬영 의도, 생성 프롬프트는 실제 영상/프레임을 본 멀티모달 모델이 작성한다.

## 설치

프로젝트 루트에서:

```bash
uv sync
uv run ai-video-reverse --help
```

`ffmpeg`와 `ffprobe`가 PATH에 있어야 한다. 의미 분석에는 설치된 Hermes Agent와 Hermes가 사용할 수 있는 vision/video 모델이 필요하다.

## 사용

### 1. 측정·증거 추출

```bash
uv run ai-video-reverse analyze input.mp4 \
  --out runs/reverse/my-video \
  --threshold 0.30 \
  --min-shot 0.25
```

주요 산출물:

- `source.json`: 원본 경로, SHA-256, 코덱·크기·FPS·오디오 정보
- `measurements.json`: 컷 경계 후보와 정확한 시간
- `shots/S###/clip.mp4`: 숏별 영상
- `shots/S###/start.jpg`, `middle.jpg`, `end.jpg`
- `shots/S###/samples/*.jpg`: 시간 순서 6프레임
- `shots/S###/contact-sheet.jpg`: 모션 변화 판독용 콘택트시트
- `semantic-request.json`: 전체 영상/숏별 분석 계약

### 2. Hermes 의미 분석

```bash
uv run ai-video-reverse semantic runs/reverse/my-video --mode auto
```

모드:

- `auto` (기본): native video를 먼저 시도하고, 모델이 영상이 보이지 않는다고 응답하면 시간표시 콘택트시트로 자동 전환
- `video`: native video만 사용. 실제 영상 증거가 전달되지 않아도 fallback하지 않으므로 진단용
- `frames`: 6프레임 콘택트시트만 사용. 행동은 샘플 사이의 가시적 상태 변화로만 표현

특정 모델을 지정하려면:

```bash
uv run ai-video-reverse semantic runs/reverse/my-video \
  --model google/gemini-2.5-flash
```

모든 원응답은 `semantic-raw/`에 보존되고, 정규화된 결과는 `semantic.json`에 저장된다.

### 3. 생성 문서 컴파일

```bash
uv run ai-video-reverse compile runs/reverse/my-video
```

- `scenario-and-cut-design.md`: 사람이 읽는 시나리오·컷 설계
- `shot-contracts.json`: 영상 생성 파이프라인이 읽는 구조화 계약
- `report.html`: 모바일에서 검토하는 시각 보고서

### 4. 검증

```bash
uv run ai-video-reverse validate runs/reverse/my-video --require-semantic
```

검증 항목은 원본 길이와 숏 길이 합, 경계 연속성, 클립/프레임/콘택트시트 존재, Shot Contract 개수다.

## Shot Contract 핵심 필드

각 숏은 다음을 포함한다.

- 원본 타임코드와 증거 파일
- 서사 기능, 진입 상태, 행동, 연기, 종료 상태
- 피사체, 배경, 구도, 앵글, 렌즈 의도, 카메라 움직임
- 조명과 색
- 대사·앰비언스·음악·효과음
- 전환과 화면 텍스트
- 생성 프롬프트와 negative prompt
- `must_show` / `must_not_show`
- 첫/끝 레퍼런스 프레임
- confidence와 증거 타임스탬프

## 정확도 경계

- FFmpeg scene score는 **숏 경계 후보**를 찾는다. 플래시, 디졸브, 화면 녹화, 빠른 오버레이는 오검출할 수 있으므로 대표 영상에서 임계값을 검증해야 한다.
- 숏은 편집 없는 연속 구간이고, 신은 여러 숏을 의미적으로 묶은 단위다. 신 그룹화는 멀티모달 판단이다.
- 콘택트시트 모드는 프레임 사이의 상태 변화는 관찰할 수 있지만 연속 움직임·정확한 속도·오디오는 증명하지 못한다. `evidence_mode`에 이 경계가 기록된다.
- 현재 Hermes native video 요청이 성공 응답을 반환하더라도 선택된 모델/라우터가 실제 영상 픽셀을 노출하지 않을 수 있다. `auto` 모드는 “no video/no frames/not accessible” 계열 응답을 감지해 vision fallback으로 전환한다.
- 채널 패턴 분석은 이 도구를 영상별로 실행한 뒤 별도의 집계 단계에서 숏 길이 분포, 반복 서사, 구도, 인물·행동, 카메라·편집 문법을 비교해야 한다.
