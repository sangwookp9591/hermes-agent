# 프로필 로스터

[ADR-002](../docs/adr/ADR-002-coordination-boundaries.md)가 정의한 역할 분리를
Hermes 프로필로 구현한 것. 이 디렉터리가 SSOT다.

## 설치

```bash
HERMES_HOME=~/.hermes-poc ./profiles/bootstrap.sh
```

## 로스터

| 프로필 | 역할 | delegation | 비고 |
|---|---|---|---|
| `orchestrator` | 분해 · 라우팅 · 요약만 | ✗ | **실행 툴 없음.** 일을 물리적으로 못 한다 |
| `architect` | 요구사항 분석 · 설계 | ✗ | |
| `backend-eng` | 구현 · 테스트 | **✓** | 실행 툴이 있는 유일한 프로필 |
| `reviewer` | 독립 검증 | ✗ | 구현자와 **반드시 다른** 프로필 |
| `researcher` | 조사 · 자료 수집 | ✗ | |
| `writer` | 문서 작성 | ✗ | |
| `analyst` | 대량 문서 · 로그 정리 | ✗ | Gemini 키 발급 시 모델 교체 대상 |

## 설정 키가 두 개인 이유

각 `config.yaml`이 같은 목록을 두 키에 중복 기재한다. 실수가 아니다.

| 키 | 문서상 | 실제 |
|---|---|---|
| `platform_toolsets` | 정식 키 | 실제 툴 노출 제한 |
| `toolsets` (최상위) | *"deprecated and ignored"* | `tools/kanban_tools.py:_profile_has_kanban_toolset()`가 읽음 |

하나만 쓰면 **제한이 안 걸리거나 kanban 툴이 안 뜬다.** 둘 다 필요하다.

> **업그레이드 시 확인**: upstream이 `toolsets` 키를 실제로 제거하면 kanban check_fn이 깨진다.
> orchestrator가 kanban 툴을 계속 갖는지 반드시 재확인할 것.

## `delegation`을 함부로 주지 말 것

자식은 부모 툴셋의 **교집합**이다(`delegate_tool.py:1827`).
실행 툴 없는 프로필에 delegation을 주면 자식도 실행할 수 없어 **막다른 길**이 된다.
실측에서 이 조합은 56회 tool call · 3분 thrash 후 **거짓 완료 보고**를 냈다.

## 검증

```bash
uv run python -m hermes_cli.main -p orchestrator chat -q "List the exact names of every tool you have."
# kanban_* 가 보이고 terminal / file 이 없어야 정상
```
