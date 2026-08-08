"""Ticket category definitions.

Adding a new ticket type is a matter of adding one entry to TICKET_CATEGORIES
below (max 5 fields per category, a Discord modal limit) - the slash command
choices, modal, and channel creation all pick it up automatically.
"""

import re
from dataclasses import dataclass, field

import discord


@dataclass(slots=True)
class TicketField:
    label: str
    style: discord.TextStyle = discord.TextStyle.short
    required: bool = True
    placeholder: str | None = None
    max_length: int | None = None


@dataclass(slots=True)
class TicketCategory:
    key: str
    label: str
    emoji: str
    color: discord.Color
    intro: str
    fields: list[TicketField] = field(default_factory=list)


TICKET_CATEGORIES: dict[str, TicketCategory] = {
    "signup": TicketCategory(
        key="signup",
        label="VeryRare Media Sign-Up",
        emoji="🎬",
        color=discord.Color.purple(),
        # No password field here on purpose: this posts into a staff-visible channel and stays
        # in that channel's history indefinitely, which isn't a safe place to hold even a new
        # account's password. Staff set one when creating the Jellyfin account and send it to
        # the requester directly (DM), not through this ticket.
        intro="New VeryRare Media access request. Staff: create the Jellyfin account, send the password directly to the requester (not in this channel), then reply here once it's ready.",
        fields=[
            TicketField("Full Name", max_length=100),
            TicketField("Email Address", max_length=100),
            TicketField("Desired Username", max_length=32),
            TicketField("Age", max_length=3, placeholder="e.g. 25"),
            TicketField("Anything else we should know?", required=False, style=discord.TextStyle.paragraph),
        ],
    ),
    "bug": TicketCategory(
        key="bug",
        label="Bug Report",
        emoji="🐞",
        color=discord.Color.red(),
        intro="Bug report submitted.",
        fields=[
            TicketField("What happened?", style=discord.TextStyle.paragraph),
            TicketField("Steps to reproduce (if known)", style=discord.TextStyle.paragraph, required=False),
        ],
    ),
    "password": TicketCategory(
        key="password",
        label="Forgot Password",
        emoji="🔑",
        color=discord.Color.orange(),
        intro="Password reset request. Staff: verify identity, then reset the account through the Jellyfin admin panel.",
        fields=[
            TicketField("VeryRare Media Username or Email", max_length=100),
        ],
    ),
    "appeal": TicketCategory(
        key="appeal",
        label="Moderation Appeal",
        emoji="⚖️",
        color=discord.Color.dark_gold(),
        intro="Moderation appeal submitted.",
        fields=[
            TicketField("Which action are you appealing?", max_length=200),
            TicketField("Why should it be reconsidered?", style=discord.TextStyle.paragraph),
        ],
    ),
    "other": TicketCategory(
        key="other",
        label="Other",
        emoji="❓",
        color=discord.Color.blurple(),
        intro="General support request.",
        fields=[
            TicketField("What do you need help with?", style=discord.TextStyle.paragraph),
        ],
    ),
}

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def channel_slug(category_key: str, username: str) -> str:
    raw = f"ticket-{category_key}-{username}".lower()
    slug = _SLUG_RE.sub("-", raw).strip("-")
    return slug[:100] or "ticket"
