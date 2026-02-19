"""Update Backlog.md with new task dates."""

from __future__ import annotations

import logging
import re
import tempfile
from datetime import date
from pathlib import Path

from reflow.parser import Task
from reflow.scheduler import Reschedule

logger = logging.getLogger(__name__)

# Maps date to the section it should live in
_WEEK_SECTIONS = {"Overdue", "Due This Week"}
_THEMED_SECTIONS = {"Personal", "Research", "Writing", "Admin"}

# Month abbreviations for formatting
_MONTH_ABBR = [
    "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


def _format_date(d: date) -> str:
    """Format a date as 'Feb 20', 'Mar 5' etc."""
    return f"{_MONTH_ABBR[d.month]} {d.day}"


def _target_section(new_date: date, task: Task) -> str | None:
    """Determine which section a task should move to based on its new date.

    Returns the target section name, or None if the task should stay put.
    """
    today = date.today()

    # Calculate end of current week (Sunday)
    days_until_sunday = 6 - today.weekday()
    end_of_week = today + __import__("datetime").timedelta(days=days_until_sunday)

    if new_date <= end_of_week:
        return "Due This Week"
    else:
        return "Upcoming"


def _replace_date_in_line(line: str, old_date: date, new_date: date) -> str:
    """Replace the date portion of a task line."""
    old_str = _format_date(old_date)
    new_str = _format_date(new_date)
    return line.replace(old_str, new_str, 1)


def update_backlog(backlog_path: Path, reschedules: list[Reschedule]) -> int:
    """Update Backlog.md with new dates for rescheduled tasks.

    Returns the number of tasks updated.
    """
    if not reschedules:
        return 0

    text = backlog_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    updated_count = 0

    # Build a map of tasks to their reschedule info
    task_map: dict[str, Reschedule] = {}
    for r in reschedules:
        task_map[r.task.raw_line] = r

    # First pass: update dates and collect lines that need to move
    lines_to_move: list[tuple[int, str, str]] = []  # (line_idx, new_line, target_section)

    for i, line in enumerate(lines):
        if line in task_map:
            r = task_map[line]
            new_line = _replace_date_in_line(line, r.task.deadline, r.new_date)
            target = _target_section(r.new_date, r.task)

            if target and target != r.task.section:
                # Mark for moving
                lines_to_move.append((i, new_line, target))
            else:
                # Just update the date in place
                lines[i] = new_line

            updated_count += 1
            logger.info(
                "Updated '%s': %s -> %s",
                r.task.name,
                _format_date(r.task.deadline),
                _format_date(r.new_date),
            )

    # Second pass: move lines to their target sections
    # Remove lines that need to move (in reverse order to preserve indices)
    for line_idx, _, _ in sorted(lines_to_move, key=lambda x: x[0], reverse=True):
        lines.pop(line_idx)

    # Insert lines into target sections
    for _, new_line, target_section in lines_to_move:
        section_header = f"## {target_section}"
        for i, line in enumerate(lines):
            if line.strip() == section_header:
                # Find the end of the section (next heading or EOF)
                insert_at = i + 1
                # Skip blank lines after the heading
                while insert_at < len(lines) and lines[insert_at].strip() == "":
                    insert_at += 1
                # Skip existing tasks to insert at the end of the section's tasks
                while insert_at < len(lines) and lines[insert_at].startswith("- ["):
                    insert_at += 1
                lines.insert(insert_at, new_line)
                break
        else:
            # Section not found, append at end
            logger.warning("Section '%s' not found, appending to end", target_section)
            lines.append(new_line)

    # Atomic write using temp file
    new_text = "\n".join(lines) + "\n"
    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        dir=backlog_path.parent,
        suffix=".tmp",
        delete=False,
        encoding="utf-8",
    )
    try:
        tmp.write(new_text)
        tmp.close()
        Path(tmp.name).replace(backlog_path)
    except Exception:
        Path(tmp.name).unlink(missing_ok=True)
        raise

    logger.info("Updated %d task(s) in %s", updated_count, backlog_path)
    return updated_count
