# hermess

[Hermes Agent](https://github.com/NousResearch/hermes-agent)를 reference architecture로
자체 멀티 에이전트 시스템을 설계하는 프로젝트.

문서를 그대로 믿지 않고 **실측(소스 확인 · 라이브 API 질의 · 실제 agent 구동)으로 검증한 뒤**
설계 결정을 내리는 것을 원칙으로 한다.

---

## 결론 요약

1. **오케스트레이터를 직접 만들지 않는다.** 만들려던 구조가 Hermes Kanban으로 이미 구현돼 있고,
   실행으로 동작을 확인했다. 우리가 작성할 것은 프로필 정의와 스킬뿐이다.
2. **기본 실행 모델은 Luna.** 초기의 "spark만 가능"은 권한이 아니라 quota 소진이었고
   회복 후 재측정 결과 **spark는 Luna보다 추론 토큰을 4배, Sol보다 8배 쓴다**(정답률 동일).
   spark는 quota 폴백으로 강등했다.
3. **모델 라우팅 사다리는 코드가 아니라 보드 컬럼이다.**
   `model_override` · `provider_override` · `reasoning_effort`가 태스크 행에 있다.

---

## 문서

| 문서 | 내용 |
|---|---|
| [`hermess-design-review.md`](hermess-design-review.md) | **실측 기록.** 초기 설계의 오류 검증, 반증된 결론, Kanban 실행 검증 |
| [`docs/adr/`](docs/adr/) | 설계 결정 4건 |
| [`hermess-arch.md`](hermess-arch.md) | 초기 조사 (Hermes 구조) — 일부 오류는 design-review에서 정정 |
| [`heremss-research.md`](heremss-research.md) | 초기 조사 (Grok Bot 대비) |

### ADR

| # | 결정 | 상태 |
|---|---|---|
| [001](docs/adr/ADR-001-kanban-adoption.md) | 오케스트레이션은 Hermes Kanban 채택 | Accepted |
| [002](docs/adr/ADR-002-coordination-boundaries.md) | Kanban / Bot / delegate_task 3계층 경계 | Accepted (실행 검증) |
| [003](docs/adr/ADR-003-model-routing.md) | quota-aware 라우팅을 보드 컬럼으로 표현 | Accepted |
| [004](docs/adr/ADR-004-external-integration.md) | 외부 연동은 CLI `--json` 경유 | Accepted (실측 후 반전) |

---

## 아키텍처

```
                        orchestrator
                  (kanban, memory, skills)
                   실행 툴 없음 = 일을 못 함
                             │
                      kanban_create
                             ▼
                    ┌────────────────┐
                    │   kanban.db    │  SQLite (WAL)
                    │  tasks/links/  │  모든 핸드오프가 행으로 남음
                    │ comments/events│
                    └────────┬───────┘
                             │ dispatcher (60s tick)
                    원자적 claim → spawn
          ┌──────────┬───────┴───────┬──────────┐
          ▼          ▼               ▼          ▼
      architect  backend-eng      reviewer   analyst
       (설계)      (구현)        (독립 검증)  (자료 정리)
```

**3계층 경계** — 셋은 경쟁이 아니라 층이 다르다.

```
Kanban            역할 경계를 넘고 · 재시작을 견디고 · 사람이 낄 수 있는 일
  └ Bot(Profile)     그 일을 맡는 이름 있는 영속 정체성
      └ delegate_task   워커가 자기 턴 안에서 쓰는 일회성 하청
```

판정 기준: *이 핸드오프가 단일 API 루프보다 오래 살아야 하고 남들에게 보여야 하는가?*
그렇다면 board, 아니면 delegate.

---

## 검증된 사실 (재현 가능)

| 항목 | 결과 |
|---|---|
| Hermes가 `gpt-5.3-codex-spark`로 구동 | ✅ |
| `delegate_task` 작동 (spark, `openai_runtime: auto`) | ✅ subagent → PONG |
| `memory` 영속 | ✅ `memories/MEMORY.md` |
| Kanban 의존성 해석 | ✅ link 시 `ready→todo`, 부모 done 시 `todo→ready` |
| Kanban 부모 결과 → 자식 컨텍스트 전달 | ✅ |
| 태스크 단위 모델 override | ✅ `set-model` |
| orchestrator 툴셋 박탈 강제 | ✅ 직접 실행 실패 → kanban 라우팅 → writer가 완수 |
| 교차 provider 위임 (anthropic ↔ openai-codex) | ✅ 자격증명 해석 확인 |
| **리뷰 되돌림 루프 (T3)** | ✅ 구현 → 반려 → 수정 → 통과, run 4건 이력 |
| **사람 개입 루프 (T4)** | ✅ block → comment → unblock → 답변 반영 |
| **effort 차등 (T1/T2)** | ⚠ spark `high→xhigh` **무효**(평균이 오히려 낮음). luna는 `max`까지 유효 |
| **모델 효율 (T2)** | spark 1211 / luna 295 / sol 155 / terra 154 토큰 — 동일 문제·동일 정답 |
| **Astra (AGENTIC 축)** | ✗ HTTP 400 — 이 계정 미가용. `--goal` 루프로 대체 |

### 뒤집힌 초기 결론

- ~~GPT 경로는 memory/delegation 불가~~ → `codex_app_server`에서만 불가. 기본 `auto`는 정상.
- ~~`max_concurrent_children` 기본 3~~ → **10**
- ~~API Server(REST)로 연동~~ → kanban 미노출. CLI `--json`으로 반전.

---

## 알려진 함정

**1. toolset 설정 키가 두 개이고 둘 다 필요하다**

```yaml
platform_toolsets:                    # 실제 툴 노출 제한
  cli: [kanban, memory, skills]
toolsets: [kanban, memory, skills]    # kanban check_fn이 읽는 키
```

`cli-config.yaml.example`은 최상위 `toolsets`를 *"deprecated and ignored"*라고 하지만,
`tools/kanban_tools.py:_profile_has_kanban_toolset()`이 실제로 이 키를 읽는다.
하나만 쓰면 제한이 안 걸리거나 kanban 툴이 안 뜬다.

**2. 실행 툴 없는 프로필에 `delegation`을 주지 말 것**

자식은 부모 툴셋의 교집합이라(`delegate_tool.py:1827`) 실행 툴 없는 부모의 자식도 실행할 수 없다.
막다른 길이 되어 실측에서 **56회 tool call · 3분 thrash 후 거짓 완료 보고**가 발생했다.

**3. `scratch` 워크스페이스는 완료 시 삭제된다**

산출물을 남기려면 `--workspace dir:<절대경로>` / `worktree:` 를 쓰거나
`kanban_complete(artifacts=[...])`로 명시 선언한다. `dir:` 보존은 실측 확인했다.

**5. 모델 가용성은 "OK" 출력으로 판단하지 말 것**

`-m astra` 같은 존재하지 않는 slug에도 grep이 "OK"를 잡아낸 적이 있다.
실제로는 HTTP 400이었다. **전체 출력 또는 `session_model_usage.model`로 확인한다.**

**6. 리뷰가 붙는 카드는 본문에 인수 기준을 반드시 넣을 것**

리뷰 run은 **구현자용으로 쓰인 같은 카드 본문을 상속**한다. 기준이 없으면
리뷰어는 결함을 정확히 보고도 통과시킨다(T3 실측). 판정할 대상이 없기 때문이다.

**4. Kanban v1 스펙 PDF는 "DESIGN ONLY"이고 구현과 다르다**

스펙 4테이블/14컬럼 → 실제 7테이블/37컬럼. **PDF는 설계 근거로만 쓰고 사실은 코드로 확인한다.**

---

## 남은 검증

- [ ] spark에서 `reasoning_effort`가 실제 차등 작동하는가
      (codex CLI가 무효값도 통과시킴 → 검증 부재. 미작동 시 라우팅 사다리 1~3단이 무의미)
- [ ] quota 회복(2026-09-07 11:41) 후 Luna/Sol 실호출
- [ ] reviewer를 포함한 3단 파이프라인 (구현 → 리뷰 → 재구현)
- [ ] ChatGPT 구독 인증의 동시 워커 rate limit 지점

---

## 재현

```bash
git clone https://github.com/NousResearch/hermes-agent.git   # 참조용 (이 리포에 미포함)
cd hermes-agent && uv sync --frozen

export HERMES_HOME=~/.hermes-poc CODEX_HOME=~/.codex
uv run python -m hermes_cli.main kanban init
uv run python -m hermes_cli.main kanban create "..." --assignee writer
uv run python -m hermes_cli.main kanban dispatch
```

`hermes-agent/`는 upstream(MIT) 클론이므로 이 리포에 포함하지 않는다.
