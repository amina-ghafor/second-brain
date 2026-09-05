# Reflow

Auto-rescheduling task manager. Reads Obsidian Backlog.md, finds free Google Calendar slots, creates events, and updates task dates.

## Architecture

```
cli.py              → Click CLI (run, status, auth commands)
config.py           → .env loading, Config dataclass
parser.py           → Backlog.md → Task dataclasses (regex-based)
scheduler.py        → Core logic: find slots, schedule tasks, idempotency
calendar_client.py  → Google Calendar API wrapper (OAuth, events, free slots)
writer.py           → Updates Backlog.md dates + appends to daily notes
```

**Data flow:** `parse tasks → authenticate → find free slots → create events → update files`

## Writing style

- Never use em dashes. Use hyphens or rewrite the sentence.

## Key conventions

- Python 3.11+, type hints throughout
- Dataclasses (frozen) for data objects (`Task`, `Reschedule`, `Config`)
- Click for CLI commands
- `logging` module for debug/info output
- Atomic file writes in writer.py (temp file → replace)

## Task format in Backlog.md

```markdown
- [ ] Task Name — Feb 20 (1h) #tag1 #tag2
- [ ] Do monthly invoice — Mar 18 (30m) #work @monthly:18
- [ ] Prep monthly report — Feb 24 (1h) #work @monthly:4tue
```

Supports: `1h`, `30m`, `1.5h` for estimates. Em-dash separates name from metadata.

### Recurring tasks

Two recurrence syntaxes:

- `@monthly:DD` - fixed day of month (e.g. `@monthly:18` for the 18th). Day is clamped to month length (e.g. day 31 in February becomes 28).
- `@monthly:NthDAY` - nth weekday of month (e.g. `@monthly:4tue` for the 4th Tuesday). If the month has fewer than N occurrences, the last one is used.

When a recurring task is marked `[x]` and `reflow run` is called, reflow auto-generates the next month's occurrence in the Upcoming section.

## Backlog sections (in priority order)

Overdue → Due This Week → Personal → Research → Admin → Writing → Upcoming

The themed sections (Personal, Research, Admin, Writing) are examples. Rename them
to your own areas of work in `scheduler.py` and `writer.py`; the scheduler only
cares about their order, not their names.

## Dual calendar setup

- **Reads** from primary calendar (to check busy times)
- **Creates** events on a dedicated reflow calendar (`reflow_calendar_id` in .env)
- Events tagged with `reflow:managed` in description for idempotency

## Working hours

Default: 11:00–19:00, lunch 13:00–14:00 (Europe/London). Configurable via .env.

## Commands

```bash
reflow status              # Dry-run preview
reflow run                 # Schedule all tasks with deadlines
reflow run --dry-run       # Preview without changes
reflow run --overdue-only  # Only reschedule overdue tasks
reflow auth                # Google OAuth flow
```

## Running tests

```bash
source .venv/bin/activate
pytest tests/ -v
```

## Files that should never be committed

- `credentials.json`, `token.json` (Google OAuth secrets)
- `.env` (personal config)
