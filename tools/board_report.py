#!/usr/bin/env python3
"""Print a deterministic, read-only summary of a Hermes Kanban database."""

from __future__ import annotations

import sqlite3
import sys
from collections import defaultdict
from contextlib import closing
from pathlib import Path
from typing import Any


CANONICAL_STATUSES = (
    "triage",
    "todo",
    "scheduled",
    "ready",
    "running",
    "blocked",
    "review",
    "done",
    "archived",
)
EMPTY_REPORT = "Kanban board report\n\n(no assignees)\n"


def _bucket(value: Any, fallback: str) -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


def _identity_sort_key(identity: str) -> tuple[int, str, str]:
    return (1, "", "") if identity == "(unassigned)" else (0, identity.casefold(), identity)


def _validate_schema(connection: sqlite3.Connection) -> bool:
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    if not tables:
        return False
    required = {
        "tasks": {"id", "assignee", "status"},
        "task_runs": {"id", "task_id", "profile", "status", "started_at", "ended_at"},
    }
    missing_tables = sorted(set(required) - tables)
    if missing_tables:
        raise ValueError("database schema is missing table(s): " + ", ".join(missing_tables))
    for table, columns in required.items():
        actual = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        missing = sorted(columns - actual)
        if missing:
            raise ValueError(
                f"database schema table {table!r} is missing column(s): {', '.join(missing)}"
            )
    return True


def _report_data(connection: sqlite3.Connection) -> tuple[dict[str, dict[str, int]], dict[str, dict[str, Any]], set[str]]:
    tasks: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    statuses: set[str] = set()
    for assignee, status in connection.execute("SELECT assignee, status FROM tasks"):
        identity = _bucket(assignee, "(unassigned)")
        normalized_status = _bucket(status, "(unknown)")
        tasks[identity]["total"] += 1
        tasks[identity][normalized_status] += 1
        if normalized_status not in CANONICAL_STATUSES:
            statuses.add(normalized_status)

    runs: dict[str, dict[str, Any]] = defaultdict(lambda: {"total": 0, "ended": 0, "duration": 0})
    for profile, started_at, ended_at in connection.execute(
        "SELECT profile, started_at, ended_at FROM task_runs"
    ):
        identity = _bucket(profile, "(unassigned)")
        metrics = runs[identity]
        metrics["total"] += 1
        if ended_at is not None:
            metrics["ended"] += 1
            metrics["duration"] += max(0, int(ended_at) - int(started_at))

    return tasks, runs, statuses


def _format_report(connection: sqlite3.Connection) -> str:
    if not _validate_schema(connection):
        return EMPTY_REPORT
    tasks, runs, extra_statuses = _report_data(connection)
    identities = sorted(set(tasks) | set(runs), key=_identity_sort_key)
    if not identities:
        return EMPTY_REPORT

    statuses: list[str] = list(CANONICAL_STATUSES)
    statuses.extend(sorted(extra_statuses, key=lambda value: (value.casefold(), value)))
    sections = ["Kanban board report"]
    for identity in identities:
        task_metrics = tasks[identity]
        run_metrics = runs[identity]
        by_status = ", ".join(
            f"{status}={task_metrics.get(status, 0)}" for status in statuses
        )
        ended = run_metrics["ended"]
        average = "n/a" if not ended else f"{run_metrics['duration'] / ended:.1f}s"
        sections.extend(
            [
                "",
                f"Assignee: {identity}",
                f"  Tasks: total={task_metrics['total']}; by_status: {by_status}",
                f"  Runs: total={run_metrics['total']}; ended={ended}; average_duration={average}",
            ]
        )
    return "\n".join(sections) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: board_report.py KANBAN_DB", file=sys.stderr)
        return 2
    path = Path(argv[1]).expanduser().resolve()
    try:
        uri = path.as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            connection.execute("PRAGMA query_only = ON")
            output = _format_report(connection)
    except (OSError, sqlite3.Error, ValueError) as error:
        print(f"board_report.py: error: {error}", file=sys.stderr)
        return 1
    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
