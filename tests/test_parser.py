"""Tests for the Backlog.md parser."""

from datetime import date
from pathlib import Path
from textwrap import dedent

import pytest

from reflow.parser import Task, parse_actionable_tasks, parse_backlog


@pytest.fixture
def sample_backlog(tmp_path: Path) -> Path:
    content = dedent("""\
        # Backlog

        > [!success] [[Completed Tasks]] — archive of done tasks

        ## Overdue

        - [ ] Old task — Jan 10 (1h) #work

        ## Due This Week

        - [ ] Update payrise request — Feb 20 (1h) #work
        - [ ] Record demo on witness flow OGG — Feb 20 (1h) #work #product
        - [x] Already done task — Feb 19 (30m) #work
        - [ ] No estimate task — Feb 20 #work

        ## Upcoming

        - [ ] Check booking status — Feb 23 (10m) #personal
        - [ ] Improper sequencing — Mar 5 (1h) #work #product

        ## No Deadline

        - [ ] Finish The Source #personal
        - [ ] Plan India bday weekend (1h) #personal #travel

        ## Personal

        - [ ] Sort out phone bill — Feb 20 (15m) #personal
    """)
    backlog = tmp_path / "Backlog.md"
    backlog.write_text(content)
    return backlog


def test_parse_backlog_finds_all_tasks(sample_backlog: Path) -> None:
    tasks = parse_backlog(sample_backlog)
    # Should find all checkbox lines (done and not done, with and without dates)
    names = [t.name for t in tasks]
    assert "Update payrise request" in names
    assert "Already done task" in names
    assert "Finish The Source" in names
    assert "Plan India bday weekend" in names


def test_parse_backlog_sections(sample_backlog: Path) -> None:
    tasks = parse_backlog(sample_backlog)
    task_map = {t.name: t for t in tasks}

    assert task_map["Old task"].section == "Overdue"
    assert task_map["Update payrise request"].section == "Due This Week"
    assert task_map["Check booking status"].section == "Upcoming"
    assert task_map["Finish The Source"].section == "No Deadline"
    assert task_map["Sort out phone bill"].section == "Personal"


def test_parse_done_tasks(sample_backlog: Path) -> None:
    tasks = parse_backlog(sample_backlog)
    task_map = {t.name: t for t in tasks}

    assert task_map["Already done task"].done is True
    assert task_map["Update payrise request"].done is False


def test_parse_estimates(sample_backlog: Path) -> None:
    tasks = parse_backlog(sample_backlog)
    task_map = {t.name: t for t in tasks}

    assert task_map["Update payrise request"].estimate_mins == 60
    assert task_map["Check booking status"].estimate_mins == 10
    assert task_map["Sort out phone bill"].estimate_mins == 15
    assert task_map["Plan India bday weekend"].estimate_mins == 60


def test_parse_tags(sample_backlog: Path) -> None:
    tasks = parse_backlog(sample_backlog)
    task_map = {t.name: t for t in tasks}

    assert "#work" in task_map["Update payrise request"].tags
    assert "#work" in task_map["Record demo on witness flow OGG"].tags
    assert "#product" in task_map["Record demo on witness flow OGG"].tags
    assert "#personal" in task_map["Sort out phone bill"].tags


def test_parse_dates(sample_backlog: Path) -> None:
    # Pin "today" so bare dates like "Feb 20" resolve deterministically.
    tasks = parse_backlog(sample_backlog, today=date(2026, 3, 6))
    task_map = {t.name: t for t in tasks}

    assert task_map["Update payrise request"].deadline == date(2026, 2, 20)
    assert task_map["Check booking status"].deadline == date(2026, 2, 23)
    assert task_map["Improper sequencing"].deadline == date(2026, 3, 5)


def test_no_deadline_tasks(sample_backlog: Path) -> None:
    tasks = parse_backlog(sample_backlog)
    task_map = {t.name: t for t in tasks}

    assert task_map["Finish The Source"].deadline is None
    assert task_map["Finish The Source"].estimate_mins is None


def test_parse_actionable_filters_correctly(sample_backlog: Path) -> None:
    actionable = parse_actionable_tasks(sample_backlog)
    names = [t.name for t in actionable]

    # Should include: tasks with deadline AND estimate AND not done
    assert "Update payrise request" in names
    assert "Check booking status" in names

    # Should exclude: done tasks
    assert "Already done task" not in names
    # Should exclude: no estimate
    assert "No estimate task" not in names
    # Should exclude: no deadline
    assert "Finish The Source" not in names
    assert "Plan India bday weekend" not in names


def test_parse_line_numbers(sample_backlog: Path) -> None:
    tasks = parse_backlog(sample_backlog)
    # All tasks should have positive line numbers
    for task in tasks:
        assert task.line_number > 0


def test_parse_raw_line_preserved(sample_backlog: Path) -> None:
    tasks = parse_backlog(sample_backlog)
    for task in tasks:
        assert task.raw_line.startswith("- [")


def test_parse_multi_hour_estimate(tmp_path: Path) -> None:
    content = "## Work\n\n- [ ] Big task — Feb 20 (2h) #work\n- [ ] Half task — Feb 20 (1.5h) #work\n"
    backlog = tmp_path / "Backlog.md"
    backlog.write_text(content)

    tasks = parse_backlog(backlog)
    task_map = {t.name: t for t in tasks}

    assert task_map["Big task"].estimate_mins == 120
    assert task_map["Half task"].estimate_mins == 90


def test_parse_recurrence_monthly(tmp_path: Path) -> None:
    content = "## Work\n\n- [ ] Do monthly invoice — Feb 18 (30m) #work @monthly:18\n"
    backlog = tmp_path / "Backlog.md"
    backlog.write_text(content)

    tasks = parse_backlog(backlog)
    assert len(tasks) == 1
    assert tasks[0].recurrence == "monthly:18"
    assert tasks[0].name == "Do monthly invoice"
    assert tasks[0].tags == ["#work"]


def test_parse_recurrence_absent(tmp_path: Path) -> None:
    content = "## Work\n\n- [ ] Regular task — Feb 20 (1h) #work\n"
    backlog = tmp_path / "Backlog.md"
    backlog.write_text(content)

    tasks = parse_backlog(backlog)
    assert len(tasks) == 1
    assert tasks[0].recurrence is None


def test_parse_done_with_recurrence(tmp_path: Path) -> None:
    content = "## Work\n\n- [x] Do monthly invoice — Feb 18 (30m) #work @monthly:18\n"
    backlog = tmp_path / "Backlog.md"
    backlog.write_text(content)

    tasks = parse_backlog(backlog)
    assert len(tasks) == 1
    assert tasks[0].done is True
    assert tasks[0].recurrence == "monthly:18"
