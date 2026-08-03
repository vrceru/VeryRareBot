import discord
from datetime import datetime, timezone

from core.version import get_version

# ============================================================
# STATUS COLORS
# ============================================================

SUCCESS = discord.Color.green()
INFO = discord.Color.blurple()
WARNING = discord.Color.orange()
ERROR = discord.Color.red()

# ============================================================
# MODULE COLORS
# ============================================================

UTILITY = discord.Color.blurple()
SERVER = discord.Color.dark_blue()
VRMS = discord.Color.dark_teal()
JELLYFIN = discord.Color.purple()
ADMIN = discord.Color.dark_red()
MUSIC = discord.Color.magenta()

# ============================================================
# BASE EMBED
# ============================================================

def make_embed(
    title: str,
    description: str | None = None,
    color=INFO
):

    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.now(timezone.utc)
    )

    embed.set_footer(
        text=f"VeryRareBot • v{get_version()}"
    )

    return embed


# ============================================================
# STATUS EMBEDS
# ============================================================

def success_embed(title, description=None):
    return make_embed(
        title,
        description,
        SUCCESS
    )


def warning_embed(title, description=None):
    return make_embed(
        title,
        description,
        WARNING
    )


def error_embed(title, description=None):
    return make_embed(
        title,
        description,
        ERROR
    )


def info_embed(title, description=None):
    return make_embed(
        title,
        description,
        INFO
    )


# ============================================================
# MODULE EMBEDS
# ============================================================

def utility_embed(title, description=None):
    return make_embed(
        title,
        description,
        UTILITY
    )


def server_embed(title, description=None):
    return make_embed(
        title,
        description,
        SERVER
    )


def vrms_embed(title, description=None):
    return make_embed(
        title,
        description,
        VRMS
    )


def jellyfin_embed(title, description=None):
    return make_embed(
        title,
        description,
        JELLYFIN
    )


def admin_embed(title, description=None):
    return make_embed(
        title,
        description,
        ADMIN
    )


def music_embed(title, description=None):
    return make_embed(
        title,
        description,
        MUSIC
    )
