from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands

from command_infra.checks import handle_check_failure, is_senior_staff, is_staff
from command_infra.help_registry import HelpEntry, HelpGroup, HelpRegistry

if TYPE_CHECKING:
    from action_log.service import ActionLogService


def register_help(registry: HelpRegistry) -> None:
    """Register help entries for the actionlog command group."""
    registry.add_group(
        HelpGroup(
            name="actionlog",
            description="Configure and manage the action log",
            commands=[
                HelpEntry(
                    "/actionlog status",
                    "Show the action log status",
                    "Staff",
                ),
                HelpEntry(
                    "/actionlog setup <forum>",
                    "Set up the action log forum channel",
                    "Senior Staff",
                ),
                HelpEntry(
                    "/actionlog toggle",
                    "Enable or disable the action log",
                    "Senior Staff",
                ),
                HelpEntry(
                    "/actionlog ignore channel <channel>",
                    "Ignore a channel from action logging",
                    "Senior Staff",
                ),
                HelpEntry(
                    "/actionlog ignore thread <thread_id>",
                    "Ignore a thread from action logging",
                    "Senior Staff",
                ),
                HelpEntry(
                    "/actionlog ignore category <category>",
                    "Ignore all channels in a category from action logging",
                    "Senior Staff",
                ),
                HelpEntry(
                    "/actionlog unignore channel <channel>",
                    "Remove a channel from the ignore list",
                    "Senior Staff",
                ),
                HelpEntry(
                    "/actionlog unignore thread <thread_id>",
                    "Remove a thread from the ignore list",
                    "Senior Staff",
                ),
                HelpEntry(
                    "/actionlog unignore category <category>",
                    "Remove a category from the ignore list",
                    "Senior Staff",
                ),
                HelpEntry(
                    "/actionlog unignore category <category>",
                    "Remove a category from the ignore list",
                    "Senior Staff",
                ),
            ],
        )
    )


class IgnoreGroup(
    app_commands.Group, name="ignore", description="Add to the ignore list"
):
    """Subgroup for ignore commands."""

    def __init__(self, service: ActionLogService) -> None:
        super().__init__()
        self._service = service

    async def on_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        await handle_check_failure(interaction, error)

    @app_commands.command(
        name="channel", description="Ignore a channel from action logging"
    )
    @app_commands.describe(channel="The channel to ignore")
    @is_senior_staff()
    async def ignore_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        added = await self._service.add_ignore(channel.id, is_thread=False)
        if added:
            await interaction.response.send_message(
                f"Now ignoring {channel.mention} in action logs.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"{channel.mention} is already ignored.", ephemeral=True
            )

    @app_commands.command(
        name="category",
        description="Ignore all channels in a category from action logging",
    )
    @app_commands.describe(category="The category to ignore")
    @is_senior_staff()
    async def ignore_category(
        self, interaction: discord.Interaction, category: discord.CategoryChannel
    ) -> None:
        added = await self._service.add_ignore_category(category.id)
        if added:
            await interaction.response.send_message(
                f"Now ignoring all channels in **{category.name}** in action logs.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"**{category.name}** is already ignored.", ephemeral=True
            )

    @app_commands.command(
        name="thread", description="Ignore a thread from action logging"
    )
    @app_commands.describe(thread_id="The ID of the thread to ignore")
    @is_senior_staff()
    async def ignore_thread(
        self, interaction: discord.Interaction, thread_id: str
    ) -> None:
        try:
            tid = int(thread_id)
        except ValueError:
            await interaction.response.send_message(
                "Invalid thread ID — must be a numeric snowflake.", ephemeral=True
            )
            return
        added = await self._service.add_ignore(tid, is_thread=True)
        if added:
            await interaction.response.send_message(
                f"Now ignoring thread `{thread_id}` in action logs.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"Thread `{thread_id}` is already ignored.", ephemeral=True
            )


