"""Core rescheduling logic: find free slots, assign overdue tasks."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from motion_cli.calendar_client import CalendarClient
from motion_cli.config import Config
from motion_cli.parser import Task

logger = logging.getLogger(__name__)

# Section priority order (lower = higher priority)
SECTION_PRIORITY = {
    "Overdue": 0,
    "Due This Week": 1,
    "Personal": 2,
    "Research": 3,
    "Admin": 4,
    "Writing": 5,
    "Upcoming": 6,
}


@dataclass
class Reschedule:
    task: Task
    new_date: date
    slot_start: datetime
    slot_end: datetime


def _is_weekday(d: date) -> bool:
    return d.weekday() < 5  # Mon=0 .. Fri=4


def _next_weekdays(start: date, count: int) -> list[date]:
    """Return the next `count` weekdays starting from `start` (inclusive if weekday)."""
    days: list[date] = []
    current = start
    while len(days) < count:
        if _is_weekday(current):
            days.append(current)
        current += timedelta(days=1)
    return days


def get_overdue_tasks(tasks: list[Task], today: date | None = None) -> list[Task]:
    """Filter and sort tasks that are overdue."""
    today = today or date.today()

    overdue = [
        t for t in tasks
        if not t.done
        and t.deadline is not None
        and t.estimate_mins is not None
        and t.deadline < today
    ]

    # Sort by deadline (oldest first), then by section priority
    overdue.sort(key=lambda t: (
        t.deadline,
        SECTION_PRIORITY.get(t.section, 99),
    ))

    return overdue


def find_slot_for_task(
    task: Task,
    calendar_client: CalendarClient,
    config: Config,
    today: date | None = None,
) -> tuple[date, datetime, datetime] | None:
    """Find the earliest free slot that fits the task.

    Returns (date, slot_start, slot_end) or None if no slot found.
    """
    today = today or date.today()
    days_to_check = _next_weekdays(today, config.lookahead_days)
    duration = timedelta(minutes=task.estimate_mins)

    for day in days_to_check:
        free_slots = calendar_client.get_free_slots(day)
        for slot_start, slot_end in free_slots:
            if slot_end - slot_start >= duration:
                return (day, slot_start, slot_start + duration)

    return None


def reschedule_overdue(
    tasks: list[Task],
    calendar_client: CalendarClient,
    config: Config,
    dry_run: bool = False,
) -> list[Reschedule]:
    """Main scheduling function: find overdue tasks and reschedule them.

    Returns a list of Reschedule actions taken (or that would be taken if dry_run).
    """
    today = date.today()
    overdue = get_overdue_tasks(tasks, today)

    if not overdue:
        logger.info("No overdue tasks found")
        return []

    logger.info("Found %d overdue task(s)", len(overdue))
    reschedules: list[Reschedule] = []

    for task in overdue:
        # Idempotency check: skip if a [Motion] event already exists
        if not dry_run:
            existing = calendar_client.find_task_event(task.name, today)
            if existing:
                logger.info("Skipping '%s': already has a [Motion] event", task.name)
                continue

        # Find a free slot
        result = find_slot_for_task(task, calendar_client, config, today)
        if result is None:
            logger.warning(
                "No free slot found for '%s' (%d min) in the next %d working days",
                task.name, task.estimate_mins, config.lookahead_days,
            )
            continue

        new_date, slot_start, slot_end = result
        action = Reschedule(
            task=task,
            new_date=new_date,
            slot_start=slot_start,
            slot_end=slot_end,
        )
        reschedules.append(action)

        if not dry_run:
            calendar_client.create_task_event(task.name, slot_start, slot_end)
            logger.info(
                "Scheduled '%s' for %s %s-%s",
                task.name,
                new_date,
                slot_start.strftime("%H:%M"),
                slot_end.strftime("%H:%M"),
            )

    return reschedules
