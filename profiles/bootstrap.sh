#!/usr/bin/env bash
# ADR-002 프로필 로스터를 HERMES_HOME에 설치한다.
#
#   HERMES_HOME=~/.hermes-poc ./profiles/bootstrap.sh
#
# 멱등이다. 기존 config.yaml / SOUL.md는 덮어쓴다 (이 리포가 SSOT).
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
HERMES_BIN="${HERMES_BIN:-uv run python -m hermes_cli.main}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "HERMES_HOME = $HERMES_HOME"

for dir in "$SRC"/*/; do
  name="$(basename "$dir")"
  [ -f "$dir/config.yaml" ] || continue

  if [ ! -d "$HERMES_HOME/profiles/$name" ]; then
    echo "  + 프로필 생성: $name"
    $HERMES_BIN profile create "$name" >/dev/null 2>&1 || true
  fi

  mkdir -p "$HERMES_HOME/profiles/$name"
  cp "$dir/config.yaml" "$HERMES_HOME/profiles/$name/config.yaml"
  [ -f "$dir/SOUL.md" ] && cp "$dir/SOUL.md" "$HERMES_HOME/profiles/$name/SOUL.md"
  echo "  ✓ $name"
done

echo
echo "보드 초기화..."
$HERMES_BIN kanban init >/dev/null 2>&1 || true

echo
echo "완료. 검증:"
echo "  $HERMES_BIN -p orchestrator chat -q \"List the exact names of every tool you have.\""
echo "  → kanban_* 가 보이고 terminal/file 이 없어야 정상 (ADR-002)"
