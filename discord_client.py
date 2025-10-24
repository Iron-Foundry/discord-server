import discord
from discord import app_commands
from loguru import logger




class DiscordClient(discord.Client):
    def __init__(self, debug: bool = False):
        super().__init__(intents=discord.Intents.all())
        self.debug = debug
        self.tree: app_commands.CommandTree = app_commands.CommandTree(self)
        logger.info("DiscordClient initialized.")

    async def init_commands(self):
        logger.info("Loading Commands...")

    async def setup_hook(self) -> None:
        logger.info("Setting up client...")


    async def on_ready(self):
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        await self.init_commands()
