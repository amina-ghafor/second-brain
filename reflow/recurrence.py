"""Recurrence logic for repeating tasks."""

from __future__ import annotations

import calendar
from datetime import date

from reflow.parser import Task

_WEEKDAY_MAP = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def next_monthly_date(current_deadline: date, day_of_month: int) -> date:
    """Compute the next month's date for a monthly recurrence.

    Clamps the day to the last day of the target month (e.g. day 31 in
    February becomes 28 or 29).
    """
    year = current_deadline.year
    month = current_deadline.month + 1
    if month > 12:
        month = 1
        year += 1
    max_day = calendar.monthrange(year, month)[1]
    clamped_day = min(day_of_month, max_day)
    return date(year, month, clamped_day)


def next_monthly_nth_weekday(current_deadline: date, nth: int, weekday: int) -> date:
    """Compute the nth occurrence of a weekday in the next month.

    If the month has fewer than ``nth`` occurrences of the weekday, the last
    occurrence is used instead.
    """
    year = current_deadline.year
    month = current_deadline.month + 1
    if month > 12:
        month = 1
        year += 1
    weeks = calendar.monthcalendar(year, month)
    occurrences = [w[weekday] for w in weeks if w[weekday] != 0]
    day = occurrences[min(nth, len(occurrences)) - 1]
    return date(year, month, day)


def find_recurring_completions(
    all_tasks: list[Task],
) -> list[tuple[Task, date]]:
    """Find completed recurring tasks that need a next occurrence.

    Scans for done tasks with a @monthly:DD recurrence marker, checks
    that no undone task with the same name already exists (dedup), and
    returns a list of (completed_task, next_date) pairs.
    """
    # Build set of undone task names for dedup
    undone_names: set[str] = set()
    for t in all_tasks:
        if not t.done:
            undone_names.add(t.name)

    results: list[tuple[Task, date]] = []

    for task in all_tasks:
        if not task.done or task.recurrence is None:
            continue

        # Parse recurrence spec
        if not task.recurrence.startswith("monthly:"):
            continue

        value = task.recurrence.split(":")[1]

        # Skip if an undone occurrence already exists
        if task.name in undone_names:
            continue

        if task.deadline is None:
            continue

        if value.isdigit():
            next_date = next_monthly_date(task.deadline, int(value))
        else:
            # Nth-weekday form, e.g. "4tue"
            try:
                nth = int(value[0])
                weekday_name = value[1:]
                weekday = _WEEKDAY_MAP[weekday_name]
            except (ValueError, KeyError, IndexError):
                continue
            next_date = next_monthly_nth_weekday(task.deadline, nth, weekday)

        results.append((task, next_date))

    return results
