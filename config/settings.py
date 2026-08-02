import os
from dotenv import load_dotenv

load_dotenv()


DISCORD_TOKEN = os.getenv(
    "DISCORD_TOKEN"
)

ANNOUNCEMENT_CHANNEL_ID = int(
    os.getenv(
        "ANNOUNCEMENT_CHANNEL_ID",
        0
    )
)

LOG_CHANNEL_ID = int(
    os.getenv(
        "LOG_CHANNEL_ID",
        0
    )
)


WELCOME_CHANNEL_ID = int(
    os.getenv(
        "WELCOME_CHANNEL_ID",
        0
    )
)


VRMS_CHANNEL_ID = int(
    os.getenv(
        "VRMS_CHANNEL_ID",
        0
    )
)

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


LOG_LEVEL = os.getenv(
    "LOG_LEVEL",
    "INFO"
)

OWNER_ROLE_ID = int(
    os.getenv(
        "OWNER_ROLE_ID",
        0
    )
)

DEV_OPS_ROLE_ID = int(
    os.getenv(
        "DEV_OPS_ROLE_ID",
        0
    )
)

ADMIN_ROLE_ID = int(
    os.getenv(
        "ADMIN_ROLE_ID",
        0
    )
)

STAFF_ROLE_ID = int(
    os.getenv(
        "STAFF_ROLE_ID",
        0
    )
)

VRS_MEMBER_ROLE_ID = int(
    os.getenv(
        "VRS_MEMBER_ROLE_ID",
        0
    )
)
