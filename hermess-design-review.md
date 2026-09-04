# Hermes Agent 설계 검증 및 재설계 Plan (실측판)

작성 2026-09-04 · 검증 방식 **소스 실측 + 라이브 API 실측 + 실제 agent 실행**
대상 `hermess-arch.md`, `heremss-research.md`, `~/.claude/skills/model-routing/SKILL.md`

> 1차 문서 리뷰(웹 문서 기준)의 결론 중 **3건이 실측으로 뒤집혔다.** 아래는 실측 결과 기준이다.

---

## 0. 실측 환경

```
hermes-agent   git 63279301 (2026-09-03) · MIT · uv sync 성공 · Python 3.11.16
codex-cli      0.152.1 · auth_mode=chatgpt · plan=prolite
설치 위치       ./hermes-agent/   (POC 상태: ~/.hermes-poc/)
```

실제로 Hermes agent를 **spark로 3회 구동**해 delegation·memory까지 확인했다.

---

## 1. 실측으로 뒤집힌 결론

| # | 1차 리뷰 주장 | 실측 결과 |
|---|---|---|
| F-1 | GPT 경로는 memory·delegation **불가** (Critical) | **부분 오류.** `codex_app_server`에서만 불가. 기본 `auto`에서는 **전부 작동** — 실행으로 확인 |
| F-3a | `max_concurrent_children` 기본 3 | **10** (`_get_max_concurrent_children()` 실행값) |
| — | "GPT는 spark만 사용 가능" (이용자 전제) | **원인이 다름.** 권한 아님, **quota 소진**. 백엔드는 Luna/Sol/Terra를 정상 반환 |

---

## 2. 핵심 실측 결과

### 2.1 "GPT = spark만" 의 진짜 원인은 quota 소진이다 (제약에 만료일이 있다)

ChatGPT Codex 백엔드에 직접 질의한 결과:

```
plan = prolite

slug                     supported_in_api   ctx
gpt-5.6-sol              True               272000
gpt-5.6-terra            True               272000
gpt-5.6-luna             True               272000
gpt-5.5                  True               272000
gpt-5.4                  True               272000
gpt-5.4-mini             True               272000
gpt-5.3-codex-spark      False              128000
```

**Luna/Sol/Terra는 이 계정에 열려 있다.** 그런데 실제 호출하면:

```
gpt-5.3-codex-spark  => OK (16,305 tokens)
gpt-5.6-luna         => ERROR: You've hit your usage limit.
                        try again at Sep 7th, 2026 11:41 AM
```

즉 **spark만 별도 quota 버킷에 남아 있어서 혼자 살아있는 상태**다.
웹 리서치로 이것이 공식 동작임을 확인했다 — spark는 저지연 전용 하드웨어에서 돌기 때문에
**별도 usage limit**을 쓴다. (관련 이슈: 메인 quota 소진이 spark를 막는 버그, spark가 메인
quota를 깎는 버그가 openai/codex에 보고돼 있음 — 우리는 전자의 반대 상황.)

또한 최초 테스트에서 전 모델이 실패한 것처럼 보인 `rmcp ... AuthRequired` 에러는
**모델과 무관한 GitHub Copilot MCP 서버 인증 누락**이었다. 이걸 모델 실패로 오독하면 안 된다.

> **설계 귀결**: 이 제약은 **영구가 아니라 2026-09-07 11:41 만료**다.
> 따라서 아키텍처를 spark 단일 모델에 하드코딩하면 안 된다.
> "지금은 spark로 폴백, quota 회복 후 Luna/Sol 승격"이 되는 **런타임 라우팅**으로 짜야 한다.

부가 발견: Hermes 자체 discovery는 `-900k` 컨텍스트 변종까지 노출한다
(`gpt-5.6-sol-900k` 등, 실측 911K). 두 원본 문서 모두 모르는 기능이다.
단 **spark에는 900k 변종이 없다 (128K 고정)** — 컨텍스트 예산 설계 시 중요.

### 2.2 F-1 정정 — GPT worker도 memory·delegation을 가질 수 있다

런타임이 **두 개**이고, 이 차이가 설계를 가른다.

| `model.openai_runtime` | 루프 주인 | api_mode | delegate_task / memory / session_search / todo |
|---|---|---|---|
| `auto` (기본) | **Hermes** | `codex_responses` | **전부 작동** |
| `codex_app_server` | Codex | — | **불가** (stateless MCP callback이 mid-loop 상태를 못 다룸) |

허용값은 소스에서 확정: `VALID_RUNTIMES = ("auto", "codex_app_server")`.

**실행으로 확인 (spark, `openai_runtime: auto`)**

