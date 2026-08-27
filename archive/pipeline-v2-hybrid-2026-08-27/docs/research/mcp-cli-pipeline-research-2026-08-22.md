# AI 영상 생성 MCP 재현성·아키텍처 연구

> 기준일: 2026-08-22  
> 질문: `How Claude Replaced Higgsfield (Build This Free MCP)`를 실제로 따라 만들 수 있는가? MCP·CLI·워크플로 엔진 중 무엇이 운영에 적합한가?  
> 결론 상태: `architecture-recommendation / implementation-ready / provider-benchmark-required`

## 한 줄 결론

**따라 만들 수 있다. 하지만 “MCP만 만들기”가 아니라 `Python 파이프라인 코어 + CLI + 얇은 MCP + HyperFrames/FFmpeg 렌더러`로 구현하는 편이 낫다.** MCP는 에이전트가 조작하는 리모컨이고, 비용·재시도·작업 상태·자산·QA를 책임지는 본체는 별도의 durable pipeline이어야 한다.

## 1. 기준 영상 판정

기준 영상은 Calvin Hia의 2026-08-19 영상(12:22)으로, Claude/Codex가 KIE.ai의 여러 이미지·영상·음악 모델을 호출하게 하는 범용 MCP를 시연한다. 영상 설명의 실제 구현체는 공개 저장소 [`mrdainami/kie-mcp`](https://github.com/mrdainami/kie-mcp)이며 MIT 라이선스다. 저장소는 5개 범용 도구만 노출한다.

- `kie_post`: 생성 작업 제출
- `kie_get`: 작업 상태 조회
- `kie_upload_file`: 입력 자산 업로드
- `kie_download`: 결과 보존
- `kie_fetch_model_docs`: 현재 모델 스키마 조회

KIE 공식 문서와 구현체 모두 생성이 비동기임을 전제로 한다. 일반 흐름은 `submit → taskId 즉시 보존 → webhook 또는 polling → 결과 다운로드`다. KIE의 공식 문서에는 Market 공통 task 조회, 파일 업로드, 잔여 크레딧, webhook 서명 검증, Veo/Runway/Seedance/Kling/Wan 등 모델별 문서가 존재한다.[S1][S2][S9]

### 그대로 믿으면 안 되는 부분

- **“무료 MCP”는 맞지만 생성이 무료라는 뜻은 아니다.** 서버 코드는 무료이고 KIE 모델 호출은 크레딧을 소비한다.
- **“Higgsfield 대체”는 조작면 대체에 가깝다.** 대화형 생성·모델 선택은 대체하지만 Higgsfield의 UI, 큐레이션, 프리셋, 에셋 관리, 품질 선택 경험 전체를 자동으로 대체하지 않는다.
- 영상은 `taskId` 유실, 중복 submit 과금, 웹훅 위조, URL 만료, 모델 스키마 변화, 비용 상한, 대량 배치 복구를 충분히 다루지 않는다.
- 공개 MCP는 유용한 connector지만 production job ledger나 shot-level provenance 시스템은 아니다.

### 영상이 실제로 보여준 범위

- `02:27–04:11`: 공개 repo 자체가 아니라 `/generate-mcp`라는 별도 Claude skill을 이용해 MCP 생성을 지시한다.
- `04:11–06:19`: 요구사항·API key·저비용 실호출 허용·설치 대상을 대화로 정한다.
- `06:19–07:13`: 생성된 `.mcpb`를 Claude Desktop에 설치한다.
- `07:13–07:40`: Seedance 계열 4초 UGC 영상 1건을 생성한다.
- 이후는 구체적인 서버 구현·복구 시험보다 응용 skill·agent team·사업 철학 설명이다.

따라서 **영상만 보고 동일 구현을 재현하기는 어렵지만, 공개 repo와 가이드까지 사용하면 MVP 복제 가능성은 높다.** 공개 서버는 강타입 KIE SDK라기보다 host·workspace 제한을 둔 HTTP proxy다. `list_models`, `get_model_schema`, `get_price`, `get_balance`, `cancel_generation` 같은 domain-level 도구는 별도로 제공되지 않는다. 새 모델도 자동 발견·동기화하는 것이 아니라 에이전트가 해당 문서 경로를 알아내 `kie_fetch_model_docs`로 읽는 방식이다.

## 2. 긴 영상 중심 close-read 결과

| 영상 | 날짜 / 길이 | 확인한 구현 패턴 | 구현체·템플릿 상태 | 판정 |
|---|---:|---|---|---|
| [Claude + ComfyUI](https://www.youtube.com/watch?v=nSS_Wi7f2Ww) | 2026-04-13 / 18:50 | Claude Code가 ComfyUI JSON과 runner를 만들고 Cloud API로 병렬 생성 | 공개 prompt, Comfy 공식 API/MCP 존재 | 자연어 graph 생성은 가능하지만 복잡한 60+ node graph는 실패·과설계가 있었고 최종 영상 품질도 미검증 |
| [Local AI VFX masterclass](https://www.youtube.com/watch?v=_n0ir5V5tX4) | 2026-03-30 / 19:12 | mask + ControlNet + reference + prompt, SAM/Depth/Canny/Pose, ComfyUI·Blender | 무료 workflow·guide와 RunPod template 제공, 고급 loop는 유료 | “프롬프트 한 번”보다 통제 레이어와 반복 선택이 품질의 핵심 |
| [Claude Code full video editing](https://www.youtube.com/watch?v=XeTAlZiIWHE) | 2026-06-29 / 22:31 | WhisperX rough cut → HyperFrames graphics → 사람의 second pass → captions/music/export | HyperFrames는 Apache-2.0 공개; 제작자의 전체 preset/skill bundle은 유료 | 편집은 결정론적 코드 렌더러가 적합. 첫 graphics pass 22분, 정교화는 약 2시간으로 사람 검수가 여전히 핵심 |
| [n8n + FFmpeg](https://www.youtube.com/watch?v=okesXuYa-UE) | 2025-06-09 / 45:12 | self-hosted n8n 컨테이너에 FFmpeg를 포함해 merge/concat | 설명은 상세하지만 template은 유료 커뮤니티 | 최종 합성은 생성 API가 아니라 FFmpeg/코드 렌더러가 저렴하고 재현 가능 |
| [Faceless factory live build](https://www.youtube.com/watch?v=6bBWmnv8Q8o) | 2026-02-01 / 37:54 | create → wait → get → publish의 no-code 흐름 | Blotato community node/API 중심 | 입문에는 좋지만 고정 wait와 수동 retry는 production 기준에 부족 |
| [100 long-form videos](https://www.youtube.com/watch?v=tboScAwJCAE) | 2025-11-18 / 38:06 | Sheets를 상태판으로 사용하고 scene split, API generate/get, Drive/YouTube 연결 | n8n workflow 설명; 유료 서비스 의존 | 구조화 출력·scene 단위 분리는 유효하나 Sheets를 authoritative DB로 쓰고 고정 2분 wait를 두는 것은 취약 |
| [InfiniteTalk long-form](https://www.youtube.com/watch?v=fYkLETrdtws) | 2025-10-28 / 18:10 | TTS submit/poll → avatar video submit/poll → Sheets update | n8n template은 커뮤니티 제공 | switch/poll/fallback이 가장 production에 가깝다. 5–6분 영상 생성 약 30분이라는 실측도 제공 |
| [Higgsfield + Claude editing](https://www.youtube.com/watch?v=vI4RdXMSq8c) | 2026-07-20 / 21:27 | Whisper·FFmpeg·HyperFrames·Higgsfield B-roll을 결합 | HyperFrames 공개 | Higgsfield는 전체 파이프라인이 아니라 생성 B-roll provider 한 칸으로 치환 가능 |

### 영상들에서 반복 확인된 공통 구조

1. **기획/shot decomposition**: LLM이 brief를 scene·shot schema로 바꾼다.
2. **생성은 비동기 provider 작업**: submit과 result retrieval을 분리한다.
3. **한 번의 생성보다 후보 생성·선택**이 중요하다.
4. **편집·자막·합성은 결정론적 도구**(FFmpeg, HyperFrames)가 적합하다.
5. **사람의 second pass**가 AI 초안과 사용 가능한 결과를 가른다.
6. 긴 영상의 다수 구현은 고정 wait, Sheets 상태, 유료 template에 기대며 idempotency·보안·회귀 테스트는 약하다.

### 추가 장시간 후보 12개 — metadata·설명 선별

아래 목록은 `yt-dlp`로 게시일·길이·설명·챕터·외부 링크를 확인해 우선순위를 매긴 것이다. 위 표에서 `close-read`로 명시한 영상 외에는 **metadata-screened 후보**이며, 내용 전체를 독립 검증한 것으로 간주하지 않는다.

| 우선 | 영상 | 날짜 / 길이 | 구현 초점 | 공개 자료 |
|---:|---|---:|---|---|
| 1 | [How I Fully Automated My Video Editing](https://www.youtube.com/watch?v=XeTAlZiIWHE) | 2026-06-29 / 22:31 | Claude Code end-to-end 편집 | HyperFrames 공개 repo; 전체 preset은 유료 |
| 2 | [n8n Zero to Hero Course](https://www.youtube.com/watch?v=UIf-SlmMays) | 2025-12-11 / 3:35:07 | 인증·HTTP·AI agent·Vertex AI 영상·Drive/Telegram·subworkflow | hands-on labs 링크 |
| 3 | [Claude Code + ComfyUI](https://www.youtube.com/watch?v=nSS_Wi7f2Ww) | 2026-04-13 / 18:50 | Cloud API·4-model 병렬·runner·stitched video | 공개 prompt 페이지 |
| 4 | [AI Long Form Videos with $0](https://www.youtube.com/watch?v=D-q5jGgo_7c) | 2025-11-18 / 26:17 | EC2+n8n 장편 영상 생성 | scripts+n8n workflow+server setup 문서 |
| 5 | [Sora 2 + n8n AI Agents](https://www.youtube.com/watch?v=Vm8QOo9MiC4) | 2025-10-22 / 28:34 | text/image-to-video·storyboard·polling·로그 | 공개 workflow repo 없음 |
| 6 | [Consistent Longform Films, Hourly](https://www.youtube.com/watch?v=dI9AhW0rrZs) | 2025-09-12 / 33:11 | Nano Banana+n8n, 음성→이미지→영상→결합 | template은 회원용 |
| 7 | [Consistent AI Characters — ComfyUI Masterclass](https://www.youtube.com/watch?v=PhiPASFYBmk) | 2025-10-07 / 24:23 | dataset·caption·LoRA·Qwen·Wan·4K | 무료 workflow, 고급 자료 일부 유료 |
| 8 | [n8n Connects to ComfyUI](https://www.youtube.com/watch?v=_t-32uJnE-U) | 2025-12-12 / 19:27 | Docker network·Comfy queue/API·output 전달 | 별도 공개 repo 없음 |
| 9 | [AI Videos FAST With Claude Code](https://www.youtube.com/watch?v=J6T8QHST2YE) | 2026-05-04 / 17:04 | Higgsfield MCP·custom skill·24 scenes·storyboard | 무료 prompts/custom skill 페이지 |
| 10 | [Higgsfield MCP + Claude Code AI Ad Agency](https://www.youtube.com/watch?v=1dga9Qxx_co) | 2026-05-01 / 17:56 | URL→브랜드 조사→정적 광고→Seedance→UGC | 별도 공개 repo 없음 |
| 11 | [ComfyUI With MCP](https://www.youtube.com/watch?v=Yk7y56Kk-LI) | 2026-03-29 / 13:14 | local Comfy MCP·LM Studio/Cursor·batch | `joenorton/comfyui-mcp-server` 공개 |
| 12 | [ComfyUI Course From Scratch](https://www.youtube.com/watch?v=HkoRkNLWQzY) | 2026-01-15 / 4:49:00 | graph·LoRA·ControlNet·GGUF·API node·오류 처리 | Easy Install repo·무료 workflow |

**우선 시청 순서:** Claude/편집은 `XeTAlZiIWHE`, API 자동화 기반은 `UIf-SlmMays`, Comfy agent workflow는 `nSS_Wi7f2Ww`가 가장 직접적이다.

## 3. 공개 구현체 판정

| 구현체 | 활용도 | 라이선스/상태 | 권장 사용 |
|---|---|---|---|
| [`mrdainami/kie-mcp`](https://github.com/mrdainami/kie-mcp) | 매우 높음 | MIT, 2026-08-20 갱신 | KIE connector를 그대로 참고하거나 vendoring 없이 외부 MCP로 사용. 다만 core job ledger는 별도 구현 |
| [`heygen-com/hyperframes`](https://github.com/heygen-com/hyperframes) | 매우 높음 | Apache-2.0, agent skill·CLI·결정론적 MP4 렌더 | MVP 편집/모션그래픽 renderer 1순위. Node 22+·FFmpeg 필요 |
| [`Comfy-Org/comfy-mcp`](https://github.com/Comfy-Org/comfy-mcp) | 높음 | beta, 40 tools, AGPL-3.0-or-later 또는 상용 | local/cloud ComfyUI 실험 connector. proprietary 서비스 포함 시 라이선스 검토 필요 |
| [`Comfy-Org/ComfyUI`](https://github.com/Comfy-Org/ComfyUI) | 높음 | GPL-3.0 | 통제가 필요한 로컬 VFX·ControlNet lane. 운영 복잡도와 GPU 비용을 감수할 때 사용 |
| [`artokun/comfyui-mcp`](https://github.com/artokun/comfyui-mcp) | 중간~높음 | MIT, 폭넓은 agent control plane | 공식 MCP보다 풍부하지만 third-party surface이므로 보안·업데이트 검증 필요 |
| [`hetpatel-11/Adobe_Premiere_Pro_MCP`](https://github.com/hetpatel-11/Adobe_Premiere_Pro_MCP) | 선택적 | MIT, 282 tools 주장 | 사람이 Premiere를 최종 NLE로 쓸 때 export bridge 후보. MVP core에는 넣지 않음 |
| [`modelcontextprotocol/python-sdk`](https://github.com/modelcontextprotocol/python-sdk) | 높음 | MIT | 얇은 MCP server 구현 기반 |
| [`n8n-io/n8n`](https://github.com/n8n-io/n8n) | 트리거/배포에 높음 | fair-code | 승인·스케줄·알림·배포 연결에 사용. 생성 job의 source of truth로는 사용하지 않음 |

### 공식 provider API 비교 — 2026-08-22

| Provider | 비동기·취소·webhook | 모델·가격 | 결과 보존·운영 | 판정 |
|---|---|---|---|---|
| **KIE.ai** | `/jobs/createTask`→`recordInfo`; callback 선택; product별 legacy endpoint 병존 | 잔액 API는 있음. 전 모델 실시간 pricing API는 공식 근거 미확인 | Runway proxy 결과는 14일 내 다운로드. 공식 SDK·SLA·idempotency 보장은 미확인 | 빠른 multi-model MVP에는 좋지만 락인·계약 불균일이 큼 |
| **fal.ai** | queue submit/status/result/cancel; webhook Ed25519·최대 31회 retry | 공식 model search와 `GET /v1/models/pricing`; usage·analytics | queue 429/5xx 등에 최대 10회 retry; 일부 fallback | **가격·webhook·queue가 가장 운영 친화적인 직접 API 후보** |
| **Replicate** | async prediction, cancel deadline, HMAC webhook | model list/search/version; 가격 단위는 모델별 | input/output/log 기본 1시간 후 삭제 → 즉시 저장 필수 | 모델 폭이 넓고 Cog 탈출구가 있으나 schema·retention 관리 필요 |
| **Runway** | task polling·DELETE cancel; 공식 완료 webhook은 확인되지 않음 | 정적 credit 가격표; third-party 모델도 Runway ID로 래핑 | 임시 URL 즉시 저장; version header 필수 | 품질 실험에는 유용하나 가격·모델 ID 락인이 높음 |
| **Google Veo** | long-running operation polling; 공식 webhook 제공 | `models.list`; preview별 초당 정적 가격 | Gemini Developer API와 Vertex adapter를 분리해야 함 | 직접 Veo 품질 비교용. preview/deprecation 변화 감시 필요 |
| **OpenAI Videos** | create/get/content/delete; completed/failed webhook; batch | Sora 2/Pro 초당 정적 가격; batch 할인 | batch 결과 최대 24시간 다운로드; 실제 인물 제한 | character/edit/extension을 쓸 때 강력하지만 Sora resource 락인 높음 |
| **ComfyUI** | `/prompt`, `/queue`, `/history`, `/view`, `/ws`, `/interrupt` | 설치 모델·`/object_info`가 catalog; per-call API 가격 없음 | 외부 webhook은 자체 worker가 발행. GPU·node 공급망 직접 운영 | 완전 자가호스팅·세밀한 VFX lane, 대신 운영 부담 최고 |

**사용자 환경 반영 후 선택 권고(2026-08-22 갱신):** 워크스테이션에 MiniMax H3가 있고 이미지는 GPT Image API로 생성하므로, production의 1차 경로는 **GPT Image reference → 로컬 H3 영상+동시 음성 생성**이다. ComfyUI는 H3를 그 위에서 실행 중일 때의 runtime/UI이며 독립 provider가 아니다. fal·KIE는 로컬 GPU burst, 장애 fallback, H3가 약한 장면의 타 모델 비교에만 추가한다. 공식 공개 H3-Base는 로컬 768p이며 H3-Context-IR과 H3-Regenerate-2K는 호스팅 API 모듈이므로, 로컬-only와 공식 2K hybrid를 별도 benchmark lane으로 취급한다. [MiniMax H3 공식 저장소](https://github.com/MiniMax-AI/MiniMax-H3) · [공식 모델 카드](https://huggingface.co/MiniMaxAI/MiniMax-H3) · [ComfyUI 공식 H3 튜토리얼](https://docs.comfy.org/tutorials/video/minimax/minimax-h3)

## 4. MCP vs CLI vs workflow engine

| 방식 | 강점 | 약점 | 적합한 역할 |
|---|---|---|---|
| MCP만 | Claude/Codex에서 자연어로 바로 사용, 데모가 빠름 | 장시간 job 복구·동시성·과금·회귀 테스트가 약함 | 대화형 제어면 |
| CLI만 | 테스트·CI·script·재현성이 좋음 | 비개발자 UX와 승인 대화가 약함 | 디버깅·배치·CI 표면 |
| n8n만 | 시각적, SaaS 연결과 알림이 빠름 | graph drift, 고정 wait, 비밀·대형 binary·복잡 상태 처리 취약 | trigger·approval·distribution |
| 코드 기반 durable pipeline | 상태·idempotency·재시도·평가를 가장 정확히 관리 | 초기 구현량이 큼 | 실행 본체 |

### 권장 구조

```text
Telegram / Claude / Codex / n8n
              │
        MCP + CLI adapters
              │
       Python pipeline core
  ┌───────────┼──────────────┐
  │           │              │
Shot plan   Job ledger     Budget/policy
  │         (SQLite)       human gates
  │           │              │
Provider adapters ── KIE / ComfyUI / direct APIs
  │
Asset store + immutable manifests
  │
HyperFrames / FFmpeg deterministic render
  │
Mechanical QA → visual QA → approval → distribution
```

**추천 기본안은 Python-first core + Node renderer다.** Python은 비동기 job, 평가·CV/ASR, FFmpeg orchestration에 유리하고, HyperFrames는 Node subprocess/worker로 분리한다. MCP는 Python SDK로 core 함수를 감싸고 CLI는 Typer 계열로 같은 함수를 호출한다. TypeScript-only도 가능하지만 영상 QA 생태계 때문에 Python을 다시 붙일 가능성이 높다.

## 5. 구현 가능한 구체 설계

### 5.1 최소 도메인 모델

```text
Project
 └─ Brief
     └─ ShotPlan[]
         ├─ ReferenceAsset[]
         ├─ GenerationAttempt[]
         │   ├─ provider/model/schema_version
         │   ├─ request_hash/task_id/status
         │   ├─ submitted_at/completed_at/cost
         │   └─ output_asset_ids/error/retry_of
         ├─ SelectionDecision
         └─ ShotQA
RenderManifest
ApprovalEvent
DistributionPacket
```

필수 상태는 `planned → submitted → running → succeeded|failed|cancelled → downloaded → qa_pass|qa_fail → selected|rejected`다. `request_hash`에 provider/model/normalized payload/reference hashes를 묶어 동일 요청의 중복 과금을 막는다.

### 5.2 provider adapter 계약

```python
class VideoProvider:
    def capabilities(self) -> list[ModelCapability]: ...
    def estimate(self, request: GenerateRequest) -> CostEstimate: ...
    def submit(self, request: GenerateRequest, idempotency_key: str) -> JobHandle: ...
    def get(self, handle: JobHandle) -> JobStatus: ...
    def cancel(self, handle: JobHandle) -> None: ...
    def download(self, handle: JobHandle, dest: Path) -> list[Asset]: ...
```

- KIE v1 adapter: Market common task API 우선, 모델별 envelope는 docs snapshot과 schema version으로 보존.
- fal v1 adapter: queue request ID, signed webhook, pricing receipt를 보존한다.
- Comfy adapter: workflow JSON hash, installed node/model inventory, prompt ID를 보존.
- Runway·Google·OpenAI는 benchmark 요구가 생길 때 추가한다. 초기부터 모든 모델을 개별 하드코딩하지 않는다.

추가 불변조건:

- webhook은 서명 검증 후 빠르게 `2xx`하고 내부 queue로 넘긴다.
- webhook 미도착·중복 전달을 전제로 reconciliation poller와 idempotent handler를 둔다.
- model ID, request schema hash, pricing snapshot, commercial-rights metadata를 분리한다.
- provider URL은 성공 즉시 자체 asset store로 복사한다. KIE 14일, Replicate 기본 1시간, OpenAI batch 24시간처럼 retention이 다르므로 provider URL을 최종 asset으로 취급하지 않는다.

### 5.3 CLI

```text
avp models sync --provider kie
avp shot submit SHOT-003 --provider kie --model bytedance/seedance-2
avp job watch JOB-...
avp job retry JOB-... --reason transient
avp pipeline run BRIEF-001 --until generation
avp render build PROJECT-001
avp qa run PROJECT-001
avp inspect PROJECT-001 --costs --failures
```

### 5.4 MCP

도구 수는 작게 유지한다.

```text
video_models_list
video_cost_estimate
video_shot_submit
video_job_status
video_job_cancel
video_pipeline_run
video_pipeline_status
video_qa_report
```

MCP 인자에 API key를 받지 않는다. credential은 환경변수·Keychain·secret manager에서 읽는다. `submit`은 예상 비용·샷 수를 반환하고 상한을 넘으면 사용자 승인을 요구한다.

2026-07-28 MCP에는 장시간 작업용 **Tasks 확장**(`tasks/get`, `tasks/update`, `tasks/cancel`)이 추가됐지만 core가 아닌 opt-in이며 host별 지원이 다르다. 따라서 Tasks를 지원하더라도 위 explicit job tools와 자체 DB를 source of truth로 유지한다. remote transport는 최신 Streamable HTTP 계약을 따르고, 초기 MVP의 Claude/Codex local 연동은 단순한 stdio로 시작한다.

### 5.5 비동기·오류 처리

- `taskId`는 submit 응답을 받는 즉시 transaction으로 저장한다.
- webhook을 우선하되 서명을 검증하고, 누락 대비 exponential polling을 둔다.
- `429/5xx/timeout`만 bounded retry; 잘못된 payload·moderation·잔액 부족은 retry하지 않는다.
- process 재시작 후 `submitted/running` job을 ledger에서 회수한다.
- 결과 URL은 만료되기 전에 content-addressed asset store로 복사하고 SHA-256을 기록한다.
- 실패는 shot 단위로 격리한다. 전체 project를 무조건 재실행하지 않는다.

### 5.6 영상·공개 MCP가 생략한 보안·테스트

현재 공개 README는 host allowlist, cross-origin redirect 시 credential 제거, docs source 제한, `KIE_WORKSPACE_DIR` 경계, symlink resolve, media-only upload와 위험한 destination 거부를 설명한다. 그러나 production 채택 전에는 다음을 source-level test로 다시 증명해야 한다.

- invalid/expired key, insufficient credits, invalid model/schema
- task `fail`, timeout, 429/5xx, `Retry-After`, malformed result JSON
- upload URL 만료, download 중단·부분 파일, MIME/magic-byte·크기·quota
- path traversal·symlink, redirect·SSRF·DNS rebinding
- process restart 후 polling resume와 duplicate submit·이중 과금 방지
- Claude Desktop·Claude Code·Codex 간 호환 회귀시험
- npm/`.mcpb` artifact checksum·provenance와 로그 secret redaction

실제 과금 smoke test는 기본 unit test와 분리하고 명시적 opt-in으로만 실행한다.

## 6. 성능·품질 점검

### 고정 benchmark pack

첫 비교는 실제 MVP shot 12개로 고정한다.

- 제품 외형/로고 보존 3개
- 인물·캐릭터 일관성 3개
- 카메라·동작 지시 3개
- 변형/VFX·복잡 상호작용 3개

provider마다 동일 prompt·reference·duration·aspect ratio를 사용하고 shot당 후보 3개를 만든다. 평가자는 provider 이름을 가린다.

### 지표

| 축 | 지표 |
|---|---|
| 품질 | first-pass usable rate, 최종 선택률, prompt 충실도, 제품/인물 identity, temporal consistency, 물리·손·텍스트 결함 |
| 운영 | 성공률, manual repair rate, retry rate, orphan job 0건, webhook/poll recovery |
| 속도 | submit→first result p50/p95, usable shot까지의 wall time, render time |
| 비용 | submit 비용, usable shot당 비용, 최종 30초당 비용, 실패·폐기 비용 비율 |
| 재현성 | manifest 완결률, request/result hash, 같은 deterministic render의 frame hash |
| 편집 QA | aspect/fps/duration, black/frozen frame, audio LUFS·true peak, caption WER·sync offset, OCR·safe-zone |

### 합격 게이트

- 12개 shot 모두 provenance·비용·상태 완결
- orphan/중복 과금 job 0
- 기계 QA 100% 통과
- provider별 최소 36 attempts에서 `usable-shot cost`와 `first-pass usable rate` 산출
- visual judge 2인의 blind agreement 기록
- 한 provider가 실패해도 동일 shot을 다른 adapter로 재개 가능
- MCP·CLI가 같은 core 결과와 동일 job ID를 가리킴

“가장 예쁜 한 샘플”이 아니라 **고정 shot pack에서 usable-shot당 비용과 복구 가능한 성공률**로 선택한다.

## 7. 단계별 빌드 큐

### Phase 0 — 0.5일: 계약 고정
- 기존 `pipeline-schema.md`를 최소 DB schema로 변환
- 12-shot benchmark pack과 평가 rubric 동결
- 비용 상한·승인 gate 결정

### Phase 1 — 2~3일: core + KIE/fal adapter
- SQLite job/asset ledger
- KIE submit/get/download/credits
- fal queue/webhook/pricing
- request hash와 중복 submit 방지
- fake provider·webhook replay 기반 unit test

### Phase 2 — 1일: CLI와 recovery
- `models/shot/job/pipeline/inspect` 명령
- process restart recovery
- 429/5xx·timeout·invalid payload failure tests

### Phase 3 — 1~2일: deterministic renderer
- HyperFrames를 기본으로 연결하고 단순 concat/audio normalization은 FFmpeg 사용
- scene manifest → preview → final render
- partial re-render 지원 여부 검증

### Phase 4 — 1~2일: QA harness
- ffprobe 기반 포맷 검사
- black/frozen frame·audio·caption 검사
- visual rubric와 blind review packet

### Phase 5 — 0.5~1일: 얇은 MCP
- 8개 이하 tool로 core wrapper
- 비용 확인과 승인 gate
- MCP와 CLI parity test

### Phase 6 — benchmark 후 선택
- KIE와 fal을 기본 비교하고, 필요 시 ComfyUI/Runway/Google/OpenAI를 같은 12-shot pack에 추가
- n8n은 승인 알림·스케줄·게시 trigger에만 추가

**실제 첫 usable MVP 예상: 6~9 개발일 + provider 생성 대기/시각 평가.** 완전 무인 게시나 다중 provider 자동 최적화는 첫 MVP 범위가 아니다.

## 8. 최종 추천

1. 공개 `kie-mcp`는 직접 재현 가능하고 그대로 설치해 실험해도 된다.
2. 그러나 제품 구현은 해당 repo를 fork해 비대하게 만들지 말고 **pipeline core를 별도 소유**한다.
3. 생성 provider의 첫 adapter는 KIE와 fal이다. 통제형 ComfyUI lane은 실제 VFX·자가호스팅 요구가 확인될 때 추가한다.
4. 최종 합성은 HyperFrames + FFmpeg로 결정론화한다.
5. MCP는 리모컨, CLI는 검증·운영 인터페이스, SQLite pipeline은 source of truth로 둔다.
6. 먼저 12-shot benchmark를 통과시킨 뒤 Higgsfield보다 낫다는 말을 한다. 현재 증거로는 “Higgsfield UI 없이 유사 생성 workflow를 만들 수 있다”까지가 안전하다.

## Source ledger

- [S1] [기준 영상 — How Claude Replaced Higgsfield](https://www.youtube.com/watch?v=83NI19L7fhQ), Calvin Hia, 2026-08-19, transcript close-read.
- [S2] [`mrdainami/kie-mcp`](https://github.com/mrdainami/kie-mcp), README/source tree/repository metadata 확인, 2026-08-22.
- [S3] [Claude Code + ComfyUI](https://www.youtube.com/watch?v=nSS_Wi7f2Ww), 2026-04-13, transcript close-read.
- [S4] [Local AI VFX pipeline](https://www.youtube.com/watch?v=_n0ir5V5tX4), 2026-03-30, transcript close-read.
- [S5] [Claude Code full video editing](https://www.youtube.com/watch?v=XeTAlZiIWHE), 2026-06-29, transcript close-read.
- [S6] [n8n + FFmpeg](https://www.youtube.com/watch?v=okesXuYa-UE), 2025-06-09, transcript close-read.
- [S7] [Faceless factory live build](https://www.youtube.com/watch?v=6bBWmnv8Q8o), 2026-02-01, transcript close-read.
- [S8] [100 long-form videos with n8n](https://www.youtube.com/watch?v=tboScAwJCAE), 2025-11-18, transcript close-read.
- [S9] [KIE official docs index](https://docs.kie.ai/llms.txt), model/task/upload/credits/webhook 목록 확인, 2026-08-22.
- [S10] [`heygen-com/hyperframes`](https://github.com/heygen-com/hyperframes), README/repository metadata 확인, 2026-08-22.
- [S11] [`Comfy-Org/comfy-mcp`](https://github.com/Comfy-Org/comfy-mcp), README/repository metadata 확인, 2026-08-22.
- [S12] [InfiniteTalk long-form workflow](https://www.youtube.com/watch?v=fYkLETrdtws), 2025-10-28, transcript close-read.
- [S13] [Higgsfield + Claude editing](https://www.youtube.com/watch?v=vI4RdXMSq8c), 2026-07-20, metadata·설명 확인.
- [S14] [n8n Zero to Hero Course](https://www.youtube.com/watch?v=UIf-SlmMays), 2025-12-11, metadata·설명·chapter 확인.
- [S15] [AI Long Form Videos with $0](https://www.youtube.com/watch?v=D-q5jGgo_7c), 2025-11-18, metadata·제공 문서 확인.
- [S16] [Sora 2 + n8n AI Agents](https://www.youtube.com/watch?v=Vm8QOo9MiC4), 2025-10-22, metadata·설명 확인.
- [S17] [Consistent Longform Films, Hourly](https://www.youtube.com/watch?v=dI9AhW0rrZs), 2025-09-12, metadata·설명 확인.
- [S18] [Consistent AI Characters — ComfyUI](https://www.youtube.com/watch?v=PhiPASFYBmk), 2025-10-07, metadata·workflow 링크 확인.
- [S19] [n8n Connects to ComfyUI](https://www.youtube.com/watch?v=_t-32uJnE-U), 2025-12-12, metadata·설명 확인.
- [S20] [AI Videos FAST With Claude Code](https://www.youtube.com/watch?v=J6T8QHST2YE), 2026-05-04, metadata·freebies 링크 확인.
- [S21] [Higgsfield MCP AI Ad Agency](https://www.youtube.com/watch?v=1dga9Qxx_co), 2026-05-01, metadata·설명 확인.
- [S22] [ComfyUI With MCP](https://www.youtube.com/watch?v=Yk7y56Kk-LI), 2026-03-29, metadata·repo 링크 확인.
- [S23] [ComfyUI Course From Scratch](https://www.youtube.com/watch?v=HkoRkNLWQzY), 2026-01-15, metadata·repo·resource 링크 확인.
- [S24] [MCP 2026-07-28 specification](https://modelcontextprotocol.io/specification/2026-07-28/index), transport·Tasks·SDK 확인.
- [S25] [KIE Market quickstart](https://docs.kie.ai/market/quickstart), unified jobs·credit·callback 확인.
- [S26] [fal queue·pricing·webhooks](https://fal.ai/docs/documentation/model-apis/inference/queue), 공식 pricing API·서명·retry 문서 확인.
- [S27] [Replicate prediction lifecycle](https://replicate.com/docs/topics/predictions/lifecycle.md), async·webhook·retention 확인.
- [S28] [Runway API context](https://docs.dev.runwayml.com/ai-context.md), tasks·models·pricing 문서 확인.
- [S29] [Google Veo API](https://ai.google.dev/gemini-api/docs/video), long-running operation·webhook·pricing 확인.
- [S30] [OpenAI video generation](https://developers.openai.com/api/docs/guides/video-generation.md), Videos resource·webhook·batch 확인.
- [S31] [ComfyUI server routes](https://docs.comfy.org/development/comfyui-server/comms_routes), queue·history·WebSocket·models 확인.

## Evidence boundary

- 영상의 품질 주장은 transcript와 제작자 시연을 분석한 것이며 독립 visual benchmark는 아직 아니다.
- GitHub star 수와 갱신일은 2026-08-22 조회값으로 변동 가능하다.
- provider 가격·모델 가용성은 변동이 빠르므로 build 시 live catalog/credits API로 다시 조회해야 한다.
- 현재 문서는 설계·구현 준비 완료 판정이지 실제 유료 모델 benchmark 완료 판정이 아니다.
