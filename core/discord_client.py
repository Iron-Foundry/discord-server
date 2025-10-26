from typing import override
import discord
from discord import app_commands
from loguru import logger
from command_handler import CommandHandler
from config import ConfigInterface, ConfigVars


class DiscordClient(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.all())
        self.config: ConfigInterface = ConfigInterface()
        self._guild: discord.Guild | None = None
        self.debug: bool = bool(self.config.get_variable(ConfigVars.DEBUG_MODE))
        self.command_handler: CommandHandler = CommandHandler(client=self)
        self.tree: app_commands.CommandTree = self.command_handler.tree

    async def guild_setup(self) -> None:
        guild_id_str: str | None = self.config.get_variable(ConfigVars.GUILD_ID)
        if guild_id_str:
            self._guild = self.get_guild(int(guild_id_str))
            if self._guild:
                self.command_handler.guild = self._guild
                logger.info(f"Guild set to: {self._guild.name}")
            else:
                logger.error(f"Guild with ID {guild_id_str} not found")

    @override
    async def setup_hook(self) -> None:
        logger.info("Setting up client...")
        await self.guild_setup()

    async def on_ready(self):
        if not self.user:
            logger.error("Failed to connect.")
            return
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        logger.info(await self.command_handler.sync())

    @property
    def current_guild(self) -> discord.Guild | None:
        if self._guild:
            raise RuntimeError("Guild not set")
        return self._guild

    @property
    def tree(self) -> app_commands.CommandTree:
        if self.tree:
            return self.tree
        raise RuntimeError("Command Initialization Failed / Not started.")
