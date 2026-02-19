"""CLI entry point for motion-cli."""

from __future__ import annotations

import logging
import sys

import click

from motion_cli.config import load_config


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
    """motion-cli: Auto-rescheduling task manager."""
    _setup_logging(verbose)


@main.command()
@click.option("--dry-run", is_flag=True, help="Show what would be done without making changes.")
def run(dry_run: bool) -> None:
    """Detect overdue tasks and reschedule them into free calendar slots."""
    from motion_cli.calendar_client import CalendarClient
    from motion_cli.parser import parse_actionable_tasks
    from motion_cli.scheduler import reschedule_overdue
    from motion_cli.writer import update_backlog

    config = load_config()
    logger = logging.getLogger("motion")

    # Parse backlog
    if not config.backlog_path.exists():
        logger.error("Backlog not found at %s", config.backlog_path)
        sys.exit(1)

    tasks = parse_actionable_tasks(config.backlog_path)
    logger.info("Parsed %d actionable tasks from backlog", len(tasks))

    # Authenticate with Google Calendar
    cal = CalendarClient(config)
    cal.authenticate()

    # Run the scheduler
    reschedules = reschedule_overdue(tasks, cal, config, dry_run=dry_run)

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

    # Update backlog (skip in dry run)
    if not dry_run:
        updated = update_backlog(config.backlog_path, reschedules)
        click.echo(f"\nUpdated {updated} task(s) in Backlog.md")
    else:
        click.echo(f"\n{len(reschedules)} task(s) would be rescheduled.")


@main.command()
def status() -> None:
    """Show overdue tasks and what would be rescheduled (dry run)."""
    from motion_cli.calendar_client import CalendarClient
    from motion_cli.parser import parse_actionable_tasks
    from motion_cli.scheduler import get_overdue_tasks, reschedule_overdue

    config = load_config()

    if not config.backlog_path.exists():
        click.echo(f"Backlog not found at {config.backlog_path}")
        sys.exit(1)

    tasks = parse_actionable_tasks(config.backlog_path)
    overdue = get_overdue_tasks(tasks)

    if not overdue:
        click.echo("No overdue tasks.")
        return

    click.echo(f"Found {len(overdue)} overdue task(s):\n")
    for t in overdue:
        click.echo(f"  - {t.name} (due {t.deadline.strftime('%b %d')}, {t.estimate_mins}m)")

    click.echo("\nConnecting to Google Calendar for slot availability...")

    cal = CalendarClient(config)
    cal.authenticate()

    reschedules = reschedule_overdue(tasks, cal, config, dry_run=True)

    if reschedules:
        click.echo(f"\nProposed reschedules:\n")
        for r in reschedules:
            click.echo(
                f"  - {r.task.name}: {r.new_date.strftime('%b %d')} "
                f"({r.slot_start.strftime('%H:%M')}-{r.slot_end.strftime('%H:%M')})"
            )
    else:
        click.echo("\nNo slots available for rescheduling in the next "
                    f"{config.lookahead_days} working days.")


@main.command()
def auth() -> None:
    """Run the Google OAuth setup flow."""
    from motion_cli.calendar_client import CalendarClient

    config = load_config()

    if not config.credentials_path.exists():
        click.echo(
            f"credentials.json not found at {config.credentials_path}\n\n"
            "To set up Google Calendar access:\n"
            "1. Go to https://console.cloud.google.com\n"
            "2. Create a project called 'motion-cli'\n"
            "3. Enable the Google Calendar API\n"
            "4. Create OAuth 2.0 credentials (Desktop app)\n"
            f"5. Download credentials.json to {config.credentials_path}\n"
            "6. Run 'motion auth' again"
        )
        sys.exit(1)

    cal = CalendarClient(config)
    cal.authenticate()
    click.echo(f"Authenticated successfully. Token saved to {config.token_path}")


if __name__ == "__main__":
    main()
