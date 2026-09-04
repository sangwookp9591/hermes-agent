# ADR — hermess

| # | 제목 | 상태 |
|---|---|---|
| [001](ADR-001-kanban-adoption.md) | 오케스트레이션은 Hermes Kanban을 채택한다 | Accepted |
| [002](ADR-002-coordination-boundaries.md) | Kanban / Bot / delegate_task 3계층 경계 | Accepted (실행 검증) |
| [003](ADR-003-model-routing.md) | quota-aware 라우팅을 보드 컬럼으로 표현 | Accepted (4차 개정) |
| [004](ADR-004-external-integration.md) | 외부 연동은 CLI `--json` 경유 | Accepted (실측 후 반전) |
| [005](ADR-005-operations.md) | 운영: 디스패처 · 동시성 · 체크포인트 · 권한 | Accepted |

근거가 되는 실측 기록은 [`../../hermess-design-review.md`](../../hermess-design-review.md).
재현 데이터는 [`../`](../) — `bench.json`(문제+정답), `bench-luna.csv`, `t1.csv`, `t2-*.csv`.
