# motion-cli

Auto-rescheduling task manager. Reads your Obsidian Backlog.md, detects overdue tasks, finds free slots in Google Calendar, updates the task dates, and creates calendar events.

Designed to run as a daily cron job so overdue tasks are automatically rescheduled before your working day starts.

## Setup

### 1. Install

```bash
cd ~/Code/motion-cli
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Google Calendar API credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project called "motion-cli"
3. Go to **APIs & Services > Library**, search for "Google Calendar API", enable it
4. Go to **APIs & Services > Credentials**
5. Click **Create Credentials > OAuth 2.0 Client ID**
6. Application type: **Desktop app**
7. Download the JSON file and save it as `~/Code/motion-cli/credentials.json`

### 3. Authenticate

```bash
motion auth
```

This opens a browser window to grant calendar access. The token is saved to `~/Code/motion-cli/token.json` for future runs.

### 4. Configuration (optional)

Copy `.env.example` to `.env` and edit as needed:

```bash
cp .env.example .env
```

Defaults:
- **Backlog:** `~/Projects/Tasks/Backlog.md`
- **Timezone:** `Europe/Madrid`
- **Working hours:** 11:00-19:00
- **Lunch:** 13:00-14:00
- **Lookahead:** 5 working days

## Usage

### Check what would be rescheduled (dry run)

```bash
motion status
```

### Run the rescheduler

```bash
motion run
```

Or preview without making changes:

```bash
motion run --dry-run
```

### What it does

1. Parses `Backlog.md` for tasks with deadlines and time estimates
2. Identifies overdue tasks (deadline < today)
3. For each overdue task, scans the next 5 working days for a free calendar slot
4. Creates a `[Motion]` calendar event in the free slot
5. Updates the task's date in `Backlog.md`

### Idempotency

Running multiple times is safe. The tool checks for existing `[Motion]` events before creating new ones. It only touches events it created (identified by the `[Motion]` prefix).

## Cron job

Run weekdays at 08:00 (before working hours):

```bash
crontab -e
```

Add:

```
0 8 * * 1-5 cd ~/Code/motion-cli && .venv/bin/python -m motion_cli.cli run >> ~/Code/motion-cli/motion.log 2>&1
```

## Running tests

```bash
source .venv/bin/activate
pytest tests/ -v
```
