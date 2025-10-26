import discord
from discord import app_commands
from loguru import logger


class PermissionHandler:
    """Handler for managing Discord channel and user permissions"""

    def __init__(self, guild: discord.Guild):
        self.guild = guild

    def has_permission(
        self,
        member: discord.Member,
        permission: discord.Permissions,
        channel: discord.abc.GuildChannel | None = None,
    ) -> bool:
        """Check if a member has specific permissions"""
        if channel:
            perms = channel.permissions_for(member)
        else:
            perms = member.guild_permissions

        return all(
            getattr(perms, perm_name) for perm_name, value in permission if value
        )

    def has_role_permission(self, member: discord.Member, *role_ids: int) -> bool:
        """Check if member has any of the specified roles"""
        member_role_ids = {role.id for role in member.roles}
        return any(role_id in member_role_ids for role_id in role_ids)

    async def set_channel_permission(
        self,
        channel: discord.abc.GuildChannel,
        target: discord.Member | discord.Role,
        overwrite: discord.PermissionOverwrite,
    ) -> None:
        """Set permission overrides for a channel"""
        try:
            await channel.set_permissions(target, overwrite=overwrite)
            logger.info(f"Updated permissions for {target} in {channel.name}")
        except discord.Forbidden:
            logger.error(f"Missing permissions to update {channel.name}")
        except discord.HTTPException as e:
            logger.error(f"Failed to update permissions: {e}")

    async def clear_channel_permission(
        self,
        channel: discord.abc.GuildChannel,
        target: discord.Member | discord.Role,
    ) -> None:
        """Remove permission overrides for a channel"""
        try:
            await channel.set_permissions(target, overwrite=None)
            logger.info(f"Cleared permissions for {target} in {channel.name}")
        except discord.Forbidden:
            logger.error(f"Missing permissions to clear {channel.name}")
        except discord.HTTPException as e:
            logger.error(f"Failed to clear permissions: {e}")

    def get_channel_permissions(
        self,
        channel: discord.abc.GuildChannel,
        target: discord.Member | discord.Role,
    ) -> discord.Permissions:
        """Get effective permissions for a target in a channel"""
        if isinstance(target, discord.Member):
            return channel.permissions_for(target)
        else:
            # For roles, get the overwrite permissions
            overwrite = channel.overwrites_for(target)
            return discord.Permissions(
                **{perm: getattr(overwrite, perm) for perm, _ in discord.Permissions()}
            )

    async def lock_channel(
        self, channel: discord.abc.GuildChannel, role: discord.Role
    ) -> None:
        """Lock a channel by denying send permissions"""
        overwrite = discord.PermissionOverwrite(send_messages=False)
        await self.set_channel_permission(channel, role, overwrite)

    async def unlock_channel(
        self, channel: discord.abc.GuildChannel, role: discord.Role
    ) -> None:
        """Unlock a channel by allowing send permissions"""
        overwrite = discord.PermissionOverwrite(send_messages=True)
        await self.set_channel_permission(channel, role, overwrite)


class PermissionCheck:
    """Decorator-style permission checks for app commands"""

    @staticmethod
    def has_permissions(**perms: bool):
        """Check if user has specific permissions"""

        async def predicate(interaction: discord.Interaction) -> bool:
            if not isinstance(interaction.user, discord.Member):
                return False

            channel = interaction.channel
            if isinstance(channel, discord.abc.GuildChannel):
                user_perms = channel.permissions_for(interaction.user)
            else:
                user_perms = interaction.user.guild_permissions

            has_perms = all(
                getattr(user_perms, perm) for perm, value in perms.items() if value
            )

            if not has_perms:
                await interaction.response.send_message(
                    "You don't have permission to use this command.",
                    ephemeral=True,
                )
            return has_perms

        return app_commands.check(predicate)

    @staticmethod
    def has_any_role(*role_ids: int):
        """Check if user has any of the specified roles"""

        async def predicate(interaction: discord.Interaction) -> bool:
            if not isinstance(interaction.user, discord.Member):
                return False

            has_role = any(role.id in role_ids for role in interaction.user.roles)

            if not has_role:
                await interaction.response.send_message(
                    "You don't have the required role to use this command.",
                    ephemeral=True,
                )
            return has_role

        return app_commands.check(predicate)
