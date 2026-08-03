"""Generates the join-welcome image card: a new member's avatar composited onto
the Very Rare Society "VRS" template, replacing ProBot's welcome card.
"""

import asyncio
import io
from pathlib import Path

import discord
from PIL import Image, ImageDraw

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "assets" / "welcome_card.png"

CANVAS_SIZE = (1080, 1080)
AVATAR_DIAMETER = 320
AVATAR_CENTER = (224, 573)
BORDER_WIDTH = 8
BORDER_COLOR = (255, 255, 255, 255)
BACKGROUND_COLOR = (255, 255, 255, 255)


def _circular_avatar(avatar_bytes: bytes, diameter: int) -> Image.Image:
    avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
    avatar = avatar.resize((diameter, diameter), Image.LANCZOS)

    mask = Image.new("L", (diameter, diameter), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, diameter, diameter), fill=255)
    avatar.putalpha(mask)
    return avatar


def render_card(avatar_bytes: bytes) -> bytes:
    """Pure, synchronous image composition -- safe to run in a thread executor."""

    canvas = Image.new("RGBA", CANVAS_SIZE, BACKGROUND_COLOR)
    cx, cy = AVATAR_CENTER

    if BORDER_WIDTH > 0:
        border_diameter = AVATAR_DIAMETER + BORDER_WIDTH * 2
        border = Image.new("RGBA", (border_diameter, border_diameter), (0, 0, 0, 0))
        ImageDraw.Draw(border).ellipse((0, 0, border_diameter, border_diameter), fill=BORDER_COLOR)
        canvas.alpha_composite(border, (cx - border_diameter // 2, cy - border_diameter // 2))

    avatar = _circular_avatar(avatar_bytes, AVATAR_DIAMETER)
    canvas.alpha_composite(avatar, (cx - AVATAR_DIAMETER // 2, cy - AVATAR_DIAMETER // 2))

    template = Image.open(TEMPLATE_PATH).convert("RGBA")
    if template.size != CANVAS_SIZE:
        template = template.resize(CANVAS_SIZE, Image.LANCZOS)
    canvas.alpha_composite(template)

    buffer = io.BytesIO()
    canvas.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()


async def generate_welcome_card(member: discord.Member) -> discord.File:
    avatar_bytes = await member.display_avatar.with_size(512).read()

    loop = asyncio.get_running_loop()
    png_bytes = await loop.run_in_executor(None, render_card, avatar_bytes)

    return discord.File(io.BytesIO(png_bytes), filename="welcome.png")
