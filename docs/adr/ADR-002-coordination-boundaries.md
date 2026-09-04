# ADR-002 — Kanban / Bot(Profile) / delegate_task 3계층 경계

- 상태 **Accepted (2026-09-04 실행 검증 완료 — 강제 방법 정정)**
- 날짜 2026-09-04
- 관련 [ADR-001](ADR-001-kanban-adoption.md)

## 맥락

`heremss-research.md`가 "Bot Mode + subagent 병렬 실행"이라고 두 메커니즘을 한 줄로 묶었다.
이건 오류다(설계 리뷰 F-2). 셋은 성격이 다르며, 경계를 안 정하면 구현 때 무너진다.

추가로 스펙 §6이 인용한 실사용자 불만이 우리가 겪을 문제와 동일하다.

> "Researcher, Writer, QA로 프로필을 나눠도 orchestrator가 라우팅 대신
> 자기가 일을 해버린다. Orchestrator는 관제실이어야지 작업자가 아니다."

## 결정

**경쟁 관계가 아니라 3계층으로 쌓는다.**

```
Kanban          역할 경계를 넘고 · 재시작을 견디고 · 사람이 낄 수 있는 일
  └ Bot(Profile)   그 일을 맡는 이름 있는 영속 정체성 (자체 HERMES_HOME/메모리/스킬)
      └ delegate_task   워커가 자기 턴 안에서 쓰는 일회성 하청
```

**판정 기준 (스펙 §10, 단일 테스트)**

> 이 핸드오프가 **단일 API 루프보다 오래 살아야 하고, 남들에게 보여야 하는가?**
> 그렇다면 board. 아니면 delegate.

구체적 적용:

| 상황 | 계층 |
|---|---|
| 구현자 → 리뷰어 핸드오프 | **Kanban** (역할 경계 + 이력 필요) |
| 애매해서 사람에게 질문 | **Kanban** (block → comment → unblock) |
| 워커가 "이 파일 3개 요약해줘" | **delegate_task** (자기 턴 안, 결과가 자기 컨텍스트로) |
| 매일 아침 브리핑 누적 | **Kanban** (P4 journal + 영속 프로필) |
| 리뷰 지적사항 재구현 | **Kanban** (같은 태스크에 N번째 에이전트) |

**Kanban 워커가 내부적으로 delegate_task를 부르는 것은 정상이며 권장된다.**

## Orchestrator는 물리적으로 일하지 못하게 만든다

관례나 프롬프트 지시가 아니라 **toolset 박탈**로 강제한다(스펙 §6.1).
다만 **강제 지점이 스펙 표기와 다르다** — 아래는 실측으로 확정한 형태다.

### 실측: 설정 키가 두 개이고, 둘 다 필요하다

```yaml
# ~/.hermes/profiles/orchestrator/config.yaml
platform_toolsets:                      # ← 실제 툴 노출을 제한하는 키
  cli: [kanban, memory, skills]
toolsets: [kanban, memory, skills]      # ← kanban check_fn이 읽는 키
```

**왜 둘 다 필요한가 (Hermes upstream 불일치):**

| 키 | 문서 | 실제 코드 |
|---|---|---|
| `toolsets` (최상위) | `cli-config.yaml.example:1427` — *"deprecated and ignored"* | `tools/kanban_tools.py:_profile_has_kanban_toolset()`이 **이 키를 읽는다** |
| `platform_toolsets` | 정식 키 | 실제 툴 노출을 제한 |

→ `platform_toolsets`만 쓰면 제한은 걸리지만 **kanban 툴이 로딩되지 않는다**(실측: `memory`,
`skill_*`만 남음). `toolsets`만 쓰면 **무시되어 제한이 안 걸린다**(실측: orchestrator가
terminal로 파일 생성 성공 — 강제 실패).

### 실측: delegation은 orchestrator에서 빼야 한다

`delegate_tool.py:1827` — `child_toolsets = [t for t in toolsets if t in expanded_parent]`.
자식은 **부모 툴셋의 교집합**이라 위임이 우회로가 되지는 않는다(보안상 좋음).
그러나 그래서 **실행 툴 없는 orchestrator의 자식도 실행할 수 없다** = 막다른 길이다.

실측에서 이 조합은 **56회 tool call · 3분 12초 thrash 후 "완료했습니다"라고 거짓 보고**했다
(파일은 생성되지 않음). 위험한 실패 모드다.

→ **orchestrator에서 `delegation`을 제거한다.** 실행이 필요한 일은 반드시
kanban으로 *툴을 가진 프로필*에 배정한다.

### 검증된 최종 형태

```
orchestrator  platform_toolsets.cli + toolsets = [kanban, memory, skills]
```

실행 검증 (2026-09-04):

```
1. 직접 실행 요청       → 툴 없음, 파일 미생성                    ✅ 강제 성공
2. "kanban으로 배정하라" → kanban_create 호출, t_84324fe5 생성     ✅ 라우팅 성공
3. dispatch             → writer 스폰 → done → /tmp/orch-test.txt: HELLO  ✅ 완결
```

orchestrator는 파일을 못 만들지만, 그가 배정한 writer는 만든다 — 의도한 분업이다.

## 프로필 로스터

`hermess-arch.md`의 역할 구분을 유지하되 Kanban 프로필로 매핑한다.

| 프로필 | 역할 | toolsets (양쪽 키에 동일하게) | 배치 (ADR-003) |
|---|---|---|---|
| `orchestrator` | 분해·라우팅·요약만 | `[kanban, memory, skills]` | Opus / high |
| `architect` | 요구사항 분석 · 설계 | `[kanban, file, web, memory, skills]` | Opus / high |
| `backend-eng` | 구현 · 테스트 | `[kanban, file, terminal, coding, memory, skills, delegation]` | spark → luna |
| `reviewer` | **독립 검증** | `[kanban, file, terminal, memory, skills]` | Opus / high |
| `analyst` | 대량 문서 · 로그 정리 | `[kanban, file, web, search, memory, skills]` | Gemini Flash (키 필요) |

`delegation`은 **실행 툴을 가진 프로필에만** 준다(위 실측 근거).
현재 POC에 `orchestrator / researcher / writer / reviewer` 4개가 구축돼 있다.

**`reviewer`는 구현자와 반드시 다른 프로필이자 다른 모델이어야 한다.**
같은 모델이 자기 코드를 채점하면 검증이 무의미하다.

## 결과

- **얻는 것**: F-2 해소. 어떤 화살표가 무엇인지 확정됐고, **실행으로 검증됐다.**
- **주의(upstream 리스크)**: `toolsets` 최상위 키는 문서상 deprecated다.
  upstream이 이 키를 실제로 제거하면 kanban check_fn이 깨진다.
  업그레이드 시 **orchestrator가 kanban 툴을 계속 갖는지 반드시 재확인**한다.
- **포기하는 것**: v1은 태스크당 assignee 1명이다. 두 명이 필요하면 형제 태스크 2개로 나눈다.
- **주의**: `orchestrator`의 toolset 제한을 풀면 즉시 §6 실패 모드로 돌아간다. 풀지 않는다.

## 계층 깊이

기본 `max_spawn_depth: 1`(평면)을 유지한다. Kanban이 상위 조율을 담당하므로
delegate_task 트리를 깊게 만들 이유가 없다. `role="orchestrator"`는 당분간 쓰지 않는다.
