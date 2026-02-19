"""Google Calendar API wrapper for reflow."""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from reflow.config import Config

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]
REFLOW_PREFIX = "[Reflow]"


class CalendarClient:
    """Wrapper around Google Calendar API."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self._service = None

    def authenticate(self) -> None:
        """Load stored credentials or run OAuth flow."""
        creds = None

        if self.config.token_path.exists():
            creds = Credentials.from_authorized_user_file(
                str(self.config.token_path), SCOPES
            )

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        elif not creds or not creds.valid:
            if not self.config.credentials_path.exists():
                raise FileNotFoundError(
                    f"credentials.json not found at {self.config.credentials_path}. "
                    "Download it from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(self.config.credentials_path), SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Save credentials for next run
        self.config.token_path.write_text(creds.to_json())

        self._service = build("calendar", "v3", credentials=creds)
        logger.info("Authenticated with Google Calendar")

    @property
    def service(self):
        if self._service is None:
            raise RuntimeError("Not authenticated. Call authenticate() first.")
        return self._service

    def get_events(self, date_start: date, date_end: date) -> list[dict]:
        """List events in the given date range (inclusive)."""
        import pytz

        tz = pytz.timezone(self.config.timezone)
        time_min = tz.localize(datetime.combine(date_start, time.min))
        time_max = tz.localize(datetime.combine(date_end + timedelta(days=1), time.min))

        events = []
        page_token = None

        while True:
            result = self.service.events().list(
                calendarId=self.config.calendar_id,
                timeMin=time_min.isoformat(),
                timeMax=time_max.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                pageToken=page_token,
            ).execute()

            events.extend(result.get("items", []))
            page_token = result.get("nextPageToken")
            if not page_token:
                break

        return events

    def get_free_slots(self, target_date: date) -> list[tuple[datetime, datetime]]:
        """Return free time blocks for a given day within working hours, excluding lunch."""
        import pytz

        tz = pytz.timezone(self.config.timezone)
        cfg = self.config

        work_start = tz.localize(datetime.combine(target_date, time(cfg.working_hours_start)))
        work_end = tz.localize(datetime.combine(target_date, time(cfg.working_hours_end)))
        lunch_start = tz.localize(datetime.combine(target_date, time(cfg.lunch_start)))
        lunch_end = tz.localize(datetime.combine(target_date, time(cfg.lunch_end)))

        events = self.get_events(target_date, target_date)

        # Build list of occupied blocks within working hours
        occupied: list[tuple[datetime, datetime]] = []
        # Lunch is always occupied
        occupied.append((lunch_start, lunch_end))

        for event in events:
            start_raw = event.get("start", {})
            end_raw = event.get("end", {})

            # Skip all-day events
            if "date" in start_raw and "dateTime" not in start_raw:
                continue

            evt_start = datetime.fromisoformat(start_raw["dateTime"])
            evt_end = datetime.fromisoformat(end_raw["dateTime"])

            # Clamp to working hours
            evt_start = max(evt_start, work_start)
            evt_end = min(evt_end, work_end)

            if evt_start < evt_end:
                occupied.append((evt_start, evt_end))

        # Sort and merge overlapping blocks
        occupied.sort(key=lambda b: b[0])
        merged: list[tuple[datetime, datetime]] = []
        for start, end in occupied:
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))

        # Calculate gaps
        free_slots: list[tuple[datetime, datetime]] = []
        cursor = work_start

        for block_start, block_end in merged:
            if cursor < block_start:
                free_slots.append((cursor, block_start))
            cursor = max(cursor, block_end)

        if cursor < work_end:
            free_slots.append((cursor, work_end))

        return free_slots

    def find_task_event(self, task_name: str, after_date: date | None = None) -> dict | None:
        """Find an existing [Reflow] event for a task name.

        Searches from after_date (or today) through the lookahead window.
        Returns the event dict if found, None otherwise.
        """
        search_start = after_date or date.today()
        search_end = search_start + timedelta(days=self.config.lookahead_days + 1)

        events = self.get_events(search_start, search_end)
        target_summary = f"{REFLOW_PREFIX} {task_name}"

        for event in events:
            if event.get("summary", "").strip() == target_summary:
                return event

        return None

    def create_task_event(
        self, task_name: str, start: datetime, end: datetime
    ) -> dict:
        """Create a calendar event with [Reflow] prefix."""
        event_body = {
            "summary": f"{REFLOW_PREFIX} {task_name}",
            "description": "Auto-scheduled by reflow from Backlog.md",
            "start": {"dateTime": start.isoformat(), "timeZone": self.config.timezone},
            "end": {"dateTime": end.isoformat(), "timeZone": self.config.timezone},
            "colorId": "8",  # grey
        }

        event = self.service.events().insert(
            calendarId=self.config.calendar_id, body=event_body
        ).execute()

        logger.info("Created event: %s at %s", event["summary"], start)
        return event

    def move_event(self, event_id: str, new_start: datetime, new_end: datetime) -> dict:
        """Reschedule an existing event."""
        event_body = {
            "start": {"dateTime": new_start.isoformat(), "timeZone": self.config.timezone},
            "end": {"dateTime": new_end.isoformat(), "timeZone": self.config.timezone},
        }

        event = self.service.events().patch(
            calendarId=self.config.calendar_id,
            eventId=event_id,
            body=event_body,
        ).execute()

        logger.info("Moved event %s to %s", event_id, new_start)
        return event
