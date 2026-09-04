# ADR-004 — 외부 서비스(Spring Boot) 연동은 API Server를 경유한다

- 상태 **Accepted (2026-09-04 개정 — 미확인 항목 1 해소로 결정 반전)**
- 날짜 2026-09-04
- 관련 [ADR-001](ADR-001-kanban-adoption.md)

## 맥락

`hermess-arch.md`는 다음 스택을 전제하고, 연동 방식으로 Python import를 제시했다.

```
React → Spring Boot → AI Middleware → Hermes
```
```python
from run_agent import AIAgent
agent = AIAgent(...)
```

이건 현재 최선이 아니다(설계 리뷰 F-5). Python import는 **같은 프로세스에 Hermes를 박아넣는**
방식이라 JVM 스택과 언어·수명주기가 어긋난다.

## 검토한 선택지

| | 방식 | 평가 |
|---|---|---|
| A | `kanban.db` 직접 읽기/쓰기 | 스키마 결합. upstream 마이그레이션 때 깨짐 |
| B | **`hermes kanban …` CLI shell-out** | `--json` 구조화 출력 확인됨. 프로세스 기동 비용 |
| C | ~~API Server (REST)~~ | 실재하나 **kanban 미노출** (라우트 43개 전수 확인) |
| D | Python import | 언어 불일치. 별도 Python 사이드카 필요 |

## 결정

> **개정 이력.** 초안은 C(API Server)를 1차로 삼았다. 그러나 아래 실측으로
> **API Server가 kanban을 전혀 노출하지 않음**이 확인되어 결정을 뒤집는다.

**실측 (2026-09-04)** — `gateway/platforms/api_server*.py`의 전체 라우트 43개:

```
/health · /health/detailed · /v1/health · /v1/capabilities
/v1/models · /api/model/options · /v1/skills · /v1/toolsets
/api/sessions[/{id}[/messages|fork|chat|chat/stream|model]]
/v1/chat/completions · /v1/responses[/{id}]
/v1/runs[/{id}[/events|steer|stop|approval]]
/api/jobs[/{id}[/pause|resume|run]] · /api/cron/fire
/v1/artifacts/upload · /v1/artifacts/download/{id}
/v1/browser-control/{register,ws} · /v1/room-members/...
/approval · /stop · /p/{profile}{path} · /api/platforms/{platform}/events
```

**kanban 엔드포인트는 하나도 없다.** 보드 조작 표면이 REST에 존재하지 않는다.

**따라서 B(CLI `--json`)를 1차 경로로 채택한다.**

```
React → Spring Boot ─┬─[프로세스 호출]─▶ hermes kanban … --json   ← 보드 조작 (1차)
                     └─[REST]─────────▶ /v1/runs                 ← 단발 에이전트 호출
                                              │
                                         kanban.db (SSOT)
```

`--json`이 구조화 출력을 준다는 것은 실행으로 확인했다(태스크 전 필드 JSON 배열).
`/v1/runs`는 보드를 거치지 않는 **단발 에이전트 호출**에 쓴다 —
`events` / `steer` / `stop` / `approval` 서브리소스가 있어 장기 실행 제어가 된다.

**A(DB 직접 접근)는 읽기 전용 조회에 한해서만 허용**하고, 쓰기는 금지한다.
스키마가 스펙 4테이블/14컬럼에서 실제 7테이블/37컬럼으로 이미 커졌다 —
결합하면 업그레이드마다 깨진다.

## 인터페이스 계약

Spring Boot 쪽이 의존할 표면을 좁게 고정한다.

| 목적 | 표면 |
|---|---|
| 작업 투입 | 태스크 생성 (assignee · workspace · model/provider override) |
| 상태 조회 | 태스크 status / result / run 이력 |
| 사람 개입 | comment · unblock |
| 산출물 회수 | `kanban_complete(artifacts=[...])` 로 선언된 첨부 |

**중요**: `scratch` 워크스페이스는 **완료 시 삭제된다.** 산출물을 남기려면
`--workspace dir:<절대경로>` 또는 `worktree:`를 쓰거나, `artifacts`로 명시 선언해야 한다.
Spring Boot가 파일을 회수하는 경로는 이 둘 중 하나로 고정한다.

## 결과

- **얻는 것**: 언어·프로세스 경계가 깨끗하다. Hermes 업그레이드가 Spring Boot를 안 건드린다.
- **포기하는 것**: in-process 호출 대비 네트워크 왕복 추가. 이 워크로드(초~분 단위)에서 무시 가능.
- **감수**: 디스패처 tick 기본 60초 → 태스크 투입~워커 기동 지연이 최대 60초.
  동기 응답이 필요한 UX라면 폴링/웹소켓으로 감싸야 한다.

## 미검증 — 구현 전 확인할 것

1. ~~API Server가 kanban을 노출하는가~~ → **해소. 노출하지 않음.** 결정 반전 완료.
2. `/v1/runs`의 인증 방식과 멀티 프로필 라우팅(`/p/{profile}{path}` 프리픽스와의 관계).
3. `kanban.db` 동시 접근 시 WAL 경합 (Spring Boot 읽기 + 디스패처 쓰기 + 워커 N개).
4. CLI shell-out의 프로세스 기동 지연 측정 — 요청당 물면 안 되므로 **비동기 큐잉 전제**.

## 재검토 트리거

- upstream이 kanban REST 엔드포인트를 추가할 때 → C로 복귀 검토
- 분산 배포가 필요해질 때 (Kanban은 single-host 설계 — ADR-001 참조)
- CLI 기동 지연이 병목이 될 때 → 상주 데몬(`hermes kanban daemon`) 경유 검토