class UnignoreGroup(
    app_commands.Group, name="unignore", description="Remove from the ignore list"
):
    """Subgroup for unignore commands."""

    def __init__(self, service: ActionLogService) -> None:
        super().__init__()
        self._service = service

    async def on_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        await handle_check_failure(interaction, error)

    @app_commands.command(
        name="channel", description="Remove a channel from the ignore list"
    )
    @app_commands.describe(channel="The channel to unignore")
    @is_senior_staff()
    async def unignore_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        removed = await self._service.remove_ignore(channel.id, is_thread=False)
        if removed:
            await interaction.response.send_message(
                f"{channel.mention} removed from action log ignore list.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"{channel.mention} was not in the ignore list.", ephemeral=True
            )

    @app_commands.command(
        name="category", description="Remove a category from the ignore list"
    )
    @app_commands.describe(category="The category to unignore")
    @is_senior_staff()
    async def unignore_category(
        self, interaction: discord.Interaction, category: discord.CategoryChannel
    ) -> None:
        removed = await self._service.remove_ignore_category(category.id)
        if removed:
            await interaction.response.send_message(
                f"**{category.name}** removed from action log ignore list.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"**{category.name}** was not in the ignore list.", ephemeral=True
            )

    @app_commands.command(
        name="thread", description="Remove a thread from the ignore list"
    )
    @app_commands.describe(thread_id="The ID of the thread to unignore")
    @is_senior_staff()
    async def unignore_thread(
        self, interaction: discord.Interaction, thread_id: str
    ) -> None:
        try:
            tid = int(thread_id)
        except ValueError:
            await interaction.response.send_message(
                "Invalid thread ID — must be a numeric snowflake.", ephemeral=True
            )
            return
        removed = await self._service.remove_ignore(tid, is_thread=True)
        if removed:
            await interaction.response.send_message(
                f"Thread `{thread_id}` removed from action log ignore list.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"Thread `{thread_id}` was not in the ignore list.", ephemeral=True
            )


class ActionLogGroup(
    app_commands.Group, name="actionlog", description="Action log management"
):
    """Slash command group for managing the action log service."""

    def __init__(self, service: ActionLogService) -> None:
        super().__init__()
        self._service = service
        self.add_command(IgnoreGroup(service=service))
        self.add_command(UnignoreGroup(service=service))

    async def on_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        await handle_check_failure(interaction, error)

    # ------------------------------------------------------------------
    # /actionlog setup <forum>
    # ------------------------------------------------------------------

    @app_commands.command(
        name="setup", description="Set up the action log forum channel"
    )
    @app_commands.describe(forum="The forum channel to use for action log threads")
    @is_senior_staff()
    async def setup(
        self, interaction: discord.Interaction, forum: discord.ForumChannel
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        config = await self._service.setup_forum(forum)
        thread_count = len(config.thread_ids)
        await interaction.followup.send(
            f"Action log configured in {forum.mention} — {thread_count} threads ready.",
            ephemeral=True,
        )

    # ------------------------------------------------------------------
    # /actionlog status
    # ------------------------------------------------------------------

    @app_commands.command(name="status", description="Show the action log status")
    @is_staff()
    async def status(self, interaction: discord.Interaction) -> None:
        config = self._service.config
        embed = discord.Embed(title="Action Log Status", color=discord.Color.blurple())

        if not config:
            embed.description = (
                "Action log is not configured. Use `/actionlog setup` to get started."
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed.add_field(
            name="State",
            value="Enabled" if config.enabled else "Disabled",
            inline=True,
        )
        forum_mention = (
            f"<#{config.forum_channel_id}>" if config.forum_channel_id else "Not set"
        )
        embed.add_field(name="Forum", value=forum_mention, inline=True)
        embed.add_field(name="Threads", value=str(len(config.thread_ids)), inline=True)

        if config.ignored_category_ids:
            embed.add_field(
                name="Ignored Categories",
                value=" ".join(f"<#{cid}>" for cid in config.ignored_category_ids),
                inline=False,
            )
        if config.ignored_channel_ids:
            embed.add_field(
                name="Ignored Channels",
                value=" ".join(f"<#{cid}>" for cid in config.ignored_channel_ids),
                inline=False,
            )
        if config.ignored_thread_ids:
            embed.add_field(
                name="Ignored Threads",
                value=" ".join(f"`{tid}`" for tid in config.ignored_thread_ids),
                inline=False,
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------
    # /actionlog toggle
    # ------------------------------------------------------------------

    @app_commands.command(name="toggle", description="Enable or disable the action log")
    @is_senior_staff()
    async def toggle(self, interaction: discord.Interaction) -> None:
        config = self._service.config
        if not config:
            await interaction.response.send_message(
                "Action log is not configured yet. Run `/actionlog setup` first.",
                ephemeral=True,
            )
            return
        new_state = not config.enabled
        changed = await self._service.set_enabled(new_state)
        if changed:
            state_str = "enabled" if new_state else "disabled"
            await interaction.response.send_message(
                f"Action log is now **{state_str}**.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "Action log state unchanged.", ephemeral=True
            )
