# second-brain

Run your work off one task list. The backlog is a plain Markdown file in an Obsidian vault. A daily script reads it, finds free time in your calendar, books the overdue work in, and rewrites the dates. Around that sit a few Claude Code commands that turn a working session into a plan, a set of notes, or a review.

Built for my own use and generalised here. No web app and no server: a text file, a calendar, and a cron job.

## The parts

**reflow** - the scheduler. It parses `Backlog.md` for tasks that have a deadline and a time estimate, picks out the overdue ones, scans the next few working days for a free calendar slot, books each task, and updates its date in the file. Tick off a recurring task and the next occurrence is written back in. Run it on a daily cron and the day is planned before you sit down.

**The vault** - the Markdown convention reflow reads: the backlog sections in priority order, the deadline and estimate format, the recurrence syntax. This is the only thing reflow depends on.

**The commands** - one prompt file each, in `skills/`. `dayplan` builds the day from the calendar and the backlog. `capture` writes a finished session into the right notes. More will land here one at a time, each with its own note on what it does and where it helps.

## Status

reflow runs and is tested. The commands are being ported across from my working setup.

## The backlog format

`Backlog.md` is divided into sections, read in this priority order:

```
Overdue → Due This Week → Personal → Research → Admin → Writing → Upcoming
```

The themed sections (Personal, Research, Admin, Writing) are examples. Rename them to your own areas in `reflow/scheduler.py` and `reflow/writer.py`; the scheduler cares about their order, not their names.

A task line:

```markdown
- [ ] Task name — Sep 20 (1h) #tag
- [ ] Do monthly report — Sep 18 (30m) #work @monthly:18
- [ ] Prep for the quarterly review — Sep 24 (1h) #work @monthly:4tue
```

An em dash separates the name from the metadata. Estimates are `1h`, `30m`, `1.5h`. Recurrence:

- `@monthly:DD` - a fixed day of the month, clamped to month length (day 31 becomes 28 in February).
- `@monthly:NthDAY` - the nth weekday, e.g. `@monthly:4tue` for the fourth Tuesday. If the month has fewer than N, the last one is used.

Mark a recurring task `[x]` and the next occurrence is generated in the Upcoming section on the next run.

## Setup

### 1. Install

```bash
git clone https://github.com/amina-ghafor/second-brain.git ~/code/second-brain
cd ~/code/second-brain
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Google Calendar API credentials

1. Open the [Google Cloud Console](https://console.cloud.google.com) and create a project.
2. Under **APIs & Services > Library**, enable the Google Calendar API.
3. Under **APIs & Services > Credentials**, create an **OAuth 2.0 Client ID**, application type **Desktop app**.
4. Download the JSON and save it as `~/code/second-brain/credentials.json`.

### 3. Authenticate

```bash
reflow auth
```

This opens a browser to grant calendar access. The token is saved to `token.json` for later runs. Both files are gitignored.

### 4. Configuration

Copy `.env.example` to `.env` and edit. Defaults:

- **Backlog:** `~/Projects/Tasks/Backlog.md`
- **Timezone:** `Europe/London`
- **Working hours:** 11:00-19:00, lunch 13:00-14:00
- **Lookahead:** 5 working days
- **Reads** busy times from your primary calendar; **creates** events on a separate calendar set by `REFLOW_CALENDAR_ID`, so the scheduled blocks stay visually distinct.

## Usage

```bash
reflow status              # dry-run preview
reflow run                 # schedule all tasks with deadlines
reflow run --dry-run       # preview without writing
reflow run --overdue-only  # only reschedule overdue tasks
```

### What a run does

1. Parses `Backlog.md` for tasks with a deadline and an estimate.
2. Identifies the overdue ones (deadline before today).
3. Scans the next few working days for a free slot the length of the estimate.
4. Creates a `[Reflow]` calendar event in the slot.
5. Rewrites the task's date in `Backlog.md`.

Running it again is safe. It checks for the `[Reflow]` event before creating one, and only ever touches events it made.

## Cron

Weekdays at 08:00, before working hours:

```
0 8 * * 1-5 cd ~/code/second-brain && .venv/bin/python -m reflow run >> ~/code/second-brain/reflow.log 2>&1
```

## Tests

```bash
source .venv/bin/activate
pytest tests/ -v
```

## Why

A backlog is only honest if it reschedules itself. A list of deadlines you set last week and never move is a wish list, not a plan. Moving that work by hand every morning is the task most likely to be skipped on the mornings it matters. reflow does the moving, so the backlog stays true to what is actually left.

The cost is worth naming: a scheduler that always finds room can hide an overcommitted list rather than force the cut. The file is plain text so you can see the pile and make that call yourself. The tool schedules; it does not decide what matters.
