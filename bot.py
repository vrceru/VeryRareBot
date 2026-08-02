import discord
from discord.ext import commands
import os
import asyncio

from core.logger import setup_logger
from core.version import get_version
from core.startup import startup_banner, ready_banner
from config import settings
from core.embed import error_embed


logger = setup_logger()

startup_banner()

class VeryRareBot(commands.Bot):

    def __init__(self):

        intents = discord.Intents.default()

        intents.message_content = True
        intents.voice_states = True
        intents.members = True

        super().__init__(
            command_prefix="!",
            intents=intents
        )


    async def setup_hook(self):

        logger.info(
            f"Starting VeryRareBot v{get_version()}"
        )

        await self.load_cogs()

        await self.tree.sync()

        logger.info(
            "Slash commands synced"
        )


    async def load_cogs(self):

        cogs_path = "cogs"

        for file in os.listdir(cogs_path):

            if file.endswith(".py") and file != "__init__.py":

                path = os.path.join(cogs_path, file)

                if os.path.getsize(path) == 0:
                    logger.warning(
                        f"Skipping empty cog: {file}"
                    )
                    continue

                extension = f"cogs.{file[:-3]}"

                try:
                    await self.load_extension(extension)

                    logger.info(
                        f"Loaded cog: {extension}"
                    )

                except Exception as e:

                    logger.exception(
                        f"Failed loading {extension}: {e}"
                    )


bot = VeryRareBot()

@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error
):

    if isinstance(
        error,
        discord.app_commands.errors.MissingRole
    ):

        embed = error_embed(
            "Permission Denied",
            "You do not have permission to use this command."
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

        return


    if isinstance(
        error,
        discord.app_commands.errors.CheckFailure
    ):

        embed = error_embed(
            "Permission Denied",
            "You do not have access to this command."
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

        return


    logger.exception(
        "Unhandled application command error",
        exc_info=error
    )

@bot.event
async def on_ready():

    logger.info(
        f"Logged in as {bot.user}"
    )

    logger.info(
        f"Connected to {len(bot.guilds)} servers"
    )

    ready_banner(bot)

    await bot.change_presence(
        activity=discord.Game(
            name=f"VRS Assistant v{get_version()}"
        )
    )


async def main():

    async with bot:

        await bot.start(
            settings.DISCORD_TOKEN
        )


if __name__ == "__main__":

    asyncio.run(main())
