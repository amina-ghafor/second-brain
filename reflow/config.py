"""Settings for reflow, overridable via .env or environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


def _load_env() -> None:
    """Load .env from the project root if it exists."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(env_path)


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _env_int(key: str, default: int) -> int:
    return int(os.environ.get(key, str(default)))


@dataclass(frozen=True)
class Config:
    backlog_path: Path = field(default_factory=lambda: Path(_env(
        "BACKLOG_PATH", "~/Projects/Tasks/Backlog.md"
    )).expanduser())
    timezone: str = field(default_factory=lambda: _env("TIMEZONE", "Europe/Madrid"))
    calendar_id: str = field(default_factory=lambda: _env("CALENDAR_ID", "primary"))
    working_hours_start: int = field(default_factory=lambda: _env_int("WORKING_HOURS_START", 11))
    working_hours_end: int = field(default_factory=lambda: _env_int("WORKING_HOURS_END", 19))
    lunch_start: int = field(default_factory=lambda: _env_int("LUNCH_START", 13))
    lunch_end: int = field(default_factory=lambda: _env_int("LUNCH_END", 14))
    lookahead_days: int = field(default_factory=lambda: _env_int("LOOKAHEAD_DAYS", 5))
    credentials_path: Path = field(default_factory=lambda: Path(_env(
        "CREDENTIALS_PATH", "~/Code/reflow/credentials.json"
    )).expanduser())
    token_path: Path = field(default_factory=lambda: Path(_env(
        "TOKEN_PATH", "~/Code/reflow/token.json"
    )).expanduser())


_load_env()


def load_config() -> Config:
    """Create a Config instance with current environment values."""
    return Config()
