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


def validate() -> list[str]:
    """Return configuration problems that should prevent the bot from starting."""
    return [] if DISCORD_TOKEN else ["DISCORD_TOKEN is required"]
