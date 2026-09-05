"""Tests for the scheduler module."""

from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from reflow.config import Config
from reflow.parser import Task
from reflow.scheduler import (
    Reschedule,
    find_slot_for_task,
    get_overdue_tasks,
    get_schedulable_tasks,
    reschedule_overdue,
    schedule_all,
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
        "timezone": "Europe/London",
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

        tz = pytz.timezone("Europe/London")
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

        tz = pytz.timezone("Europe/London")
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

        tz = pytz.timezone("Europe/London")
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
        import reflow.scheduler as sched
        original_get_overdue = sched.get_overdue_tasks

        reschedules = reschedule_overdue([task], cal, config, dry_run=True)

        assert len(reschedules) == 1
        assert reschedules[0].task.name == "Overdue task"
        # Should NOT have called create_task_event or find_task_event
        cal.create_task_event.assert_not_called()
        cal.find_task_event.assert_not_called()

    def test_skips_existing_reflow_event(self) -> None:
        import pytz

        tz = pytz.timezone("Europe/London")
        task = _make_task("Already scheduled", deadline=date(2026, 2, 18))
        config = _make_config()

        cal = MagicMock()
        cal.find_task_event.return_value = {
            "summary": "Already scheduled",
            "description": "reflow:managed | From Backlog.md",
        }
        cal.get_free_slots.return_value = [
            (
                tz.localize(datetime(2026, 2, 19, 11, 0)),
                tz.localize(datetime(2026, 2, 19, 13, 0)),
            ),
        ]

        reschedules = reschedule_overdue([task], cal, config, dry_run=False)
        assert len(reschedules) == 0


class TestGetSchedulableTasks:
    def test_includes_overdue_and_upcoming(self) -> None:
        today = date(2026, 2, 19)
        tasks = [
            _make_task("Overdue", deadline=date(2026, 2, 18)),
            _make_task("Today", deadline=date(2026, 2, 19)),
            _make_task("Tomorrow", deadline=date(2026, 2, 20)),
            _make_task("Far future", deadline=date(2026, 4, 1)),
        ]
        schedulable = get_schedulable_tasks(tasks, today)
        assert len(schedulable) == 3
        assert [t.name for t in schedulable] == ["Overdue", "Today", "Tomorrow"]

    def test_excludes_done_and_missing_fields(self) -> None:
        today = date(2026, 2, 19)
        done_task = _make_task("Done", deadline=date(2026, 2, 20), done=True)
        no_deadline = _make_task("No deadline")
        no_deadline.deadline = None
        no_estimate = _make_task("No estimate", deadline=date(2026, 2, 20))
        no_estimate.estimate_mins = None
        assert get_schedulable_tasks([done_task, no_deadline, no_estimate], today) == []


class TestFreeSlotsSkipsPastTime:
    def test_today_excludes_past_slots(self) -> None:
        """Free slots before the current time should not be returned."""
        import pytz

        from reflow.calendar_client import CalendarClient

        tz = pytz.timezone("Europe/London")
        today = date(2026, 2, 20)
        config = _make_config()
        config.calendar_id = "primary"
        config.reflow_calendar_id = "primary"
        config.token_path = MagicMock()

        cal = CalendarClient.__new__(CalendarClient)
        cal.config = config
        cal._service = MagicMock()

        # No events - whole day is free in theory
        cal._service.events.return_value.list.return_value.execute.return_value = {
            "items": [],
            "nextPageToken": None,
        }

        # Freeze "now" to 15:00 London time
        fake_now = tz.localize(datetime(2026, 2, 20, 15, 0))
        with patch("reflow.calendar_client.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.combine = datetime.combine
            mock_dt.fromisoformat = datetime.fromisoformat
            slots = cal.get_free_slots(today)

        # All slots should start at or after 15:00
        for slot_start, slot_end in slots:
            assert slot_start >= fake_now, (
                f"Slot {slot_start} is before current time {fake_now}"
            )

    def test_future_date_includes_full_day(self) -> None:
        """Free slots for a future date should include the full working day."""
        import pytz

        from reflow.calendar_client import CalendarClient

        tz = pytz.timezone("Europe/London")
        future = date(2026, 2, 21)
        config = _make_config()
        config.calendar_id = "primary"
        config.reflow_calendar_id = "primary"
        config.token_path = MagicMock()

        cal = CalendarClient.__new__(CalendarClient)
        cal.config = config
        cal._service = MagicMock()

        cal._service.events.return_value.list.return_value.execute.return_value = {
            "items": [],
            "nextPageToken": None,
        }

        # Even though "now" is 15:00 today, future date should have full slots
        fake_now = tz.localize(datetime(2026, 2, 20, 15, 0))
        with patch("reflow.calendar_client.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.combine = datetime.combine
            mock_dt.fromisoformat = datetime.fromisoformat
            slots = cal.get_free_slots(future)

        # First slot should start at 11:00 (work_start)
        assert slots[0][0].hour == 11


class TestScheduleAll:
    def test_schedules_upcoming_tasks(self) -> None:
        import pytz

        tz = pytz.timezone("Europe/London")
        today = date(2026, 2, 19)
        task = _make_task("Tomorrow task", deadline=date(2026, 2, 20), estimate_mins=60)
        config = _make_config()

        cal = MagicMock()
        cal.find_task_event.return_value = None
        cal.get_free_slots.return_value = [
            (
                tz.localize(datetime(2026, 2, 20, 11, 0)),
                tz.localize(datetime(2026, 2, 20, 13, 0)),
            ),
        ]

        reschedules = schedule_all([task], cal, config, dry_run=False)
        assert len(reschedules) == 1
        assert reschedules[0].task.name == "Tomorrow task"
        assert reschedules[0].new_date == date(2026, 2, 20)
        cal.create_task_event.assert_called_once()
