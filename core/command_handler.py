from collections.abc import Callable
from typing import Any, Optional
import discord
from discord import app_commands


class FoundryCommandTree(app_commands.CommandTree):
    """CommandTree subclass with friendly error responses."""

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        """Handle tree-level errors for standalone commands and context menus."""
        if isinstance(error, app_commands.CommandNotFound):
            await interaction.response.send_message(
                "Unknown command. Use `/help` to see available commands.",
                ephemeral=True,
            )
            return
        if isinstance(error, app_commands.CheckFailure):
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "You don't have permission to use this command.", ephemeral=True
                )
            return
        await super().on_error(interaction, error)


class CommandHandler:
    _instance: Optional["CommandHandler"] = None
    _tree: Optional[app_commands.CommandTree] = None
    _guild: Optional[discord.Guild] = None
    _client: Optional[discord.Client] = None

    def __new__(cls, client: Optional[discord.Client] = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, client: Optional[discord.Client] = None) -> None:
        if self._tree is None and client is not None:
            self._tree = FoundryCommandTree(client)
            self._client = client

    @property
    def tree(self) -> app_commands.CommandTree:
        if self._tree is None:
            raise RuntimeError("CommandTree not initialized, pass a client first.")

        return self._tree

    @property
    def client(self) -> discord.Client:
        if self._client is None:
            raise RuntimeError("Client not initialized, pass a client first.")

        return self._client

    @property
    def guild(self):
        return self._guild

    @guild.setter
    def guild(self, guild: discord.Guild) -> None:
        self._guild = guild

    def add_command(self, name: str, description: str):
        """Decorator to add a command to the tree"""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            command = app_commands.command(name=name, description=description)(func)

            if self._guild:
                self.tree.add_command(command, guild=self._guild)
            else:
                self.tree.add_command(command)

            return func

        return decorator

    def add_group(
        self, name: str, description: str, parent: Optional[app_commands.Group] = None
    ) -> app_commands.Group:
        """Create and add a command group"""
        group = app_commands.Group(name=name, description=description)

        if parent:
            parent.add_command(group)
        else:
            if self._guild:
                self.tree.add_command(group, guild=self._guild)
            else:
                self.tree.add_command(group)

        return group

    async def sync(self, _global: bool = False) -> list[app_commands.AppCommand]:
        """Sync commands with Discord"""
        if not _global:
            return await self.tree.sync(guild=self._guild)
        else:
            return await self.tree.sync()
