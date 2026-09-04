# ADR-003 — Model Routing: quota-aware 사다리를 보드 컬럼으로 표현한다

- 상태 **Accepted (2026-09-04 3차 개정 — AGENTIC 축 추가, Astra 미가용 확인)**
- 날짜 2026-09-04
- 관련 [ADR-002](ADR-002-coordination-boundaries.md)

## 맥락

`~/.claude/skills/model-routing/SKILL.md`는 `GPT-5.6 Luna / Sol` 2차원 사다리를 전제한다.
이용자는 "GPT는 현재 5.3 spark만 가능"이라고 했다.

**실측 결과 이용자 전제는 맞았지만 이유가 달랐다.**

```
plan = prolite
백엔드 응답: gpt-5.6-sol / terra / luna / 5.5 / 5.4 / 5.4-mini  전부 열려 있음
실호출:  spark => OK
        luna  => usage limit, retry at Sep 7th 2026 11:41 AM
```

**권한이 아니라 quota 소진**이고, spark만 별도 버킷이라 혼자 살아 있다.
(웹 리서치로 spark의 별도 usage limit이 공식 동작임을 확인.)

즉 **제약에 만료일이 있다.** skill의 Luna/Sol 표는 틀리지 않았다 —
`hermes_cli/codex_models.py`의 `DEFAULT_CODEX_MODELS`에 그대로 있고, 지금 못 쓸 뿐이다.

## 결정

### 1. spark에 하드코딩하지 않는다 — quota-aware 폴백으로 짠다

```
[채택 · quota 정상]  luna/low → luna/medium → luna/high → luna/max
                              → sol/high → ★Opus/high 교차 → Fable/high

[폴백 · quota 소진]  spark/low → spark/medium → spark/high → ★Opus/high 교차
                     (spark에서 xhigh는 쓰지 않는다 — 무효)
```

> **T2 실측 반영(§4.7).** quota 회복 후 재측정 결과 **spark를 기본으로 둘 이유가 없다.**
> Luna는 동일 문제·동일 정답률에서 spark보다 **추론 토큰을 4배 적게 쓰고**,
> `max`까지 사다리가 실제로 작동한다. spark는 quota 폴백으로 강등한다.

모델 축이 막히면 **provider 교차 검증이 그 자리를 대신한다.**
이건 손해가 아니다 — 원래 skill도 "Sol/xhigh에서 막히면 성능이 아니라 전제를 의심하라"고
했는데, 이제 강제로 그 단계로 간다.

### 2. 사다리를 보드 컬럼으로 표현한다 (별도 라우터를 만들지 않는다)

`tasks` 테이블에 실측 확인된 3개 컬럼이 있다.

```
model_override · provider_override · reasoning_effort
```

CLI/툴로 노출돼 있고 실행 검증했다.

```bash
hermes kanban create "..." --assignee backend-eng \
    --model gpt-5.3-codex-spark --provider openai-codex
hermes kanban set-model <id> gpt-5.6-luna --provider openai-codex   # 승격
```

→ **승격은 "행을 고쳐 다시 dispatch"다.** 라우터 코드가 필요 없다.
또한 `task_events`에 override가 기록되므로 **어느 단계에서 풀렸는지 사후에 알 수 있다** —
skill이 "한 칸씩 올려라"고 한 이유(정보 손실 방지)가 자동으로 충족된다.

### 3. 배치표

| 작업 | 배치 |
|---|---|
| 파일/코드 탐색 | luna / low |
| 단순 수정, CRUD/DTO, 테스트 코드 | luna / low |
| 일반 구현, 빌드·테스트 오류 수정 | luna / medium |
| 여러 파일 수정, 복잡한 비즈니스 로직 | luna / high |
| 복잡한 버그, Root Cause, 동시성/트랜잭션 | sol / high |
| Production 장애, 반복 실패 | sol / max |
| **위 단계에서 2회 실패** | **Opus / high 독립 분석** (승격 아님, 관점 교체) |
| 구현 + 기동 + 브라우저/E2E 실검증 (AGENTIC) | ~~Astra~~ 미가용 → **luna\|sol + `--goal`** (§4.8) |
| 요구사항 분석 / 문서 / ADR | Opus / medium |
| 계획, 영향도 분석, 코드 리뷰, 독립 검증 | Opus / high |
| 시스템 전체 Architecture, 대규모 Migration | Fable / high |
| 대량 문서·로그·이미지 정리 | Gemini Flash (**키 미발급**) |

> **쉬운 태스크에 effort를 올리지 않는다** — 모델이 문제가 요구할 때만 더 쓴다(§4.7).
> **quota 소진 시 폴백**: `spark`로 내려가되 천장은 `high`. `xhigh`는 무효이므로 쓰지 않는다.
> **AGENTIC은 CODE 사다리를 타지 않는다** — 처음부터 `--goal` 카드로 만든다.

### 4. Codex 런타임은 `auto`로 고정한다

```yaml
model:
  openai_runtime: auto      # codex_app_server 금지
```

`codex_app_server`를 켜면 `delegate_task` · `memory` · `session_search` · `todo`가 죽는다.
기본 `auto`에서는 전부 작동함을 실행으로 확인했다(설계 리뷰 §2.2).

### 5. 교차 provider 위임은 확인됐다

```
openai-codex → OK  api_mode=codex_responses    key=Y
anthropic    → OK  api_mode=anthropic_messages key=Y
openrouter   → 키 없음
google       → 키 없음
```

`cli-config.yaml.example`의 지원 목록(`openrouter, nous, zai, kimi-coding, minimax`)은
**불완전한 주석**이다. 실제로는 `resolve_runtime_provider()`로 위임되므로 anthropic도 된다.

## 결과

- **얻는 것**: 라우터 코드 0줄. 승격 이력이 감사 로그로 남는다.
- **포기하는 것**: Gemini 트랙은 키 발급 전까지 비활성. 멀티모달/대량 문서 작업은
  당분간 Opus가 떠안거나 보류한다.
- **되돌리기**: 사다리는 config·컬럼 값이라 코드 변경 없이 조정된다.

## 4.6 T1 실측 — spark의 effort 사다리는 2단이다

**코드 레벨.** `agent/reasoning_effort.codex_supported_efforts()` 실행값:

```
gpt-5.3-codex-spark  ('none','low','medium','high','xhigh')      ← max 없음
gpt-5.6-luna / sol   ('none','low','medium','high','xhigh','max')
```

spark에 `max`를 요청하면 `clamp_effort`가 **`xhigh`로 강등**한다(절대 승격 안 함).
즉 skill의 `Sol/max` 단계는 spark에서 존재하지 않는다.

**실측.** 동일 추론 문제(5x5 그리드, 정답 R+C=130)를 effort별 3회씩 총 12회 실행하고
`session_model_usage.reasoning_tokens`를 비교했다.

| effort | reasoning tokens (3회) | 평균 | low 대비 |
|---|---|---|---|
| low | 183, 154, 152 | 163 | 1.00x |
| medium | 497, 834, 835 | 722 | **4.43x** |
| high | 1284, 536, 998 | 939 | 5.76x |
| xhigh | 753, 982, 1069 | 935 | **5.73x** |

**판정**

- `low → medium` — **유효.** 범위가 겹치지 않는다(low 최대 183 < medium 최소 497).
- `medium → high` — **약함.** 범위가 겹친다(medium 835 vs high 536).
- `high → xhigh` — **무효.** 평균이 사실상 동일하고(939 / 935) 범위가 완전히 겹친다.

정답률은 전 조건 100%였다. 즉 이 측정은 **"추론을 얼마나 쓰는가"**를 본 것이지
품질을 직접 잰 게 아니다. 다만 high와 xhigh가 같은 양을 쓴다면
**xhigh가 더 나을 기전 자체가 없다.**

**따라서 사다리를 줄인다.**

```
[폐기]  spark/medium → spark/high → spark/xhigh → Opus
[채택]  spark/low → spark/medium → Opus/high 교차 → Fable/high
```

`high`/`xhigh`는 배치표에서 **spark 한정으로 쓰지 않는다** — 토큰만 더 쓰고 얻는 게 없다.
Luna/Sol에는 `max`가 있으므로 quota 회복 후 재측정한다(아래 2번).

**한계**: 문제 1종 · 조건당 3회. `high`/`xhigh` 동일성은 신호가 강하나,
`medium`/`high` 구분은 표본이 더 필요하다. 재현 데이터는 `/tmp/t1.csv`.

## 4.7 T2 실측 — quota 회복 후 (2026-09-04)

전 모델 응답 확인: `luna / sol / terra / 5.5 / 5.4 / 5.4-mini / spark` 7종 OK.

### effort 사다리는 문제 난이도에 따라 열린다

쉬운 문제(5x5 그리드)에서는 Luna의 인접 단계가 **전부 겹쳤다**(low 104 → max 236, 2.3x).
어려운 문제(교란순열 D(8))에서는 분리됐다. 즉 모델은 **문제가 요구할 때만 더 쓴다.**

→ **쉬운 태스크에 effort를 올리는 것은 낭비다.** 사다리는 어려운 문제에서만 의미가 있다.

### 동일 문제(D(8)=14833) · 조건당 3회 · 정답률 전 조건 100%

| effort | spark | luna |
|---|---|---|
| low | 842, 452, 722 → **672** | 86, 190, 164 → **147** |
| high | 1333, 1207, 1092 → **1211** | 363, 342, 181 → **295** |
| xhigh | 891, 1059, 1246 → **1065** | — |
| max | (미지원) | 409, 528, 411 → **449** |

- **spark `high → xhigh`: 무효.** 범위가 겹칠 뿐 아니라 **평균이 오히려 낮다**(1065 < 1211).
  T1 결론이 문제 난이도 탓이 아님을 확정한다.
- **luna `high → max`: 유효.** 범위가 겹치지 않는다(363 < 409).

### 모델 축 — effort=high 고정, 동일 문제

