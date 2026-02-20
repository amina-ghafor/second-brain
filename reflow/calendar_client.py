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
REFLOW_TAG = "reflow:managed"


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

    def _get_events_from_calendar(
        self, calendar_id: str, date_start: date, date_end: date
    ) -> list[dict]:
        """List events from a specific calendar in the given date range."""
        import pytz

        tz = pytz.timezone(self.config.timezone)
        time_min = tz.localize(datetime.combine(date_start, time.min))
        time_max = tz.localize(datetime.combine(date_end + timedelta(days=1), time.min))

        events = []
        page_token = None

        while True:
            result = self.service.events().list(
                calendarId=calendar_id,
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

    def get_events(self, date_start: date, date_end: date) -> list[dict]:
        """List events from the primary calendar in the given date range (inclusive)."""
        return self._get_events_from_calendar(
            self.config.calendar_id, date_start, date_end
        )

    def get_free_slots(self, target_date: date) -> list[tuple[datetime, datetime]]:
        """Return free time blocks for a given day within working hours, excluding lunch.

        Checks BOTH primary calendar and reflow tasks calendar for occupied slots.
        """
        import pytz

        tz = pytz.timezone(self.config.timezone)
        cfg = self.config

        work_start = tz.localize(datetime.combine(target_date, time(cfg.working_hours_start)))
        work_end = tz.localize(datetime.combine(target_date, time(cfg.working_hours_end)))
        lunch_start = tz.localize(datetime.combine(target_date, time(cfg.lunch_start)))
        lunch_end = tz.localize(datetime.combine(target_date, time(cfg.lunch_end)))

        # Get events from primary calendar
        events = self.get_events(target_date, target_date)

        # Also get events from the reflow tasks calendar to avoid double-booking
        if cfg.reflow_calendar_id != cfg.calendar_id:
            reflow_events = self._get_events_from_calendar(
                cfg.reflow_calendar_id, target_date, target_date
            )
            events.extend(reflow_events)

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

            evt_start = datetime.fromisoformat(start_raw["dateTime"]).astimezone(tz)
            evt_end = datetime.fromisoformat(end_raw["dateTime"]).astimezone(tz)

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

        # Skip past time when scheduling for today
        now = datetime.now(tz)
        if target_date == now.date():
            cursor_floor = now
        else:
            cursor_floor = work_start

        # Calculate gaps
        free_slots: list[tuple[datetime, datetime]] = []
        cursor = max(work_start, cursor_floor)

        for block_start, block_end in merged:
            if cursor < block_start:
                free_slots.append((cursor, block_start))
            cursor = max(cursor, block_end)

        if cursor < work_end:
            free_slots.append((cursor, work_end))

        return free_slots

    def find_task_event(self, task_name: str, after_date: date | None = None) -> dict | None:
        """Find an existing reflow-managed event for a task name.

        Searches the reflow tasks calendar from after_date through the lookahead window.
        Matches by task name in the summary and reflow:managed tag in description.
        Returns the event dict if found, None otherwise.
        """
        search_start = after_date or date.today()
        search_end = search_start + timedelta(days=self.config.lookahead_days + 1)

        events = self._get_events_from_calendar(
            self.config.reflow_calendar_id, search_start, search_end
        )

        for event in events:
            desc = event.get("description", "")
            summary = event.get("summary", "").strip()
            if REFLOW_TAG in desc and task_name.lower() in summary.lower():
                return event

        return None

    def create_task_event(
        self, task_name: str, start: datetime, end: datetime
    ) -> dict:
        """Create a calendar event on the reflow tasks calendar."""
        event_body = {
            "summary": task_name,
            "description": f"{REFLOW_TAG} | From Backlog.md",
            "start": {"dateTime": start.isoformat(), "timeZone": self.config.timezone},
            "end": {"dateTime": end.isoformat(), "timeZone": self.config.timezone},
            "colorId": "8",  # grey
        }

        event = self.service.events().insert(
            calendarId=self.config.reflow_calendar_id, body=event_body
        ).execute()

        logger.info("Created event: %s at %s", event["summary"], start)
        return event

    def move_event(self, event_id: str, new_start: datetime, new_end: datetime) -> dict:
        """Reschedule an existing event on the reflow tasks calendar."""
        event_body = {
            "start": {"dateTime": new_start.isoformat(), "timeZone": self.config.timezone},
            "end": {"dateTime": new_end.isoformat(), "timeZone": self.config.timezone},
        }

        event = self.service.events().patch(
            calendarId=self.config.reflow_calendar_id,
            eventId=event_id,
            body=event_body,
        ).execute()

        logger.info("Moved event %s to %s", event_id, new_start)
        return event
