"""Parse Backlog.md into Task objects."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from dateutil import parser as dateutil_parser


@dataclass
class Task:
    raw_line: str
    name: str
    done: bool
    deadline: date | None
    estimate_mins: int | None
    tags: list[str] = field(default_factory=list)
    section: str = ""
    line_number: int = 0
    recurrence: str | None = None


# Matches: - [ ] Name — Date (estimate) #tag1 #tag2
# Also handles: - [x] for done tasks
_TASK_RE = re.compile(
    r"^- \[([ x])\] "       # checkbox
    r"(.+?)"                 # task name (non-greedy)
    r"(?:\s*—\s*"            # optional em-dash separator
    r"([A-Z][a-z]+ \d+)"    # date like "Feb 20" or "Mar 5"
    r")?"
    r"(?:\s*\((\d+\.?\d*[mh])\))?"  # optional estimate like (1h), (30m), (1.5h)
    r"((?:\s+#\w+)*)"       # optional tags
    r"(?:\s+@(\w+:\w+))?"   # optional recurrence like @monthly:18
    r"\s*$"
)


def _parse_date(date_str: str, today: date | None = None) -> date | None:
    """Parse 'Feb 20', 'Mar 5' etc. into a date object.

    Assumes the current year, rolling forward if the date appears to be
    in the distant past (i.e. more than 6 months ago). ``today`` can be
    passed in for deterministic tests; it defaults to the system date.
    """
    if not date_str:
        return None
    try:
        parsed = dateutil_parser.parse(date_str, fuzzy=False)
        today = today or date.today()
        result = parsed.date().replace(year=today.year)
        # If the parsed date is more than 6 months in the past,
        # assume it means next year
        if (today - result).days > 180:
            result = result.replace(year=today.year + 1)
        return result
    except (ValueError, OverflowError):
        return None


def _parse_estimate(est_str: str) -> int | None:
    """Parse '1h', '30m', '1.5h' into minutes."""
    if not est_str:
        return None
    if est_str.endswith("h"):
        return int(float(est_str[:-1]) * 60)
    if est_str.endswith("m"):
        return int(float(est_str[:-1]))
    return None


def _parse_tags(tag_str: str) -> list[str]:
    """Extract #tags from a string."""
    return re.findall(r"#\w+", tag_str)


def parse_backlog(backlog_path: Path, today: date | None = None) -> list[Task]:
    """Parse a Backlog.md file and return a list of Task objects.

    Skips tasks that are done, have no deadline, or have no estimate.
    ``today`` is used to resolve bare dates like "Feb 20" to a year and
    defaults to the system date.
    """
    text = backlog_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    tasks: list[Task] = []
    current_section = ""

    for i, line in enumerate(lines, start=1):
        # Track section headings
        if line.startswith("## "):
            current_section = line[3:].strip()
            continue

        match = _TASK_RE.match(line)
        if not match:
            continue

        checkbox, name, date_str, est_str, tag_str, recurrence_str = match.groups()
        done = checkbox == "x"
        deadline = _parse_date(date_str or "", today)
        estimate = _parse_estimate(est_str or "")
        tags = _parse_tags(tag_str or "")

        task = Task(
            raw_line=line,
            name=name.strip(),
            done=done,
            deadline=deadline,
            estimate_mins=estimate,
            tags=tags,
            section=current_section,
            line_number=i,
            recurrence=recurrence_str,
        )
        tasks.append(task)

    return tasks


def parse_actionable_tasks(backlog_path: Path, today: date | None = None) -> list[Task]:
    """Parse backlog and return only actionable tasks (not done, has deadline and estimate)."""
    return [
        t for t in parse_backlog(backlog_path, today)
        if not t.done and t.deadline is not None and t.estimate_mins is not None
    ]