```
$ cli.py -q "delegate_task로 subagent 하나 띄워 PONG 받아와" --toolsets delegation
  ┊ 🔀 delegate  1x: ...
  → The subagent returned: PONG          ✅ delegation 작동

$ cli.py -q "memory 툴로 'hermess-poc-marker-4471' 저장"
  ┊ 🧠 memory    +memory: "hermess-poc-marker-4471"
$ cat ~/.hermes-poc/memories/MEMORY.md
  hermess-poc-marker-4471                 ✅ 디스크 영속 확인
```

또한 `codex_app_server`를 켜더라도 **memory가 완전히 죽지는 않는다** —
self-improvement 리뷰 fork를 Hermes가 자동으로 `codex_responses`로 **강등**시켜
`memory` / `skill_manage`를 호출하게 한다(문서 286행). 다만 모델이 턴 중에 직접
memory를 부르지는 못한다.

> **설계 귀결**: `codex_app_server`를 켜지 마라.
> 기본 `auto`로 두면 GPT 노드도 1급 시민이 된다.
> 1차 리뷰의 "Codex는 기억 없는 순수 실행 노드" 제약은 **철회**한다.

### 2.3 교차 provider 라우팅은 가능하다 (config 주석이 틀렸다)

`cli-config.yaml.example`은 이렇게 적고 있다.

```yaml
  # provider: "openrouter"
  #   Supported: openrouter, nous, zai, kimi-coding, minimax
```

이 목록은 **불완전하다.** 코드는 하드코딩 목록이 아니라 `resolve_runtime_provider()`로
위임한다. 실제 해석 결과:

```
openai-codex  gpt-5.3-codex-spark    -> OK  api_mode=codex_responses   key=Y
openai-codex  gpt-5.6-luna           -> OK  api_mode=codex_responses   key=Y
anthropic     claude-opus-4-...      -> OK  api_mode=anthropic_messages key=Y
openrouter    z-ai/glm-5.2           -> ValueError: no API key
google        gemini-3-flash         -> ValueError: no credentials
```

**Claude ↔ GPT 교차 위임이 자격증명까지 완비된 상태다.** 이게 라우팅 설계의 토대다.
반면 openrouter·google은 키가 없어 지금은 못 쓴다(필요하면 발급).

### 2.4 F-3 정정 — 계층 제약은 맞지만 공식 우회로가 있다

런타임 실측값:

```
MAX_DEPTH 상수          = 1
max_spawn_depth         = 1     (기본 = 평면)
max_concurrent_children = 10    (문서의 3은 오래된 값)
orchestrator_enabled    = True
```

`role="orchestrator"`가 **1급 기능**으로 존재한다. `max_spawn_depth >= 2`이면
중간 에이전트가 자기 워커를 스폰할 수 있고, `orchestrator_enabled`가 킬스위치다.
상한은 없고(`floor 1, no ceiling`) 계층마다 비용이 곱해진다.

또한 배치가 동시성 상한을 넘으면 — 1차 리뷰가 인용한 "에러 반환"이 아니라
`run_agent.py:5512`가 **초과분을 잘라낸다**(`Truncate excess delegate_task calls`).

> **설계 귀결**: 4단 계층은 "불가능"이 아니라 **명시적 opt-in**이다.
> 다만 기본 평면 구조를 권장하는 이유(비용 곱셈)는 유효하므로,
> 2단으로 시작하고 필요할 때 orchestrator role을 붙인다.

---

## 2.5 Kanban 실행 검증 (2026-09-04)

`docs/hermes-kanban-v1-spec.pdf` 32쪽 정독 + **실제 파이프라인 구동**을 마쳤다.

### 실행 결과 — 전 항목 통과

프로필 3개(`default/researcher/writer`), spark 워커 2개, 실제 OS 프로세스 spawn:

```
t_dab22a46 (researcher) ──link──▶ t_45476e17 (writer)

link 직후        T2: ready → todo                        ✅ 의존성 해석
dispatch         Spawned: 1 (pid 43828)                  ✅ 원자적 claim + spawn
T1 완료          Result: red / green / blue
자동 승격        T2: todo → ready                        ✅ 부모 done 캐스케이드
set-model pin    openai-codex:gpt-5.3-codex-spark        ✅ 태스크 단위 라우팅
dispatch → T2    Result: red, green, blue                ✅ 부모 결과가 자식 컨텍스트로 전달
```

이벤트가 SQLite에 전부 남는다 — `created / linked / promoted / claimed / spawned /
heartbeat / completed`, run별 소요시간 포함. 컨텍스트 압축으로 소실되지 않는다.

### 스펙 대비 드리프트 — PDF를 사실 근거로 쓰면 안 된다

PDF는 2026-04-25 **"DESIGN ONLY. No implementation accompanies this document."**
그런데 이미 구현됐고, 스펙보다 훨씬 커졌다.

