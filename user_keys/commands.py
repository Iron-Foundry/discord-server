from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import discord
from discord import app_commands
from loguru import logger

if TYPE_CHECKING:
    from user_keys.service import UserKeyService


def make_userkey_command(service: UserKeyService) -> app_commands.Command:  # type: ignore[type-arg]
    """Return the /userkey slash command with the service injected."""

    @app_commands.command(
        name="userkey",
        description="View or regenerate your Foundry API key for the RuneLite plugin",
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
                "New API key generated. Enter this in the RuneLite plugin "
                "(Advanced Settings → Verification Code):\n"
                f"```\n{user_key.key}\n```"
                "Your previous key has been invalidated.",
                ephemeral=True,
            )
        else:
            user_key = await service.get_key(interaction.user)
            if user_key is None:
                await interaction.response.send_message(
                    "You don't have an API key yet. "
                    "Use `/userkey new` to generate one.",
                    ephemeral=True,
                )
                return
            await interaction.response.send_message(
                f"Your current API key:\n```\n{user_key.key}\n```",
                ephemeral=True,
            )

    return userkey  # type: ignore[return-value]
