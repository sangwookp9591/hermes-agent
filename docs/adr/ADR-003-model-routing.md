# ADR-003 — Model Routing: quota-aware 사다리를 보드 컬럼으로 표현한다

- 상태 **Accepted**
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
현재(quota 소진)  spark/med → spark/high → spark/xhigh → ★Opus/high 교차 → Fable/high
```

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
| 여러 파일 수정, 복잡한 비즈니스 로직 | spark / high → (9/7 이후) luna / high |
| 복잡한 버그, Root Cause, 동시성/트랜잭션 | spark / xhigh → (9/7 이후) sol / xhigh |
| **위 단계에서 2회 실패** | **Opus / high 독립 분석** (승격 아님, 관점 교체) |
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

## 미검증 — 실행 전 확인할 것

1. **spark에서 `reasoning_effort`가 실제 차등 작동하는가.**
   codex CLI가 `bogus` 같은 무효값도 에러 없이 통과시킨다 → CLI에 검증이 없다.
   사다리의 1~3단이 전부 같은 결과라면 사다리가 무의미해지므로 **측정이 필요하다.**
2. **quota 회복(2026-09-07 11:41) 후 Luna/Sol 실호출.**
3. **ChatGPT 구독 인증이 동시 워커 N개에서 rate limit에 걸리는 지점.**
   Kanban은 프로필별 OS 프로세스라 동시성이 올라간다.

## 재검토 트리거

- 2026-09-07 quota 회복 직후 (1번 항목 결론과 함께)
- Gemini / OpenRouter 키 발급 시
- spark가 research preview에서 내려가거나 별도 quota 정책이 바뀔 때
