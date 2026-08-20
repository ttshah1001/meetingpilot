"""Load configuration from .env. Secrets are never hardcoded."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Project root = parent of the meetingpilot package
PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")


def _path_from_env(key: str, default: str) -> Path:
    raw = os.getenv(key, default)
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str
    anthropic_model: str
    gemini_api_key: str
    gemini_model: str
    db_path: Path
    google_credentials_path: Path
    google_token_path: Path
    google_calendar_id: str
    low_confidence_threshold: float


def get_settings() -> Settings:
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    return Settings(
        anthropic_api_key=key,
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
        gemini_api_key=gemini_key,
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
        db_path=_path_from_env("MEETINGPILOT_DB", "meetings.db"),
        google_credentials_path=_path_from_env(
            "GOOGLE_CREDENTIALS_PATH", "credentials.json"
        ),
        google_token_path=_path_from_env("GOOGLE_TOKEN_PATH", "token.json"),
        google_calendar_id=os.getenv("GOOGLE_CALENDAR_ID", "primary"),
        low_confidence_threshold=float(os.getenv("LOW_CONFIDENCE_THRESHOLD", "0.6")),
    )