| model | reasoning tokens | 평균 |
|---|---|---|
| gpt-5.3-codex-spark | 1333, 1207, 1092 | **1211** |
| gpt-5.6-luna | 363, 342, 181 | **295** |
| gpt-5.6-sol | 113, 168, 183 | **155** |
| gpt-5.6-terra | 153, 140, 168 | **154** |

정답률은 전부 100%다. **spark가 같은 답을 내는 데 Sol의 8배, Luna의 4배를 쓴다.**

> **결정 변경**: 기본 실행 모델을 **spark → luna**로 바꾼다.
> spark는 quota 폴백 전용이며, 그 안에서 천장은 `high`다(`xhigh` 금지).

**한계**: 문제 2종 · 조건당 3회 · 전 조건 정답률 100%라
**품질 차이는 측정하지 못했다.** 측정한 것은 "추론을 얼마나 쓰는가"다.
low에서도 정답이 나오는 문제였으므로, 난이도가 더 높을 때의 정답률 차이는 미지수다.
재현 데이터: `docs/t1.csv`, `docs/t2-*.csv`.

## 4.8 AGENTIC 축 — Astra는 이 계정에서 사용 불가

`model-routing` skill이 네 번째 축을 추가했다.

```
CODE / PLAN·REVIEW / MULTIMODAL·DATA / AGENTIC·COMPUTER USE
                                       └ GPT-6 Astra
```

판별 기준: *"코드만 고치면 끝나는가, 아니면 띄우고·눌러보고·확인까지 해야 끝나는가?"*
후자가 AGENTIC이고, **Astra는 Sol의 상위 칸이 아니라 다른 축**이다
(Sol=깊이, Astra=폭). 우리 Kanban 워커가 "구현 → 서버 기동 → 브라우저 확인"을
한 카드 안에서 하려는 순간 이 축에 해당한다.

### 실측 — 사용 불가

백엔드 모델 목록(plan=prolite)에 astra/gpt-6 계열이 **없다**. 실호출 결과:

```
HTTP 400: {"detail":"The 'gpt-6-astra' model is not supported
           when using Codex with a ChatGPT account."}
```

Hermes 코드베이스도 `astra` / `gpt-6`를 모른다(`codex_models.py`, `model_metadata.py`,
`reasoning_effort.py` 전부 미인지). quota 문제였던 Luna/Sol과 달리 이건 **entitlement 문제**라
시간이 지나도 열리지 않는다.

> **주의**: 검증 중 `-m astra` 같은 존재하지 않는 slug에 "OK"가 나온 것처럼 보였으나
> grep 오탐이었다. 모델 가용성은 **전체 출력 또는 `session_model_usage.model`로 확인**한다.

### 그래서 AGENTIC 축을 무엇으로 채우는가

**모델 층이 아니라 오케스트레이션 층으로 대체한다.**

Kanban의 `--goal` / `goal_mode=True`가 Astra의 핵심 성질(장시간 멀티스텝 자가 완료)을
카드 단위로 제공한다 — 매 턴 후 보조 judge가 카드의 title+body를 인수 기준으로 삼아
완료 여부를 판정하고, 아니면 **같은 세션에서 계속 진행**한다. 예산 소진 시 조용히 끝내지 않고
`blocked` 처리한다.

```yaml
# AGENTIC 성격의 카드
hermes kanban create "..." --assignee backend-eng   --workspace dir:/abs/path --goal --goal-max-turns 20
```

즉 배치는 **`luna|sol` + `--goal` + browser/terminal toolset**이고, Astra가 열리면
그때 모델 축으로 옮긴다.

**한계**: judge 기반 반복은 Astra의 네이티브 computer-use와 동등하지 않다.
브라우저 왕복이 본질인 작업의 품질은 검증하지 못했다(아래 미검증 5번).

## 미검증 — 실행 전 확인할 것

1. ~~spark `reasoning_effort` 차등~~ → **해소(§4.6, §4.7).** `xhigh` 무효 확정.
2. ~~quota 회복 후 Luna/Sol + `max` 재측정~~ → **해소(§4.7).** 기본 모델을 luna로 변경.
3. **정답률이 갈리는 난이도에서의 effort 효과.** 위 측정은 전부 100% 정답이라
   품질 축을 못 봤다. 실패가 나오는 문제로 재측정이 필요하다.
4. **ChatGPT 구독 인증이 동시 워커 N개에서 rate limit에 걸리는 지점.**
   Kanban은 프로필별 OS 프로세스라 동시성이 올라간다.
5. **`--goal` 루프가 AGENTIC 작업을 실제로 완주하는가**(§4.8 대체안).
   "구현 → 서버 기동 → 브라우저 확인 → 실패 시 자가 수정" 카드로 검증 필요.
6. **Astra 개방 여부 재확인** — plan 업그레이드 또는 OpenAI 정책 변경 시.

## 재검토 트리거

- 2026-09-07 quota 회복 직후 (1번 항목 결론과 함께)
- Gemini / OpenRouter 키 발급 시
- spark가 research preview에서 내려가거나 별도 quota 정책이 바뀔 때
