import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_int(name: str, default: int = 0) -> int:
    """Read a Discord snowflake without failing on a blank environment value."""
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a numeric Discord ID") from exc


DISCORD_TOKEN = os.getenv(
    "DISCORD_TOKEN"
)

GUILD_ID = env_int("GUILD_ID")
ANNOUNCEMENT_CHANNEL_ID = env_int("ANNOUNCEMENT_CHANNEL_ID")
LOG_CHANNEL_ID = env_int("LOG_CHANNEL_ID")
WELCOME_CHANNEL_ID = env_int("WELCOME_CHANNEL_ID")
VRMS_CHANNEL_ID = env_int("VRMS_CHANNEL_ID")

JELLYFIN_URL = os.getenv(
    "JELLYFIN_URL"
)

JELLYFIN_TOKEN = os.getenv(
    "JELLYFIN_TOKEN"
)

JELLYFIN_USER_ID = os.getenv(
    "JELLYFIN_USER_ID"
)


VRMS_PATH = os.getenv(
    "VRMS_PATH",
    "/home/ceru/VRMS"
)
VRMS_SERVICE_NAME = os.getenv("VRMS_SERVICE_NAME", "").strip()


LOG_LEVEL = os.getenv(
    "LOG_LEVEL",
    "INFO"
)

OWNER_ROLE_ID = env_int("OWNER_ROLE_ID")
DEV_OPS_ROLE_ID = env_int("DEV_OPS_ROLE_ID")
ADMIN_ROLE_ID = env_int("ADMIN_ROLE_ID")
STAFF_ROLE_ID = env_int("STAFF_ROLE_ID")
VRS_MEMBER_ROLE_ID = env_int("VRS_MEMBER_ROLE_ID")


def env_float(name: str, default: float) -> float:
    """Read a float setting without failing on a blank environment value."""
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


MUSIC_MAX_QUEUE_SIZE = env_int("MUSIC_MAX_QUEUE_SIZE", 200)
MUSIC_DEFAULT_VOLUME = env_float("MUSIC_DEFAULT_VOLUME", 0.5)
MUSIC_IDLE_DISCONNECT_SECONDS = env_int("MUSIC_IDLE_DISCONNECT_SECONDS", 300)
MUSIC_SEARCH_RESULTS = env_int("MUSIC_SEARCH_RESULTS", 5)
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg").strip() or "ffmpeg"

DATABASE_PATH = os.getenv("DATABASE_PATH", "").strip() or str(BASE_DIR / "data" / "verrarebot.sqlite3")

JELLYFIN_NOTIFY_CHANNEL_ID = env_int("JELLYFIN_NOTIFY_CHANNEL_ID")
JELLYFIN_POLL_SECONDS = env_int("JELLYFIN_POLL_SECONDS", 300)
VRMS_NOTIFY_CHANNEL_ID = env_int("VRMS_NOTIFY_CHANNEL_ID")
VRMS_POLL_SECONDS = env_int("VRMS_POLL_SECONDS", 60)

TICKET_CATEGORY_ID = env_int("TICKET_CATEGORY_ID")
TICKET_STAFF_ROLE_ID = env_int("TICKET_STAFF_ROLE_ID") or STAFF_ROLE_ID
TICKET_MAX_OPEN_PER_USER = env_int("TICKET_MAX_OPEN_PER_USER", 3)

TMDB_API_KEY = os.getenv("TMDB_API_KEY", "").strip()
MEDIA_REQUEST_CHANNEL_ID = env_int("MEDIA_REQUEST_CHANNEL_ID")
# Where the staff review card (Approve/Deny/Hold) posts. Deliberately separate from
# MEDIA_REQUEST_CHANNEL_ID so a public request panel and a staff-only approval queue can live in
# different channels -- falls back to MEDIA_REQUEST_CHANNEL_ID, then the invoking channel, if unset.
MEDIA_QUE_CHANNEL_ID = env_int("MEDIA_QUE_CHANNEL_ID")

VRMS_API_URL = os.getenv("VRMS_API_URL", "").strip()
VRMS_API_KEY = os.getenv("VRMS_API_KEY", "").strip()
VRMS_JOB_POLL_SECONDS = env_int("VRMS_JOB_POLL_SECONDS", 30)


def validate() -> list[str]:
    """Return configuration problems that should prevent the bot from starting."""
    return [] if DISCORD_TOKEN else ["DISCORD_TOKEN is required"]
