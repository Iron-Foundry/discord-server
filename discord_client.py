import discord
from discord import app_commands
from loguru import logger
from typing import Optional
from command_handler import CommandHandler
from config import ConfigInterface, ConfigVars


class DiscordClient(discord.Client):
    _guild = Optional[discord.Guild] = None

    def __init__(self):
        super().__init__(intents=discord.Intents.all())
        config = ConfigInterface()
        self.debug = config.get_variable(ConfigVars.debug_mode)
        self.command_handler: CommandHandler = CommandHandler(client=self)
        self.tree: app_commands.CommandTree = self.command_handler.tree
        self._guild = self.get_guild(id=int(config.get_variable(ConfigVars.guild_id)))
        self.command_handler.guild = self._guild
        logger.info("DiscordClient initialized.")

    @property
    def guild(self):
        if not self._guild:
            raise RuntimeError("Guild not set")
        return self._guild

    async def setup_hook(self) -> None:
        logger.info("Setting up client...")

    async def on_ready(self):
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        logger.info(await self.command_handler.sync())
