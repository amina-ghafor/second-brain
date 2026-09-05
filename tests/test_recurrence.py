"""Tests for recurring task logic."""

from datetime import date
from pathlib import Path
from textwrap import dedent

import pytest

from reflow.parser import Task, parse_backlog
from reflow.recurrence import (
    find_recurring_completions,
    next_monthly_date,
    next_monthly_nth_weekday,
)


class TestNextMonthlyDate:
    def test_basic_next_month(self) -> None:
        assert next_monthly_date(date(2026, 2, 18), 18) == date(2026, 3, 18)

    def test_december_rolls_to_january(self) -> None:
        assert next_monthly_date(date(2026, 12, 15), 15) == date(2027, 1, 15)

    def test_day_clamped_to_feb_28(self) -> None:
        assert next_monthly_date(date(2026, 1, 31), 31) == date(2026, 2, 28)

    def test_day_clamped_to_feb_29_leap_year(self) -> None:
        assert next_monthly_date(date(2027, 1, 30), 30) == date(2027, 2, 28)
        assert next_monthly_date(date(2023, 1, 29), 29) == date(2023, 2, 28)
        assert next_monthly_date(date(2024, 1, 29), 29) == date(2024, 2, 29)

    def test_day_clamped_to_april_30(self) -> None:
        assert next_monthly_date(date(2026, 3, 31), 31) == date(2026, 4, 30)

    def test_day_smaller_than_month_max(self) -> None:
        assert next_monthly_date(date(2026, 3, 5), 5) == date(2026, 4, 5)


class TestNextMonthlyNthWeekday:
    def test_basic_4th_tuesday(self) -> None:
        # 4th Tuesday of March 2026 is March 24
        assert next_monthly_nth_weekday(date(2026, 2, 24), 4, 1) == date(2026, 3, 24)

    def test_december_rolls_to_january(self) -> None:
        # 4th Tuesday of January 2027 is January 26
        assert next_monthly_nth_weekday(date(2026, 12, 22), 4, 1) == date(2027, 1, 26)

    def test_5th_weekday_falls_back_to_last(self) -> None:
        # April 2026 has 4 Tuesdays (7, 14, 21, 28), so 5th falls back to last
        assert next_monthly_nth_weekday(date(2026, 3, 24), 5, 1) == date(2026, 4, 28)

    def test_1st_monday(self) -> None:
        # 1st Monday of March 2026 is March 2
        assert next_monthly_nth_weekday(date(2026, 2, 2), 1, 0) == date(2026, 3, 2)


class TestFindRecurringCompletions:
    def _make_task(
        self,
        name: str,
        done: bool,
        deadline: date | None = None,
        recurrence: str | None = None,
    ) -> Task:
        return Task(
            raw_line=f"- [{'x' if done else ' '}] {name}",
            name=name,
            done=done,
            deadline=deadline,
            estimate_mins=60,
            recurrence=recurrence,
        )

    def test_finds_completed_recurring(self) -> None:
        tasks = [
            self._make_task("Invoice", True, date(2026, 2, 18), "monthly:18"),
        ]
        results = find_recurring_completions(tasks)
        assert len(results) == 1
        assert results[0][0].name == "Invoice"
        assert results[0][1] == date(2026, 3, 18)

    def test_skips_incomplete_task(self) -> None:
        tasks = [
            self._make_task("Invoice", False, date(2026, 2, 18), "monthly:18"),
        ]
        assert find_recurring_completions(tasks) == []

    def test_skips_task_without_recurrence(self) -> None:
        tasks = [
            self._make_task("Invoice", True, date(2026, 2, 18), None),
        ]
        assert find_recurring_completions(tasks) == []

    def test_dedup_skips_if_undone_exists(self) -> None:
        tasks = [
            self._make_task("Invoice", True, date(2026, 2, 18), "monthly:18"),
            self._make_task("Invoice", False, date(2026, 3, 18), "monthly:18"),
        ]
        assert find_recurring_completions(tasks) == []

    def test_skips_task_without_deadline(self) -> None:
        tasks = [
            self._make_task("Invoice", True, None, "monthly:18"),
        ]
        assert find_recurring_completions(tasks) == []

    def test_december_rollover(self) -> None:
        tasks = [
            self._make_task("Invoice", True, date(2026, 12, 18), "monthly:18"),
        ]
        results = find_recurring_completions(tasks)
        assert results[0][1] == date(2027, 1, 18)

    def test_nth_weekday_recurrence(self) -> None:
        tasks = [
            self._make_task("Funding prep", True, date(2026, 2, 24), "monthly:4tue"),
        ]
        results = find_recurring_completions(tasks)
        assert len(results) == 1
        assert results[0][1] == date(2026, 3, 24)

    def test_nth_weekday_invalid_day_name_skipped(self) -> None:
        tasks = [
            self._make_task("Bad", True, date(2026, 2, 24), "monthly:4xyz"),
        ]
        assert find_recurring_completions(tasks) == []


class TestRecurrenceIntegration:
    def test_parse_and_find_recurring(self, tmp_path: Path) -> None:
        content = dedent("""\
            ## Due This Week

            - [x] Do monthly invoice — Feb 18 (30m) #work @monthly:18

            ## Upcoming

            - [ ] Check booking status — Feb 23 (10m) #personal
        """)
        backlog = tmp_path / "Backlog.md"
        backlog.write_text(content)

        all_tasks = parse_backlog(backlog, today=date(2026, 2, 20))
        recurring = find_recurring_completions(all_tasks)

        assert len(recurring) == 1
        task, next_date = recurring[0]
        assert task.name == "Do monthly invoice"
        assert next_date == date(2026, 3, 18)

    def test_parse_nth_weekday_recurring(self, tmp_path: Path) -> None:
        content = dedent("""\
            ## Due This Week

            - [x] Prep monthly report \u2014 Feb 24 (1h) #work @monthly:4tue

            ## Upcoming

            - [ ] Check booking status \u2014 Feb 23 (10m) #personal
        """)
        backlog = tmp_path / "Backlog.md"
        backlog.write_text(content)

        all_tasks = parse_backlog(backlog, today=date(2026, 2, 20))
        recurring = find_recurring_completions(all_tasks)

        assert len(recurring) == 1
        task, next_date = recurring[0]
        assert task.name == "Prep monthly report"
        assert next_date == date(2026, 3, 24)

    def test_idempotent_when_undone_exists(self, tmp_path: Path) -> None:
        content = dedent("""\
            ## Due This Week

            - [x] Do monthly invoice — Feb 18 (30m) #work @monthly:18

            ## Upcoming

            - [ ] Do monthly invoice — Mar 18 (30m) #work @monthly:18
        """)
        backlog = tmp_path / "Backlog.md"
        backlog.write_text(content)

        all_tasks = parse_backlog(backlog)
        recurring = find_recurring_completions(all_tasks)

        assert len(recurring) == 0
