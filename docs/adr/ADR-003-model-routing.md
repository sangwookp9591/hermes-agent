# ADR-003 — Model Routing: quota-aware 사다리를 보드 컬럼으로 표현한다

- 상태 **Accepted (2026-09-04 개정 — T1 실측으로 사다리 단축)**
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
정상시(9/7 이후)  spark/med → luna/high → sol/high → sol/xhigh → Opus 교차 → Fable/high
현재(quota 소진)  spark/low → spark/medium → ★Opus/high 교차 → Fable/high
```

> **T1 실측 반영.** 초안은 `spark/med → high → xhigh` 3단이었으나,
> 측정 결과 **high와 xhigh가 구분되지 않아** 2단으로 줄였다. 아래 §4.6 참조.

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
| 파일/코드 탐색 | spark / low |
| 단순 수정, CRUD/DTO, 테스트 코드 | spark / medium |
| 일반 구현, 빌드·테스트 오류 수정 | spark / medium |
| 여러 파일 수정, 복잡한 비즈니스 로직 | spark / medium → (9/7 이후) luna / high |
| 복잡한 버그, Root Cause, 동시성/트랜잭션 | **Opus / high** → (9/7 이후) sol / xhigh |
| **위 단계에서 2회 실패** | **Opus / high 독립 분석** (승격 아님, 관점 교체) |

> spark에서는 `high`/`xhigh`를 쓰지 않는다(§4.6). quota 소진 중에는
> `spark/medium`이 GPT 쪽 천장이고, 그 위는 provider 교차다.
| 요구사항 분석 / 문서 / ADR | Opus / medium |
| 계획, 영향도 분석, 코드 리뷰, 독립 검증 | Opus / high |
| 시스템 전체 Architecture, 대규모 Migration | Fable / high |
| 대량 문서·로그·이미지 정리 | Gemini Flash (**키 미발급**) |

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

## 미검증 — 실행 전 확인할 것

1. ~~spark에서 `reasoning_effort`가 차등 작동하는가~~ → **해소(§4.6).**
   작동하나 `high`/`xhigh`는 구분되지 않아 사다리를 2단으로 단축했다.
2. **quota 회복(2026-09-07 11:41) 후 Luna/Sol 실호출** + `max` 포함 effort 재측정.
3. **ChatGPT 구독 인증이 동시 워커 N개에서 rate limit에 걸리는 지점.**
   Kanban은 프로필별 OS 프로세스라 동시성이 올라간다.

## 재검토 트리거

- 2026-09-07 quota 회복 직후 (1번 항목 결론과 함께)
- Gemini / OpenRouter 키 발급 시
- spark가 research preview에서 내려가거나 별도 quota 정책이 바뀔 때
