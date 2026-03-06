from __future__ import annotations

import discord
from loguru import logger

from core.service_base import Service
from join_roles.models import JoinRoleConfig
from join_roles.repository import MongoJoinRoleRepository


class JoinRoleService(Service):
    """Manages roles automatically assigned when a member joins the server."""

    def __init__(self, guild: discord.Guild, repo: MongoJoinRoleRepository) -> None:
        self._guild = guild
        self._repo = repo
        self._config: JoinRoleConfig | None = None

    async def initialize(self) -> None:
        """Load config from DB and ensure indexes."""
        await self._repo.ensure_indexes()
        self._config = await self._repo.get_config(self._guild.id)
        if self._config is None:
            logger.debug("JoinRoleService: no config found, creating default")
            self._config = JoinRoleConfig(guild_id=self._guild.id)
        else:
            logger.debug(
                f"JoinRoleService: loaded config with {len(self._config.role_ids)}"
                " role(s)"
            )
        logger.info("JoinRoleService: initialized")

    async def add_role(self, role_id: int) -> bool:
        """Add a role to the join list. Returns True if added, False if already present."""
        assert self._config is not None
        if role_id in self._config.role_ids:
            logger.debug(f"JoinRoleService: role {role_id} already in join list")
            return False
        self._config.role_ids.append(role_id)
        await self._repo.save_config(self._config)
        logger.debug(f"JoinRoleService: added role {role_id}")
        return True

    async def remove_role(self, role_id: int) -> bool:
        """Remove a role from the join list. Returns True if removed, False if not found."""
        assert self._config is not None
        if role_id not in self._config.role_ids:
            logger.debug(f"JoinRoleService: role {role_id} not in join list")
            return False
        self._config.role_ids.remove(role_id)
        await self._repo.save_config(self._config)
        logger.debug(f"JoinRoleService: removed role {role_id}")
        return True

    @property
    def role_ids(self) -> list[int]:
        """Return the list of configured join role IDs."""
        if self._config is None:
            return []
        return list(self._config.role_ids)

    async def assign_roles(self, member: discord.Member) -> None:
        """Assign all configured join roles to a new member."""
        if self._config is None or not self._config.role_ids:
            logger.debug(
                f"JoinRoleService: no roles to assign for {member.display_name}"
            )
            return
        logger.debug(
            f"JoinRoleService: assigning {len(self._config.role_ids)} role(s)"
            f" to {member.display_name}"
        )
        for role_id in self._config.role_ids:
            role = self._guild.get_role(role_id)
            if role is None:
                logger.warning(
                    f"JoinRoleService: role {role_id} not found in guild"
                    f" {self._guild.id}"
                )
                continue
            try:
                await member.add_roles(role, reason="Join role assignment")
                logger.debug(
                    f"JoinRoleService: assigned {role.name} to {member.display_name}"
                )
            except discord.HTTPException as e:
                logger.error(
                    f"JoinRoleService: failed to assign role {role_id} to {member}: {e}"
                )
