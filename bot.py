import discord
from discord.ext import commands
import os
import asyncio

from core.logger import setup_logger
from core.version import get_version
from core.startup import startup_banner, ready_banner
from config import settings
from core.embed import error_embed
from services.database import Database


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

        self.db = Database(settings.DATABASE_PATH)


    async def setup_hook(self):

        logger.info(
            f"Starting VeryRareBot v{get_version()}"
        )

        await self.db.connect()
        logger.info("Database connected at %s", settings.DATABASE_PATH)

        await self.load_cogs()

        if settings.GUILD_ID:
            guild = discord.Object(id=settings.GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info("Slash commands synced to development guild %s", settings.GUILD_ID)
        else:
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


    async def close(self):

        await self.db.close()

        await super().close()


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


    logger.exception("Unhandled application command error", exc_info=error)

    embed = error_embed(
        "Command Failed",
        "Something went wrong while running that command. Please try again later."
    )
    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed, ephemeral=True)

    log_channel = bot.get_channel(settings.LOG_CHANNEL_ID) if settings.LOG_CHANNEL_ID else None
    if log_channel is not None:
        command_name = interaction.command.qualified_name if interaction.command else "unknown"
        try:
            await log_channel.send(
                embed=error_embed(
                    "Unhandled Command Error",
                    f"`/{command_name}` raised `{type(error).__name__}: {error}`"
                )
            )
        except discord.HTTPException:
            logger.warning("Failed to deliver an error report to the configured log channel.")

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

    configuration_errors = settings.validate()
    if configuration_errors:
        raise RuntimeError("Invalid configuration: " + "; ".join(configuration_errors))

    async with bot:

        await bot.start(
            settings.DISCORD_TOKEN
        )


if __name__ == "__main__":

    asyncio.run(main())
