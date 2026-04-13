from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import discord
from discord import app_commands
from loguru import logger

if TYPE_CHECKING:
    from features.user_keys.service import UserKeyService


def make_userkey_command(service: UserKeyService) -> app_commands.Command:  # type: ignore[type-arg]
    """Return the /userkey slash command with the service injected."""

    @app_commands.command(
        name="userkey",
        description="View or regenerate your Foundry key (RuneLite plugin and website login)",
    )
    @app_commands.describe(
        action="Omit to view your current key; choose 'new' to generate a fresh one"
    )
    async def userkey(
        interaction: discord.Interaction,
        action: Literal["view", "new"] = "view",
    ) -> None:
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "This command can only be used inside the server.",
                ephemeral=True,
            )
            return

        logger.debug(f"userkey: action={action!r} invoked by {interaction.user}")

        if action == "new":
            user_key = await service.generate_key(interaction.user)
            await interaction.response.send_message(
                "New key generated. Use this in the RuneLite plugin "
                "(Advanced Settings → Verification Code) and to log in on the website:\n"
                f"```\n{user_key.key}\n```"
                "Your previous key has been invalidated.",
                ephemeral=True,
            )
        else:
            user_key = await service.get_key(interaction.user)
            if user_key is None:
                await interaction.response.send_message(
                    "You don't have a key yet. "
                    "Use `/userkey new` to generate one.",
                    ephemeral=True,
                )
                return
            await interaction.response.send_message(
                f"Your current key:\n```\n{user_key.key}\n```",
                ephemeral=True,
            )

    return userkey  # type: ignore[return-value]


def make_privacy_command(service: UserKeyService) -> app_commands.Command:  # type: ignore[type-arg]
    """Return the /privacy slash command with the service injected."""

    @app_commands.command(
        name="privacy",
        description="Control whether your stats, loot, and PBs are stored by the Foundry",
    )
    @app_commands.describe(action="opt-out to stop storing your data; opt-in to resume")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="opt-out", value="opt-out"),
            app_commands.Choice(name="opt-in", value="opt-in"),
        ]
    )
    async def privacy(
        interaction: discord.Interaction,
        action: str,
    ) -> None:
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "This command can only be used inside the server.",
                ephemeral=True,
            )
            return

        opt_out = action == "opt-out"
        logger.debug(f"privacy: action={action!r} invoked by {interaction.user}")
        await service.set_stats_opt_out(interaction.user, opt_out)

        if opt_out:
            await interaction.response.send_message(
                "Opted out. Your stats, loot, and PBs will no longer be stored by the "
                "Foundry. Existing data is not deleted — contact staff if you want it "
                "removed.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "Opted back in. Your stats, loot, and PBs will be stored again.",
                ephemeral=True,
            )

    return privacy  # type: ignore[return-value]
