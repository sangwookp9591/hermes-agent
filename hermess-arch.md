네. **Hermes Agent를 직접 만들거나 구조를 참고해서 자체 Agent 플랫폼을 만들 목적**이라면, 블로그보다 **Nous Research 공식 GitHub + 공식 Developer Guide**를 기준으로 보는 게 가장 좋습니다.

가장 중요한 원본은 이것입니다.

[NousResearch/hermes-agent 공식 GitHub](https://github.com/NousResearch/hermes-agent?utm_source=chatgpt.com)
[Hermes Agent 공식 문서](https://hermes-agent.nousresearch.com/docs/?utm_source=chatgpt.com)

Hermes는 MIT 라이선스이고, 핵심 Agent Loop부터 Tools, Memory, Skills, MCP, Bot Mode, Cron, Gateway까지 실제 구현이 모두 공개돼 있습니다. 공식 문서는 현재 코드베이스 구조까지 상당히 자세하게 설명합니다. ([GitHub][1])

### 제가 읽는 순서를 잡는다면

| 순서 | 볼 것             | 왜 중요한가                               |
| -- | --------------- | ------------------------------------ |
| 1  | Architecture    | Hermes 전체 구조 파악                      |
| 2  | Agent Loop      | LLM → Tool → Result → LLM 반복 핵심      |
| 3  | Prompt Assembly | System Prompt / Memory / Skill 결합 방식 |
| 4  | Tools Runtime   | Agent가 실제 행동하는 구조                    |
| 5  | Memory          | 세션을 넘어 기억하는 방식                       |
| 6  | Skills          | 경험을 재사용 가능한 절차로 만드는 방식               |
| 7  | MCP             | GitHub·DB·사내 API 등 외부 도구 연결          |
| 8  | Bot Mode        | 여러 전문 Agent 구성                       |
| 9  | Gateway         | Slack/Telegram 등 장기 실행 Agent         |
| 10 | Security        | 실행 권한과 위험 명령 통제                      |

특히 공식 Architecture 문서 자체도 거의 이 순서대로 `Architecture → Agent Loop → Prompt Assembly → Provider → Tools → Session → Gateway → Context Compression`을 권장하고 있습니다. ([Hermes Agent][2])

### 1. 가장 먼저 볼 Architecture

[Hermes Architecture](https://hermes-agent.nousresearch.com/docs/developer-guide/architecture?utm_source=chatgpt.com)

이 문서가 제일 중요합니다.

Hermes 내부는 대략 이렇게 생겼습니다.

```text
                 Entry Points
     CLI / Gateway / API / Python Library
                      │
                      ▼
                  AIAgent
               run_agent.py
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
     Prompt         Tools        Provider
     Builder        Runtime       Runtime
        │             │             │
        ▼             ▼             ▼
     Memory        MCP/Skill      LLM APIs
        │
        ▼
   Session / Context
```

실제 핵심 파일도 공식 문서에 나옵니다.

```text
hermes-agent/

├─ run_agent.py
│   └─ AIAgent
│
├─ agent/
│   ├─ prompt_builder.py
│   ├─ context_engine.py
│   ├─ context_compressor.py
│   ├─ prompt_caching.py
│   ├─ runtime_provider.py
│   └─ models.py
│
├─ tools/
│
├─ gateway/
│
├─ hermes_state.py
│
└─ skills/
```

`run_agent.py`의 `AIAgent`가 사실상 Hermes의 심장입니다. ([Hermes Agent][2])

---

# 2. 실제 Agent Loop는 이 문서를 보면 됩니다

[Agent Loop Internals](https://hermes-agent.nousresearch.com/docs/developer-guide/agent-loop?utm_source=chatgpt.com)

여기서 Hermes가 어떻게 계속 작업하는지 볼 수 있습니다.

개념적으로는:

```text
User
 ↓
Prompt 구성
 ↓
LLM
 ↓
Tool Call 필요?
 │
 ├─ NO → Final Response
 │
 └─ YES
      ↓
   Tool 실행
      ↓
   Result
      ↓
     LLM
      ↓
   다시 판단
```

하지만 실제 Hermes는 여기에 더 들어갑니다.

```text
AIAgent
 │
 ├─ Provider 선택
 ├─ Prompt 조립
 ├─ Tool schema 제공
 ├─ Model 호출
 ├─ Tool 병렬 실행
 ├─ Retry
 ├─ Fallback Model
 ├─ Context Compression
 ├─ Memory Flush
 └─ Session 저장
```

즉 단순 ReAct Agent보다 **운영 가능한 Runtime**에 더 가깝습니다. ([Hermes Agent][3])

---

# 3. 당신이 특히 봐야 하는 건 Skills

[Hermes Skills System](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills/?utm_source=chatgpt.com)

제가 보기엔 Hermes에서 가장 참고할 가치가 큰 부분 중 하나입니다.

Skill은 코드가 아니라 기본적으로:

```text
SKILL.md
```

형태의 **필요할 때만 읽는 작업 지침서**입니다.

예를 들어:

```text
skills/
 ├─ deploy/
 │   └─ SKILL.md
 │
 ├─ github-pr/
 │   └─ SKILL.md
 │
 ├─ code-review/
 │   └─ SKILL.md
 │
 └─ postgres-debug/
     └─ SKILL.md
```

Agent가 모든 내용을 항상 컨텍스트에 넣는 게 아니라 **Skill 설명만 먼저 알고 있다가 해당 작업이 들어오면 본문을 로드**합니다.

그래서 토큰도 덜 먹습니다. 공식 문서도 이를 progressive disclosure 구조라고 설명합니다. ([Hermes Agent][4])

그리고 직접 만들 때 중요한 판단 기준도 잘 나와 있습니다.

[Creating Skills 공식 가이드](https://hermes-agent.nousresearch.com/docs/developer-guide/creating-skills?utm_source=chatgpt.com)

예를 들어:

```text
Git Workflow
Docker Deploy
PDF 분석
Code Review 방법
```

처럼 **기존 도구를 어떻게 사용할지 알려주는 것**은 Skill.

반대로:

```text
Browser Automation
Streaming API
Custom Authentication
실시간 이벤트
```

처럼 실행 로직 자체가 필요한 건 Tool로 만드는 것을 권장합니다. ([Hermes Agent][5])

이 구분은 상당히 좋습니다.

---

# 4. Memory도 꼭 보세요

Hermes에서 또 중요한 건:

```text
Conversation
      ↓
중요 정보 판단
      ↓
Persistent Memory
      ↓
다음 Session
      ↓
Search / Recall
```

구조입니다.

Config에서도:

```yaml
memory:
  memory_enabled: true
  user_profile_enabled: true
  memory_char_limit: 2200
  user_char_limit: 1375
```

처럼 별도로 관리하며, memory write 자체를 사람 승인 후 저장하게 만들 수도 있습니다. ([Hermes Agent][6])

당신이 전에 이야기했던:

```text
실수
 ↓
Feedback
 ↓
Rule
 ↓
다음 작업
 ↓
같은 실수 방지
```

구조를 만들려면 Hermes의 **Memory + Skills 조합**을 특히 보는 게 좋습니다.

---

# 5. MCP는 그대로 참고할 가치가 큽니다

[Hermes MCP 공식 문서](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp?utm_source=chatgpt.com)

Hermes에서는 MCP 서버를 `config.yaml`에 등록합니다.

```yaml
mcp_servers:

  filesystem:
    command: "npx"
    args:
      - "-y"
      - "@modelcontextprotocol/server-filesystem"
      - "/projects"
```

그러면 Agent 입장에서는:

```text
Built-in Tool
MCP Tool
Plugin Tool
```

을 비슷한 방식으로 사용할 수 있습니다.

특히 Hermes는 MCP 서버가 제공하는 모든 도구를 무조건 Agent에게 노출하는 게 아니라 **include/exclude로 필요한 Tool만 노출하는 기능**도 제공합니다. ([Hermes Agent][7])

이건 자체 Agent를 만들 때 꽤 중요합니다.

Tool 100개를 모두 LLM에게 넘기면:

```text
Tool 선택 정확도 ↓
Prompt Token ↑
Latency ↑
```

가 생길 수 있기 때문입니다.

---

# 6. Multi Agent를 만들 거라면 Bot Mode

[Hermes Bot Mode](https://hermes-agent.nousresearch.com/docs/user-guide/bot-mode?utm_source=chatgpt.com)

이건 당신이 만들고 싶어 하는 구조와 상당히 비슷합니다.

Hermes에서는 Bot 하나가 사실상 **독립 Profile**입니다.

```text
Coordinator
│
├─ Architect Bot
│    ├─ Model
│    ├─ Memory
│    ├─ Skills
│    └─ Tools
│
├─ Coding Bot
│    ├─ Model
│    ├─ Memory
│    ├─ Skills
│    └─ Tools
│
└─ Reviewer Bot
     ├─ Model
     ├─ Memory
     ├─ Skills
     └─ Tools
```

각 Bot은 별도 모델, 메모리, Skills, MCP 서버, 대화 기록을 가질 수 있습니다. ([Hermes Agent][8])

예를 들어 당신 방식으로 바꾸면:

```text
Main Coordinator
        │
        ├── Claude
        │    요구사항 분석
        │    Architecture
        │
        ├── Codex
        │    코드 구현
        │    테스트
        │
        ├── Gemini
        │    이미지/PDF/CSV
        │
        └── Reviewer
             독립 검증
```

를 Hermes Profile/Bot 구조 위에 올릴 수 있습니다.

---

# 7. 장기 실행 Agent를 만들면 Gateway

[Gateway Internals](https://hermes-agent.nousresearch.com/docs/developer-guide/gateway-internals/?utm_source=chatgpt.com)

이 부분도 좋은 참고 자료입니다.

Gateway가:

```text
Slack
Telegram
Discord
WhatsApp
Teams
...
   │
   ▼
Gateway
   │
   ▼
AIAgent
```

를 담당합니다.

중요한 건 Agent Core와 Slack/Telegram 구현을 섞지 않는다는 점입니다.

```text
Channel Adapter
      ↓
Gateway
      ↓
Agent Core
```

구조로 분리합니다. 공식 Gateway는 세션 저장, outbound delivery, DM pairing, 채널 디렉터리, hook 등을 별도 모듈로 나눕니다. ([Hermes Agent][9])

---

# 8. 직접 서비스에 넣을 거면 Python Library 문서

Hermes 자체 UI를 쓸 게 아니라

```text
React
   ↓
Spring Boot
   ↓
AI Middleware
   ↓
Hermes
```

같이 만들 생각이면 이것도 꼭 보세요.

[Using Hermes as a Python Library](https://hermes-agent.nousresearch.com/docs/guides/python-library?utm_source=chatgpt.com)

Hermes의 `AIAgent`를 직접 import해서 사용할 수 있습니다.

기본 개념은:

```python
from run_agent import AIAgent

agent = AIAgent(...)

response = agent.chat(
    "이 Repository에서 결제 중복 지급 원인을 찾아줘"
)
```

형태입니다.

공식 문서상 현재는 일반적인 PyPI wheel을 사용하는 방식보다 **Git checkout + uv 환경**을 기준으로 지원합니다. ([Hermes Agent][10])

---

# 9. 보안 구조는 반드시 참고하세요

[Hermes Security Architecture](https://hermes-agent.nousresearch.com/docs/user-guide/security?utm_source=chatgpt.com)

Agent를 실제 업무에 사용한다면 이게 매우 중요합니다.

Hermes는 보안을 대략:

```text
Agent
 │
 ├─ 사용자 인증
 ├─ 위험 명령 승인
 ├─ File Write 제한
 ├─ Container Isolation
 ├─ MCP Credential Filtering
 ├─ Prompt Injection Detection
 ├─ Session Isolation
 └─ Input Sanitization
```

처럼 여러 겹으로 나눕니다. ([Hermes Agent][11])

특히 직접 Agent를 만들 때

```text
LLM이 shell 실행 가능
```

만 넣어놓고 끝내면 위험합니다.

최소:

```text
Read
Write
Execute
Network
Secrets
Destructive Action
```

을 권한으로 분리하는 게 좋습니다.

---

# 그리고 정말 유용한 게 하나 있습니다

공식 Hermes 문서에는 **LLM이 읽기 위한 문서 묶음**도 따로 제공합니다.

```text
/llms.txt
/llms-full.txt
```

`llms.txt`는 각 공식 문서의 인덱스이고, `llms-full.txt`는 전체 문서를 하나의 Markdown으로 합친 버전입니다. 공식 사이트는 이를 coding agent나 LLM에 넣기 위한 machine-readable entry point로 안내합니다. ([Hermes Agent][12])

즉 Claude/Codex에게 Hermes를 분석시키려면 굉장히 편합니다.

[Hermes LLM 문서 인덱스](https://hermes-agent.nousresearch.com/docs/llms.txt?utm_source=chatgpt.com)

예를 들어 Codex/Fable에:

```text
Hermes Agent를 reference architecture로 사용한다.

먼저 아래 문서를 읽어라.

https://hermes-agent.nousresearch.com/docs/llms.txt

그리고 공식 repository:

https://github.com/NousResearch/hermes-agent

특히 다음 subsystem을 분석한다.

1. AIAgent / Agent Loop
2. Tool Registry
3. Memory
4. Skills
5. MCP
6. Context Compression
7. Bot/Profile isolation
8. Gateway
9. Cron
10. Security

단순 복제하지 말고
우리 서비스에 필요한 구조와 불필요한 구조를 분리해서 ADR을 작성해라.
```

라고 시키면 상당히 좋은 출발점이 됩니다.

---

## 당신이 만든다면 저는 Hermes를 통째로 Fork하기보다 이렇게 가져오겠습니다

```text
                    AI Orchestrator
                          │
               ┌──────────┴──────────┐
               │                     │
            Router               Coordinator
                                      │
                 ┌────────────────────┼───────────────────┐
                 ▼                    ▼                   ▼
             Claude Bot           Codex Bot           Gemini Bot
             Architect            Implementer         Multimodal
                 │                    │                   │
                 └────────────────────┼───────────────────┘
                                      ▼
                              Independent Reviewer

────────────────────────────────────────────────────────────

                    Shared Runtime
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
       Memory          Skills           MCP
          │              │              │
          └──────────────┼──────────────┘
                         ▼
                       Tools
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
        GitHub          DB            Browser
        Slack           Docs          Internal API
```

그리고 Hermes에서 특히 **그대로 공부할 네 부분**을 고르면:

**`AIAgent Agent Loop + Tool Registry + Memory/Skills Learning Loop + Profile/Bot Isolation`**

입니다.

이 네 개만 제대로 이해해도 단순 ChatBot이 아니라 **“오래 일하고, 도구를 쓰고, 이전 작업을 기억하고, 다음에는 더 잘하는 Agent”** 구조가 어떻게 만들어지는지 거의 잡힙니다. ([Hermes Agent][2])

특히 공식 문서에는 **Codebase Ownership Map**도 있어서, `Agent core를 수정하려면 어디`, `Tool 추가는 어디`, `Provider는 어디`처럼 소스 위치와 테스트 위치까지 연결해줍니다. 처음 코드 뜯어볼 때 상당히 유용합니다. ([Hermes Agent][13])

원한다면 다음 단계는 **Hermes Agent GitHub를 기준으로 소스 구조를 실제 파일 단위까지 뜯어서 `Spring Boot + React 백오피스 + Python Agent Runtime`으로 재설계한 아키텍처**까지 잡는 게 좋습니다.

[1]: https://github.com/nousresearch/hermes-agent?utm_source=chatgpt.com "GitHub - NousResearch/hermes-agent: The agent that grows with you · GitHub"
[2]: https://hermes-agent.nousresearch.com/docs/developer-guide/architecture?utm_source=chatgpt.com "Architecture | Hermes Agent"
[3]: https://hermes-agent.nousresearch.com/docs/developer-guide/agent-loop?utm_source=chatgpt.com "Agent Loop Internals | Hermes Agent"
[4]: https://hermes-agent.nousresearch.com/docs/user-guide/features/skills/?utm_source=chatgpt.com "Skills System | Hermes Agent"
[5]: https://hermes-agent.nousresearch.com/docs/developer-guide/creating-skills?utm_source=chatgpt.com "Creating Skills | Hermes Agent"
[6]: https://hermes-agent.nousresearch.com/docs/user-guide/configuration?utm_source=chatgpt.com "Hermes Agent Configuration | Hermes Agent"
[7]: https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp?utm_source=chatgpt.com "MCP (Model Context Protocol) | Hermes Agent"
[8]: https://hermes-agent.nousresearch.com/docs/user-guide/bot-mode?utm_source=chatgpt.com "Bot Mode | Hermes Agent"
[9]: https://hermes-agent.nousresearch.com/docs/developer-guide/gateway-internals/?utm_source=chatgpt.com "Gateway Internals | Hermes Agent"
[10]: https://hermes-agent.nousresearch.com/docs/guides/python-library?utm_source=chatgpt.com "Using Hermes as a Python Library | Hermes Agent"
[11]: https://hermes-agent.nousresearch.com/docs/user-guide/security?utm_source=chatgpt.com "Security | Hermes Agent"
[12]: https://hermes-agent.nousresearch.com/docs/?utm_source=chatgpt.com "Hermes Agent Documentation | Hermes Agent"
[13]: https://hermes-agent.nousresearch.com/docs/developer-guide/codebase-ownership?utm_source=chatgpt.com "Codebase Ownership Map | Hermes Agent"

