"""CLI entry point for reflow."""

from __future__ import annotations

import logging
import sys

import click

from reflow.config import load_config


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging.")
def main(verbose: bool) -> None:
    """reflow: Auto-rescheduling task manager."""
    _setup_logging(verbose)


@main.command()
@click.option("--dry-run", is_flag=True, help="Show what would be done without making changes.")
@click.option("--overdue-only", is_flag=True, help="Only reschedule overdue tasks (legacy mode).")
def run(dry_run: bool, overdue_only: bool) -> None:
    """Schedule tasks into free calendar slots on the reflow tasks calendar."""
    from reflow.calendar_client import CalendarClient
    from reflow.parser import parse_actionable_tasks, parse_backlog
    from reflow.recurrence import find_recurring_completions
    from reflow.scheduler import reschedule_overdue, schedule_all
    from reflow.writer import append_daily_note, insert_recurring_tasks, update_backlog

    config = load_config()
    logger = logging.getLogger("reflow")

    # Parse backlog
    if not config.backlog_path.exists():
        logger.error("Backlog not found at %s", config.backlog_path)
        sys.exit(1)

    # Handle recurring tasks before scheduling
    all_tasks = parse_backlog(config.backlog_path)
    recurring = find_recurring_completions(all_tasks)

    if recurring:
        for task, next_date in recurring:
            prefix = "[DRY RUN] Would generate" if dry_run else "Generating"
            click.echo(
                f"{prefix}: {task.name} due {next_date.strftime('%b %d')}"
            )

        if not dry_run:
            count = insert_recurring_tasks(config.backlog_path, recurring)
            click.echo(f"Inserted {count} recurring task(s) into Upcoming.")

    # Parse actionable tasks (re-read after recurring inserts)
    tasks = parse_actionable_tasks(config.backlog_path)
    logger.info("Parsed %d actionable tasks from backlog", len(tasks))

    # Authenticate with Google Calendar
    cal = CalendarClient(config)
    cal.authenticate()

    # Run the scheduler
    if overdue_only:
        reschedules = reschedule_overdue(tasks, cal, config, dry_run=dry_run)
    else:
        reschedules = schedule_all(tasks, cal, config, dry_run=dry_run)

    if not reschedules:
        click.echo("No tasks to reschedule.")
        return

    # Display results
    for r in reschedules:
        prefix = "[DRY RUN] " if dry_run else ""
        click.echo(
            f"{prefix}{r.task.name}: "
            f"{r.task.deadline.strftime('%b %d')} -> {r.new_date.strftime('%b %d')} "
            f"({r.slot_start.strftime('%H:%M')}-{r.slot_end.strftime('%H:%M')})"
        )

    # Update backlog and daily note (skip in dry run)
    if not dry_run:
        updated = update_backlog(config.backlog_path, reschedules)
        click.echo(f"\nUpdated {updated} task(s) in Backlog.md")

        daily_notes_dir = config.backlog_path.parent.parent / "Daily Notes"
        if daily_notes_dir.exists():
            note_path = append_daily_note(daily_notes_dir, reschedules)
            if note_path:
                click.echo(f"Added summary to {note_path.name}")
    else:
        click.echo(f"\n{len(reschedules)} task(s) would be rescheduled.")


@main.command()
def status() -> None:
    """Show all schedulable tasks and what would be scheduled (dry run)."""
    from reflow.calendar_client import CalendarClient
    from reflow.parser import parse_actionable_tasks
    from reflow.scheduler import get_overdue_tasks, get_schedulable_tasks, schedule_all

    config = load_config()

    if not config.backlog_path.exists():
        click.echo(f"Backlog not found at {config.backlog_path}")
        sys.exit(1)

    tasks = parse_actionable_tasks(config.backlog_path)
    overdue = get_overdue_tasks(tasks)
    schedulable = get_schedulable_tasks(tasks)

    if not schedulable:
        click.echo("No tasks to schedule.")
        return

    if overdue:
        click.echo(f"Overdue: {len(overdue)} task(s)")
        for t in overdue:
            click.echo(f"  - {t.name} (due {t.deadline.strftime('%b %d')}, {t.estimate_mins}m)")
        click.echo()

    upcoming = [t for t in schedulable if t not in overdue]
    if upcoming:
        click.echo(f"Upcoming: {len(upcoming)} task(s)")
        for t in upcoming:
            click.echo(f"  - {t.name} (due {t.deadline.strftime('%b %d')}, {t.estimate_mins}m)")
        click.echo()

    click.echo("Connecting to Google Calendar for slot availability...")

    cal = CalendarClient(config)
    cal.authenticate()

    reschedules = schedule_all(tasks, cal, config, dry_run=True)

    if reschedules:
        click.echo(f"\nProposed schedule:\n")
        for r in reschedules:
            click.echo(
                f"  - {r.task.name}: {r.new_date.strftime('%b %d')} "
                f"({r.slot_start.strftime('%H:%M')}-{r.slot_end.strftime('%H:%M')})"
            )
    else:
        click.echo("\nNo slots available for scheduling in the next "
                    f"{config.lookahead_days} working days.")


@main.command()
def auth() -> None:
    """Run the Google OAuth setup flow."""
    from reflow.calendar_client import CalendarClient

    config = load_config()

    if not config.credentials_path.exists():
        click.echo(
            f"credentials.json not found at {config.credentials_path}\n\n"
            "To set up Google Calendar access:\n"
            "1. Go to https://console.cloud.google.com\n"
            "2. Create a project called 'reflow'\n"
            "3. Enable the Google Calendar API\n"
            "4. Create OAuth 2.0 credentials (Desktop app)\n"
            f"5. Download credentials.json to {config.credentials_path}\n"
            "6. Run 'reflow auth' again"
        )
        sys.exit(1)

    cal = CalendarClient(config)
    cal.authenticate()
    click.echo(f"Authenticated successfully. Token saved to {config.token_path}")


if __name__ == "__main__":
    main()
