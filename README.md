# hermess

[Hermes Agent](https://github.com/NousResearch/hermes-agent)를 reference architecture로
자체 멀티 에이전트 시스템을 구성한 프로젝트.

문서를 그대로 믿지 않고 **실측(소스 확인 · 라이브 API 질의 · 실제 agent 구동)으로 검증한 뒤**
설계 결정을 내리는 것을 원칙으로 한다. 실제로 초기 결론 중 **5건이 실측으로 뒤집혔다.**

---

## 결론 요약

1. **오케스트레이터를 직접 만들지 않는다.** 만들려던 구조가 Hermes Kanban으로 이미 구현돼 있다.
   우리가 작성한 것은 **프로필 7개와 부트스트랩 스크립트뿐**이고 커널 코드는 0줄이다.
2. **기본 실행 모델은 Luna.** spark는 동일 문제·동일 정답률에서 Sol의 8배, Luna의 4배 토큰을 쓴다.
3. **effort 사다리의 유효 구간은 `low → high` 하나다.** `max`/`xhigh`는 이득이 없다.
4. **`low`는 조용히 틀린다** — 정답률 40%인데 오답이 "거의 맞는 값"이라 눈으로 못 거른다.

---

## 빠른 시작

```bash
# 1. upstream 클론 (이 리포에 미포함 — 438M)
git clone https://github.com/NousResearch/hermes-agent.git
cd hermes-agent && uv sync --frozen

# 2. Codex 자격증명 임포트 (ChatGPT 구독 인증 재사용)
export HERMES_HOME=~/.hermes-poc CODEX_HOME=~/.codex
uv run python -c "
from hermes_cli.auth import _import_codex_cli_tokens, _save_codex_tokens, \
    _update_config_for_provider, DEFAULT_CODEX_BASE_URL
t=_import_codex_cli_tokens(); _save_codex_tokens(t)
print(_update_config_for_provider('openai-codex', DEFAULT_CODEX_BASE_URL))"

# 3. 프로필 로스터 설치 + 보드 초기화
HERMES_HOME=~/.hermes-poc ../profiles/bootstrap.sh

# 4. 검증 — orchestrator에 kanban_* 만 있고 terminal/file 이 없어야 정상
cd .. && ./hermess -p orchestrator chat -q "List the exact names of every tool you have."
```

이후 모든 실행은 리포 루트의 `./hermess` 래퍼를 쓴다 (아래 **실행 방법**).

## 실행 방법

리포 루트의 [`./hermess`](hermess) 래퍼를 쓴다. `HERMES_HOME` / `CODEX_HOME` / `PATH` 를
알아서 잡고 `hermes-agent/`로 이동해 실행한다.

```bash
./hermess <아무 hermes 명령>
```

`HERMES_HOME`은 기본 `~/.hermes-poc`이고, 바꾸려면 앞에 붙인다:
`HERMES_HOME=~/.hermes-other ./hermess ...`

### 대화형 세션

```bash
./hermess chat                    # 기본 프로필
./hermess -p backend-eng chat     # 특정 프로필
./hermess -p architect chat --checkpoints   # 파일을 만질 거면 체크포인트 on
```

세션 안에서 `/kanban`, `/rollback`, `/model` 같은 슬래시 커맨드를 쓴다.
**`/rollback`은 대화형에서만 동작한다** — `-q`로 주면 그냥 문자열로 해석된다.

### 단발 실행 (스크립트·자동화용)

```bash
./hermess -p backend-eng chat -q "..."     -m gpt-5.6-luna --provider openai-codex --reasoning high
```

`--reasoning`은 `low|medium|high|xhigh|max`. **유효 구간은 `low → high` 하나다**(§품질 축).

### 보드로 일 시키기 (권장)

```bash
# 카드 생성 — 산출물을 남기려면 반드시 dir: 또는 worktree:<절대경로>
./hermess kanban create "제목" --body "ACCEPTANCE CRITERIA: ..." \
    --assignee backend-eng --workspace dir:/abs/path

# 의존성 (부모 done 시 자식이 자동 ready)
./hermess kanban link <parent> <child>

# 태스크 단위 모델 라우팅
./hermess kanban set-model <id> gpt-5.6-sol --provider openai-codex

# 실행
./hermess kanban dispatch          # 개발용 1회
./hermess gateway start            # 운영: 내장 디스패처 (60초 tick)

# 관찰
./hermess kanban list
./hermess kanban show <id>         # 결과 · 코멘트 · 이벤트 · run 이력
./hermess kanban list --json       # 외부 연동용 (ADR-004)
python3 tools/board_report.py ~/.hermes-poc/kanban.db   # 담당자별 집계
```

가장 실용적인 진입점은 **orchestrator에게 요청만 주는 것**이다. 분해·배정·연결을 알아서 한다:

```bash
./hermess -p orchestrator chat -q "<하고 싶은 일>. 너는 코드를 못 쓰니 분해해서 배정해라."
./hermess gateway start     # 나머지는 디스패처가 진행
```

### 리뷰 루프

```bash
./hermess kanban request-review <id> --reviewer reviewer
./hermess kanban request-changes <id> "실패 입력과 기대/실제"
```

> **카드 본문에 인수 기준을 반드시 넣는다.** 리뷰 run은 구현자용으로 쓰인 같은 본문을
> 상속하므로, 기준이 없으면 리뷰어가 결함을 정확히 보고도 통과시킨다(실측).

### 사람이 끼어들기

```bash
./hermess kanban comment <id> "답변"
./hermess kanban unblock <id>      # 재spawn된 워커가 코멘트 스레드를 읽는다
```

### AGENTIC 작업 (구현 → 실행 → 자가 수정)

```bash
./hermess kanban create "..." --assignee backend-eng \
    --workspace dir:/abs/path --goal --goal-max-turns 15
```

매 턴 judge가 카드의 title+body를 인수 기준으로 완료를 판정하고, 아니면 같은 세션에서 계속한다.
예산 소진 시 조용히 끝내지 않고 `blocked` 처리한다.

### 체크포인트 / 롤백

```bash
./hermess -p backend-eng chat --checkpoints -q "..."
./hermess -p backend-eng checkpoints status     # ← -p 필수. 없으면 0 B로 오보고한다
```

복원은 대화형 `/rollback` 또는 Python API ([ADR-005](docs/adr/ADR-005-operations.md)).

### 운영 상태 점검

```bash
./hermess doctor              # 설치·인증·런타임 진단
./hermess kanban stats
./hermess kanban diagnostics  # 보드의 활성 문제
./hermess approvals test "rm -rf /"   # 실행 없이 승인 판정만 확인
```

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
                    │ comments/events│  + task_runs (시도 이력)
                    └────────┬───────┘
                             │ dispatcher (gateway 내장, 60s)
                    원자적 claim → spawn
       ┌──────────┬──────────┴────┬──────────┬──────────┐
       ▼          ▼               ▼          ▼          ▼
   architect  backend-eng     reviewer   researcher  writer/analyst
    (설계)      (구현)        (독립 검증)   (조사)      (문서/정리)
     sol        luna            sol         luna        luna
```

**3계층 경계** — 셋은 경쟁이 아니라 층이 다르다.

```
Kanban            역할 경계를 넘고 · 재시작을 견디고 · 사람이 낄 수 있는 일
  └ Bot(Profile)     그 일을 맡는 이름 있는 영속 정체성
      └ delegate_task   워커가 자기 턴 안에서 쓰는 일회성 하청
```

판정: *이 핸드오프가 단일 API 루프보다 오래 살아야 하고 남들에게 보여야 하는가?*
그렇다면 board, 아니면 delegate.

---

## 모델 라우팅

| 작업 | 배치 |
|---|---|
| 탐색·나열 (틀리면 즉시 드러나는 일) | luna / low |
| 단순 수정, CRUD/DTO, 테스트 코드 | luna / medium |
| **계산·집계·정합성이 섞인 모든 것** | **luna / high** |
| 복잡한 버그, Root Cause, 동시성 | sol / high |
| 2회 실패 | **Opus / high 독립 분석** (승격 아님, 관점 교체) |
| AGENTIC (구현+실행+검증) | luna\|sol + `--goal` (Astra 미가용) |
| 분석 · 계획 · 리뷰 · ADR | Opus |
| 시스템 전체 Architecture | Fable / high |

승격은 **행을 고쳐 다시 dispatch**다 — `tasks.model_override / provider_override /
reasoning_effort` 컬럼이 사다리를 그대로 표현한다. 라우터 코드가 없다.

---

## 검증된 사실 (재현 가능)

| 항목 | 결과 |
|---|---|
| Hermes가 Codex 구독 인증으로 구동 | ✅ |
| `delegate_task` (`openai_runtime: auto`) | ✅ subagent → PONG |
| `memory` 영속 | ✅ `memories/MEMORY.md` |
| Kanban 의존성 해석 · 부모 결과 전달 | ✅ |
| 태스크 단위 모델 override | ✅ |
| orchestrator 툴셋 박탈 강제 | ✅ 직접 실행 실패 → 라우팅 → 워커가 완수 |
| 리뷰 되돌림 루프 | ✅ 구현 → 반려 → 수정 → 통과, run 4건 이력 |
| 사람 개입 루프 | ✅ block → comment → unblock → 반영 |
| `--goal` 자가 완료 | ✅ pytest 부재 → **스스로 unittest 전환** → 5/5 통과 |
| 동시 워커 20개 | ✅ 72초, 실패 0 |
| 디스패처 데몬 | ✅ 15초 tick 자동 처리 |
| 체크포인트 복원 | ✅ `WRECKED3` → `BASELINE v3` |
| 승인 시스템 | ✅ `rm -rf /` deny, 파이프-투-셸 dangerous |
| **E2E: 요청 → 분해 → 구현 → 검증** | ✅ orchestrator가 3단 파이프라인을 스스로 설계·연결, 데몬이 무인 완주 |
| 교차 provider 위임 (anthropic ↔ openai-codex) | ✅ 자격증명 해석 |
| Astra (AGENTIC 축) | ✗ HTTP 400 — 이 계정 미가용 |

### 모델 비교 (동일 문제 · 동일 정답 · effort=high)

| model | reasoning tokens |
|---|---|
| gpt-5.3-codex-spark | 1211 |
| gpt-5.6-luna | 295 |
| gpt-5.6-sol | **155** |
| gpt-5.6-terra | 154 |

### effort 품질 (문제 5종, 순수 추론)

| | low | high | max |
|---|---|---|---|
| 정답률 | **2/5 (40%)** | 5/5 | 4/4 |
| 평균 토큰 | 813 | 1666 | 1162 |

### 뒤집힌 초기 결론

- ~~GPT 경로는 memory/delegation 불가~~ → `codex_app_server`에서만. 기본 `auto`는 정상
- ~~`max_concurrent_children` 기본 3~~ → **10**
- ~~API Server(REST)로 연동~~ → kanban 미노출. CLI `--json`으로 반전
- ~~"spark만 사용 가능"은 권한 문제~~ → **quota 소진**이었고, 회복 후 spark를 폴백으로 강등
- ~~effort 사다리 3단~~ → 유효 구간은 `low → high` **하나**

---

## 알려진 함정

**1. toolset 설정 키가 두 개이고 둘 다 필요하다**

```yaml
platform_toolsets:                    # 실제 툴 노출 제한
  cli: [kanban, memory, skills]
toolsets: [kanban, memory, skills]    # kanban check_fn이 읽는 키
```

`cli-config.yaml.example`은 최상위 `toolsets`를 *"deprecated and ignored"*라고 하지만
`tools/kanban_tools.py:_profile_has_kanban_toolset()`이 실제로 이 키를 읽는다.
하나만 쓰면 제한이 안 걸리거나 kanban 툴이 안 뜬다.

**2. 실행 툴 없는 프로필에 `delegation`을 주지 말 것**

자식은 부모 툴셋의 교집합이라(`delegate_tool.py:1827`) 막다른 길이 된다.
실측에서 **56회 tool call · 3분 thrash 후 거짓 완료 보고**가 발생했다.

**3. `scratch` 워크스페이스는 완료 시 삭제된다**

`--workspace dir:<절대경로>` / `worktree:` 또는 `kanban_complete(artifacts=[...])`.

**4. `checkpoints status`는 `-p <프로필>` 없이는 0 B로 오보고한다**

저장소가 프로필별이다. "체크포인트가 안 잡힌다"는 오진의 원인.

**5. 모델 가용성을 "OK" 출력으로 판단하지 말 것**

존재하지 않는 slug에도 grep이 "OK"를 잡은 적이 있다. 실제로는 HTTP 400이었다.
**전체 출력 또는 `session_model_usage.model`로 확인한다.**

**6. 리뷰가 붙는 카드는 본문에 인수 기준을 반드시 넣을 것**

리뷰 run은 구현자용 본문을 상속한다. 기준이 없으면 결함을 보고도 통과시킨다.

**7. `worktree` 워크스페이스는 카드 본문의 절대경로를 무시한다**

카드에 `/abs/path/x.py`를 쓰라고 해도 워커의 쓰기는 `.worktrees/<id>/` 안으로 격리된다.
격리가 목적이면 맞는 동작이고, 지정 위치에 파일을 남기려면 `dir:<절대경로>`를 쓴다.

**8. `worktree`는 경로를 안 주면 스폰 자체가 실패한다**

```
task ... has workspace_kind=worktree but no workspace_path,
and board 'default' has no default_workdir set
```
2회 연속 실패 시 서킷 브레이커가 카드를 자동 차단한다(설계대로).
`kanban boards set-default-workdir default <절대 리포 경로>`로 보드에 기본값을 주거나
`--workspace worktree:<절대경로>`로 카드마다 지정한다.

**9. Kanban v1 스펙 PDF는 "DESIGN ONLY"이고 구현과 다르다**

스펙 4테이블/14컬럼 → 실제 7테이블/37컬럼.
**PDF는 설계 근거로만 쓰고 사실은 코드로 확인한다.**

---

## E2E 실행 기록 (2026-09-04)

깨끗한 `HERMES_HOME`에서 README 순서대로 시작해, orchestrator에게 요청 하나만 주고
나머지는 맡겼다. 산출물은 [`tools/board_report.py`](tools/board_report.py) — 이 프로젝트가 실제로 쓰는 도구다.

**요청**: "kanban.db를 읽어 담당자별 상태 집계와 run 통계를 출력하는 스크립트. 읽기 전용,
빈 DB에서 크래시 금지. 너는 코드를 못 쓰니 분해해서 배정해라."

**orchestrator가 스스로 만든 파이프라인** (사람 개입 없이):

```
t_032e3bbf  architect    스키마·출력·읽기전용 계약 정의
     │ link
t_8e5e1b14  backend-eng  구현
     │ link
t_455a8d69  reviewer     독립 검증
```

**run 이력** — 중간 실패와 회복이 그대로 남는다:

```
#1  completed     @architect    153s
#2  spawn_failed  @backend-eng    0s   ← worktree 경로 누락
#3  gave_up       @backend-eng    0s   ← 서킷 브레이커 자동 차단
#4  completed     @backend-eng  198s   ← 보드 workdir 설정 후 재개
#5  completed     @reviewer     185s
```

**독립 검증** (사람이 직접):

| 인수 기준 | 결과 |
|---|---|
| 실제 보드 리포트 출력 | ✅ 담당자 3명, 상태 집계, 평균 run 시간 |
| 빈 DB에서 크래시 금지 | ✅ `(no assignees)`, exit 0 |
| 읽기 전용 | ✅ INSERT/UPDATE/DELETE/DROP 0건 |
| 없는 파일 / 인자 누락 | ✅ 명확한 에러 + usage, 크래시 없음 |

리뷰어 자체 판정: *"코드 검사와 실행으로 승인. 엣지 케이스 probe 통과,
실제 스키마 DB 사본에 대해 해시·스키마·행수 변화 없이 2회 통과."*

**이 실행에서 배운 것**: 위 함정 7·8번. orchestrator SOUL.md에 워크스페이스 규칙을 추가했다.

## 문서

| 문서 | 내용 |
|---|---|
| [`hermess-design-review.md`](hermess-design-review.md) | 실측 기록 — 초기 설계 오류 검증, 반증된 결론 |
| [`docs/adr/`](docs/adr/) | 설계 결정 5건 |
| [`profiles/`](profiles/) | 프로필 로스터 (SSOT) + 부트스트랩 |
| [`hermess`](hermess) | 실행 래퍼 — 환경변수를 잡고 upstream CLI로 넘긴다 |
| [`tools/board_report.py`](tools/board_report.py) | E2E 테스트 산출물 — 보드 리포팅 도구 |
| [`docs/bench.json`](docs/) · `bench-luna.csv` · `t1.csv` · `t2-*.csv` | 측정 재현 데이터 |
| [`hermess-arch.md`](hermess-arch.md) · [`heremss-research.md`](heremss-research.md) | 초기 조사 (일부 오류는 design-review에서 정정) |

---

## 남은 검증

- [ ] 브라우저 왕복이 본질인 AGENTIC 작업 (`--goal`의 한계선)
- [ ] 시크릿 축 (1Password / Bitwarden / command 소스)
- [ ] `terminal.backend: docker` 격리 실효성
- [ ] 토큰이 큰 작업 20개 동시 (측정은 1줄 쓰기 기준)
- [ ] Spring Boot 연동 PoC (CLI shell-out + 비동기 큐잉)
- [ ] upstream 업그레이드 회귀 (`toolsets` 키 제거 시 kanban 툴 소실)
