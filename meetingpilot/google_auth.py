"""Shared Google OAuth: one combined token for Calendar + Gmail + Tasks scopes.

calendar_tool.py, gmail_tool.py, and tasks_tool.py all use this so a
single consent covers every tool instead of each requesting its own
scope against the same token file (which silently produces a token
missing the other tools' scopes).
"""

from __future__ import annotations

from meetingpilot.config import get_settings

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/tasks",
]


def get_credentials():
    """Build an authenticated Google credentials object. Token is stored locally."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    settings = get_settings()
    creds_path = settings.google_credentials_path
    token_path = settings.google_token_path

    if not creds_path.exists():
        raise FileNotFoundError(
            f"Google OAuth client file not found at {creds_path}. "
            "See README.md for Cloud Console setup, or use --dry-run."
        )

    creds = None
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except Exception:  # noqa: BLE001
            creds = None

    if not creds or not creds.valid or not set(SCOPES).issubset(set(creds.scopes or [])):
        if creds and creds.expired and creds.refresh_token and set(SCOPES).issubset(set(creds.scopes or [])):
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            # Bind to 127.0.0.1 explicitly, not "localhost" — on some Macs
            # "localhost" resolves to ::1 first, which the callback server
            # isn't listening on, and the browser redirect fails even
            # though the Google-side consent succeeded.
            creds = flow.run_local_server(port=0, host="127.0.0.1", open_browser=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds
