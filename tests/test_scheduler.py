"""Tests for the scheduler module."""

from datetime import date, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from motion_cli.config import Config
from motion_cli.parser import Task
from motion_cli.scheduler import (
    Reschedule,
    find_slot_for_task,
    get_overdue_tasks,
    reschedule_overdue,
)


def _make_task(
    name: str = "Test task",
    deadline: date | None = None,
    estimate_mins: int = 60,
    done: bool = False,
    section: str = "Due This Week",
) -> Task:
    deadline = deadline or date(2026, 2, 18)  # a Wednesday
    return Task(
        raw_line=f"- [ ] {name} — Feb 18 ({estimate_mins}m) #work",
        name=name,
        done=done,
        deadline=deadline,
        estimate_mins=estimate_mins,
        tags=["#work"],
        section=section,
        line_number=1,
    )


def _make_config(**overrides) -> Config:
    defaults = {
        "working_hours_start": 11,
        "working_hours_end": 19,
        "lunch_start": 13,
        "lunch_end": 14,
        "lookahead_days": 5,
        "timezone": "Europe/Madrid",
    }
    defaults.update(overrides)

    config = MagicMock(spec=Config)
    for k, v in defaults.items():
        setattr(config, k, v)
    return config


class TestGetOverdueTasks:
    def test_identifies_overdue(self) -> None:
        today = date(2026, 2, 19)
        tasks = [
            _make_task("Past", deadline=date(2026, 2, 18)),
            _make_task("Today", deadline=date(2026, 2, 19)),
            _make_task("Future", deadline=date(2026, 2, 25)),
        ]
        overdue = get_overdue_tasks(tasks, today)
        assert len(overdue) == 1
        assert overdue[0].name == "Past"

    def test_excludes_done(self) -> None:
        today = date(2026, 2, 19)
        tasks = [_make_task("Done", deadline=date(2026, 2, 18), done=True)]
        assert get_overdue_tasks(tasks, today) == []

    def test_excludes_no_deadline(self) -> None:
        today = date(2026, 2, 19)
        task = _make_task("No deadline")
        task.deadline = None
        assert get_overdue_tasks([task], today) == []

    def test_excludes_no_estimate(self) -> None:
        today = date(2026, 2, 19)
        task = _make_task("No estimate", deadline=date(2026, 2, 18))
        task.estimate_mins = None
        assert get_overdue_tasks([task], today) == []

    def test_sorts_by_deadline_then_section(self) -> None:
        today = date(2026, 2, 19)
        tasks = [
            _make_task("B", deadline=date(2026, 2, 17), section="Due This Week"),
            _make_task("A", deadline=date(2026, 2, 16), section="Overdue"),
            _make_task("C", deadline=date(2026, 2, 17), section="Overdue"),
        ]
        overdue = get_overdue_tasks(tasks, today)
        assert [t.name for t in overdue] == ["A", "C", "B"]


class TestFindSlotForTask:
    def test_finds_morning_slot(self) -> None:
        """Task fits in the morning block (11:00-13:00)."""
        import pytz

        tz = pytz.timezone("Europe/Madrid")
        today = date(2026, 2, 19)
        task = _make_task("Morning task", estimate_mins=60)
        config = _make_config()

        cal = MagicMock()
        # Return a free morning and afternoon (no events)
        cal.get_free_slots.return_value = [
            (
                tz.localize(datetime(2026, 2, 19, 11, 0)),
                tz.localize(datetime(2026, 2, 19, 13, 0)),
            ),
            (
                tz.localize(datetime(2026, 2, 19, 14, 0)),
                tz.localize(datetime(2026, 2, 19, 19, 0)),
            ),
        ]

        result = find_slot_for_task(task, cal, config, today)
        assert result is not None
        d, start, end = result
        assert d == today
        assert start.hour == 11
        assert end.hour == 12

    def test_skips_to_next_day_if_full(self) -> None:
        """If today is full, find a slot tomorrow."""
        import pytz

        tz = pytz.timezone("Europe/Madrid")
        today = date(2026, 2, 19)  # Thursday
        task = _make_task("Big task", estimate_mins=60)
        config = _make_config()

        cal = MagicMock()
        # Day 1: only a 30-min slot (too small)
        # Day 2: full morning and afternoon free
        cal.get_free_slots.side_effect = [
            [
                (
                    tz.localize(datetime(2026, 2, 19, 11, 0)),
                    tz.localize(datetime(2026, 2, 19, 11, 30)),
                ),
            ],
            [
                (
                    tz.localize(datetime(2026, 2, 20, 11, 0)),
                    tz.localize(datetime(2026, 2, 20, 13, 0)),
                ),
                (
                    tz.localize(datetime(2026, 2, 20, 14, 0)),
                    tz.localize(datetime(2026, 2, 20, 19, 0)),
                ),
            ],
        ]

        result = find_slot_for_task(task, cal, config, today)
        assert result is not None
        d, start, end = result
        assert d == date(2026, 2, 20)

    def test_returns_none_if_no_slots(self) -> None:
        """No slots available in the lookahead window."""
        today = date(2026, 2, 19)
        task = _make_task("Huge task", estimate_mins=480)  # 8 hours
        config = _make_config(lookahead_days=2)

        cal = MagicMock()
        cal.get_free_slots.return_value = []  # No free slots

        result = find_slot_for_task(task, cal, config, today)
        assert result is None


class TestRescheduleOverdue:
    def test_dry_run_does_not_create_events(self) -> None:
        import pytz

        tz = pytz.timezone("Europe/Madrid")
        today = date(2026, 2, 19)
        task = _make_task("Overdue task", deadline=date(2026, 2, 18))
        config = _make_config()

        cal = MagicMock()
        cal.get_free_slots.return_value = [
            (
                tz.localize(datetime(2026, 2, 19, 11, 0)),
                tz.localize(datetime(2026, 2, 19, 13, 0)),
            ),
        ]

        # Patch date.today
        import motion_cli.scheduler as sched
        original_get_overdue = sched.get_overdue_tasks

        reschedules = reschedule_overdue([task], cal, config, dry_run=True)

        assert len(reschedules) == 1
        assert reschedules[0].task.name == "Overdue task"
        # Should NOT have called create_task_event or find_task_event
        cal.create_task_event.assert_not_called()
        cal.find_task_event.assert_not_called()

    def test_skips_existing_motion_event(self) -> None:
        import pytz

        tz = pytz.timezone("Europe/Madrid")
        task = _make_task("Already scheduled", deadline=date(2026, 2, 18))
        config = _make_config()

        cal = MagicMock()
        cal.find_task_event.return_value = {"summary": "[Motion] Already scheduled"}
        cal.get_free_slots.return_value = [
            (
                tz.localize(datetime(2026, 2, 19, 11, 0)),
                tz.localize(datetime(2026, 2, 19, 13, 0)),
            ),
        ]

        reschedules = reschedule_overdue([task], cal, config, dry_run=False)
        assert len(reschedules) == 0
