"""Standalone access check — run BEFORE building the Gmail/multimodal extension.

Pokes each API "door" with the smallest possible request and reports
yes/no. Does not create, send, or delete anything real.

Usage:
    uv run python scripts/check_access.py

Requires (put these in .env / credentials.json first, see README.md):
    GEMINI_API_KEY      (.env) -- primary LLM, free tier via https://aistudio.google.com/apikey
    ANTHROPIC_API_KEY   (.env) -- optional, only if still testing the Claude path
    credentials.json    (Google OAuth Desktop client, project root) -- Calendar + Gmail
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from meetingpilot.config import get_settings  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []
OPTIONAL = {"Anthropic API (optional, legacy)"}


def record(name: str, ok: bool, detail: str) -> None:
    RESULTS.append((name, ok, detail))
    icon = "PASS" if ok else ("SKIP" if name in OPTIONAL else "FAIL")
    print(f"[{icon}] {name}: {detail}")


# A 1x1 transparent PNG, base64-encoded. Just proves the model accepts
# an image the way it accepts text; not a real screenshot.
TINY_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def check_gemini() -> None:
    """Primary LLM (free tier). Proves the key + model work for a plain text call."""
    settings = get_settings()
    if not settings.gemini_api_key:
        record("Gemini API (primary LLM)", False, "GEMINI_API_KEY missing from .env — get one at https://aistudio.google.com/apikey")
        return
    try:
        from google import genai

        client = genai.Client(api_key=settings.gemini_api_key)
        client.models.generate_content(
            model=settings.gemini_model,
            contents="hi",
        )
        record("Gemini API (primary LLM)", True, f"key + model '{settings.gemini_model}' work")
    except Exception as exc:  # noqa: BLE001
        record("Gemini API (primary LLM)", False, f"{type(exc).__name__}: {exc}")


def check_gemini_vision() -> None:
    """The extraction call needs to accept image input for the screenshot feature."""
    settings = get_settings()
    if not settings.gemini_api_key:
        record("Gemini vision (image input)", False, "skipped — no API key")
        return
    try:
        import base64

        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.gemini_api_key)
        client.models.generate_content(
            model=settings.gemini_model,
            contents=[
                types.Part.from_bytes(data=base64.b64decode(TINY_PNG), mime_type="image/png"),
                "describe in one word",
            ],
        )
        record("Gemini vision (image input)", True, "model accepted an image input")
    except Exception as exc:  # noqa: BLE001
        record("Gemini vision (image input)", False, f"{type(exc).__name__}: {exc}")


def check_anthropic() -> None:
    """Optional / legacy path — only relevant if still comparing against Claude."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        record("Anthropic API (optional, legacy)", False, "skipped — ANTHROPIC_API_KEY not set, not required now")
        return
    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=settings.anthropic_api_key)
        client.messages.create(
            model=settings.anthropic_model,
            max_tokens=1,
            messages=[{"role": "user", "content": "hi"}],
        )
        record("Anthropic API (optional, legacy)", True, f"key + model '{settings.anthropic_model}' work")
    except Exception as exc:  # noqa: BLE001
        record("Anthropic API (optional, legacy)", False, f"{type(exc).__name__}: {exc}")


ALL_GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/gmail.compose",
]


def _google_creds():
    """One combined OAuth round-trip for both Calendar + Gmail scopes.

    Binds the local callback server to 127.0.0.1 explicitly (not
    "localhost") — on some Macs, "localhost" resolves to the IPv6
    address ::1 first, which the server isn't listening on, so the
    browser redirect fails with "can't connect to the server" even
    though the Google consent step itself succeeded.
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    settings = get_settings()
    creds_path = settings.google_credentials_path
    token_path = settings.google_token_path

    if not creds_path.exists():
        raise FileNotFoundError(f"{creds_path} not found — see README.md Google setup steps")

    creds = None
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), ALL_GOOGLE_SCOPES)
        except Exception:  # noqa: BLE001
            creds = None
    if not creds or not creds.valid or not set(ALL_GOOGLE_SCOPES).issubset(set(creds.scopes or [])):
        if creds and creds.expired and creds.refresh_token and set(ALL_GOOGLE_SCOPES).issubset(set(creds.scopes or [])):
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), ALL_GOOGLE_SCOPES)
            creds = flow.run_local_server(port=0, host="127.0.0.1", open_browser=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds


def check_google() -> None:
    try:
        creds = _google_creds()
    except Exception as exc:  # noqa: BLE001
        record("Google Calendar API", False, f"{type(exc).__name__}: {exc}")
        record("Gmail API (gmail.compose)", False, "skipped — Google login failed above")
        return

    try:
        from googleapiclient.discovery import build

        # calendar.events scope only covers the Events resource, not
        # Calendars metadata — calendars().get() needs a broader scope
        # and will 403 even with valid calendar.events access.
        service = build("calendar", "v3", credentials=creds)
        events = service.events().list(calendarId="primary", maxResults=1).execute()
        record("Google Calendar API", True, f"events access confirmed ({len(events.get('items', []))} event(s) visible)")
    except Exception as exc:  # noqa: BLE001
        record("Google Calendar API", False, f"{type(exc).__name__}: {exc}")

    try:
        from googleapiclient.discovery import build

        service = build("gmail", "v1", credentials=creds)
        profile = service.users().getProfile(userId="me").execute()
        record("Gmail API (gmail.compose)", True, f"reachable for {profile.get('emailAddress')}")
    except Exception as exc:  # noqa: BLE001
        record(
            "Gmail API (gmail.compose)",
            False,
            f"{type(exc).__name__}: {exc} "
            "(likely cause: Gmail API not enabled in the same Cloud Console project — "
            "APIs & Services > Library > Gmail API > Enable)",
        )


def main() -> None:
    print("MeetingPilot access check — no real events/drafts are created.\n")
    check_gemini()
    check_gemini_vision()
    check_google()
    check_anthropic()

    print("\nSummary:")
    failed = [name for name, ok, _ in RESULTS if not ok and name not in OPTIONAL]
    for name, ok, _ in RESULTS:
        tag = "OK " if ok else ("SKIP" if name in OPTIONAL else "MISSING")
        print(f"  {tag}  {name}")
    if failed:
        print(f"\n{len(failed)} required door(s) not open yet: {', '.join(failed)}")
        print("Fix these before building the matching feature — see README.md setup steps.")
        sys.exit(1)
    print("\nAll required doors open. Safe to build the multimodal + Gmail-draft + .ics extension.")


if __name__ == "__main__":
    main()