| | v1 스펙 | 실제 (실측) |
|---|---|---|
| 테이블 | 4개 | **7개** (`task_runs`, `task_attachments`, `kanban_notify_subs` 추가) |
| `tasks` 컬럼 | 14개 | **37개** |
| 노출 방식 | "CLI + skill 권장, toolset 아님"(§16.3 Open Q1) | **toolset으로 노출** — 권고가 뒤집힘 |
| CLI verb | 13개 | **40개+** (`swarm` `specify` `decompose` `daemon` `runs` `request-review` `boards` `gc` `repair` …) |

→ **PDF는 설계 근거(왜 이렇게 만들었나)로만 쓰고, 사실 관계는 코드로 확인한다.**

### 설계에 직결되는 발견 4가지

**K-1. 라우팅 사다리가 이미 보드 컬럼이다.**
`tasks`에 `model_override` · `provider_override` · **`reasoning_effort`**가 나란히 있다.
§4.1의 승격 사다리를 **태스크 행 단위로** 표현할 수 있다. 별도 라우터를 만들 필요가 없다.
CLI도 `--model` / `--provider` / `set-model`로 노출돼 있다.

**K-2. F-2(Bot vs Delegation 경계)가 여기서 풀린다.**
스펙 §6이 인용한 사용자 불만이 우리 상황과 동일하다 —
*"Researcher/Writer/QA로 프로필을 나눠도 orchestrator가 라우팅 대신 자기가 일을 해버린다."*
해법이 커널 기능이 아니라 **프로필 설정**이다: orchestrator에서
`terminal/file/web/browser/code`를 끄고 `[kanban, gateway, memory]`만 남기면
**구현을 물리적으로 못 하게** 된다. 3계층이 확정된다:

```
Kanban          역할 경계를 넘고 · 재시작을 견디고 · 사람이 낄 수 있는 일
  └ Bot(Profile)   그 일을 맡는 이름 있는 영속 정체성
      └ delegate_task   워커가 자기 턴 안에서 쓰는 일회성 하청
```
판정 기준(스펙 §10): *"이 핸드오프가 단일 API 루프보다 오래 살아야 하고
남들에게 보여야 하는가? 그렇다면 board, 아니면 delegate."*

**K-3. 회복 기능이 요구사항을 이미 덮는다.**
`max_retries` 서킷 브레이커, `consecutive_failures`, `worker_pid` 기반 크래시 회수,
`last_heartbeat_at`, stale-claim 회수, `--goal` 판정 루프, `task_runs` 재시도 이력.

**K-4. 명시적 스코프 밖 — 직접 만들어야 하는 것.**
스펙 §14가 커널 밖으로 밀어낸 것: smart routing / auto-assignment, 예산 제한,
승인 게이트, 대시보드. 전부 "user-space 프로필·플러그인으로 하라".
그리고 **single-host 설계**(trusted-local-user 위협 모델) — 분산이 필요하면 여기서 갈린다.

### D1 판단

**Kanban 채택. 오케스트레이터를 직접 만들지 않는다.**
`hermess-arch.md`가 그린 구조가 오늘 실행으로 동작하는 것을 확인했고,
추가로 만들 것은 **프로필 정의 + 스킬**뿐이다 — 커널 코드는 필요 없다.
근거와 대안은 `docs/adr/` 참조.


---

## 3. 여전히 유효한 지적 (1차 리뷰에서 변경 없음)

- **F-2 [C] Bot Mode ≠ Delegation.** Bot = 영속 Profile(`~/.hermes/profiles/<name>/`),
  `message_agent`로 통신. Delegation = 1회성 자식, 컨텍스트 격리, **최종 요약만** 반환.
  `heremss-research.md`가 둘을 "Bot Mode + subagent 병렬 실행"으로 묶은 건 오류.
- **F-5 [H] Spring Boot 연동은 Python import가 아니라 API Server(REST)**가 정석.
- **F-6 [M] 코드베이스 트리 부정확.** 실제 루트 확인: `cli.py`, `model_tools.py`,
  `hermes_state.py`(+`_schema/_search/_registry/...` 분할), `batch_runner.py`,
  `toolsets.py`, `trajectory_compressor.py`, `acp_adapter/`, `providers/`, `plugins/`,
  `cron/`, `native/`, `web/`, `evals/`. 엔트리포인트는 CLI / Gateway / **ACP** 3개.
- **F-8 [M] Learning Loop의 실제 이름은 Curator.** 두 문서 모두 언급 없음.
- **F-9 [M] 누락 서브시스템**: Kanban Multi-Agent(+worker lanes), Checkpoints & Rollback,
  Tool Search, Hooks, Loops, Persistent Goals, Fallback Providers, Credential Pools,
  Egress proxy, Trajectory Format, Mixture of Agents.
  → 리포지토리에 `docs/kanban/`, `docs/hermes-kanban-v1-spec.pdf`가 실재한다.
- **F-10 [ok] 검증 통과**: Skill vs Tool 구분, progressive disclosure,
  MCP include/exclude, Gateway–Core 분리, Grok Bot 대비.

---

## 4. Model Routing 재설계 (실측 반영)

### 4.1 전제 수정

1차 리뷰는 "모델 축이 사라졌다"고 했으나, 실제로는 **모델 축이 살아 있고 지금 일시적으로
막혀 있을 뿐**이다. 따라서 사다리를 지우는 게 아니라 **quota-aware 폴백**을 넣는다.

```
정상시(9/7 이후)   spark/med → luna/high → sol/high → sol/xhigh → Opus 교차 → Fable
현재(quota 소진)   spark/med → spark/high → spark/xhigh → ★Opus/high 교차 → Fable/high
```

`Luna/Sol` 이름은 skill이 지어낸 게 아니다 — `hermes_cli/codex_models.py`의
`DEFAULT_CODEX_MODELS`에 `gpt-5.6-sol / terra / luna`가 그대로 있다.
**skill의 표는 틀리지 않았고, 지금 quota 때문에 실행 불가일 뿐이다.**

### 4.2 실행 가능한 config

```yaml
# Coordinator (판단 소유)
model:
  provider: anthropic
  default: claude-opus-4-...
  openai_runtime: auto          # ← codex_app_server 금지 (2.2)

# Worker 위임 — 교차 provider 확인됨 (2.3)
delegation:
  provider: openai-codex
  model: gpt-5.3-codex-spark    # quota 회복 후 gpt-5.6-luna
  max_concurrent_children: 3    # 기본 10은 이 용도엔 과함
  max_spawn_depth: 1            # orchestrator 필요해지면 2

memory:
  memory_enabled: true
```

### 4.3 미검증으로 남은 항목

- spark에서 `model_reasoning_effort` 차등 작동 여부
  (codex CLI가 `bogus` 같은 무효값도 에러 없이 통과 → CLI 검증 없음. 별도 측정 필요)
- quota 회복 후 Luna/Sol 실호출 (2026-09-07 이후)
- `codex_app_server`에서 delegate_task 소멸 재현 — 리포 문서가 4곳에서 명시하고
  아키텍처적 근거도 명확하나, 이걸 켜면 `~/.codex/config.toml`에 managed 블록을 쓰므로
  **이용자 실제 Codex 설정을 건드리게 되어 보류**했다. 격리된 `CODEX_HOME`으로 재현 가능.

---

## 5. 수정된 Plan

**Phase 0 (완료)** — 실측. 위 결과가 산출물. `./hermes-agent/`, `~/.hermes-poc/` 존재.

**Phase 1 (완료)** — PDF 정독 + 실행 검증(§2.5) → ADR 4건 작성 → `docs/adr/`.

**Phase 2 — 경계 확정**
Bot(Profile) 경계 vs Delegation 경계(F-2) · 계층 깊이와 동시성 예산 ·
quota-aware 라우팅 테이블(4.1) · 권한 6축(Read/Write/Execute/Network/Secrets/Destructive).
배치: **Opus / high**

**Phase 3 — PoC 확장**
현재 POC는 `spark 부모 → spark 자식`까지 왔다. 다음은 **`Claude 부모 → spark 자식 → Opus 독립검증`**
수직 슬라이스. 2.3에서 자격증명이 확인됐으므로 바로 가능. 배치: **spark/medium → Opus/high**

**Phase 4 — 통합**
API Server(REST) 경유 Spring Boot 연동(F-5) · Checkpoints/Rollback · Curator 루프 · Egress.

---

## 6. 요약

1. **이용자 전제는 맞았지만 이유가 달랐다.** spark 단독 가용은 권한이 아니라 **quota 소진**이며
   **2026-09-07 11:41에 만료**된다. 설계를 spark에 고정하면 안 된다.
2. **1차 리뷰의 Critical F-1은 과했다.** `openai_runtime: auto`(기본)에서 GPT 노드는
   delegation·memory를 정상 사용한다 — 실행으로 확인. `codex_app_server`만 피하면 된다.
3. **Claude ↔ GPT 교차 위임이 자격증명까지 준비돼 있다.** 라우팅 설계의 토대가 확보됐다.
4. **남은 Critical은 F-2 하나** — Bot과 Delegation의 경계.
5. **Kanban 채택 결정 완료(§2.5).** 실행 검증 통과. 커널 수정 없이 프로필+스킬만 작성한다.
6. **F-2도 해소.** Kanban / Bot / delegate_task 3계층으로 경계가 확정됐다(K-2).
