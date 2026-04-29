"""PostgreSQL persistence for the party system."""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta, timezone

from loguru import logger
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from core.db.models import Config, PartyDB, PartyMemberDB

_PANEL_KEY = "party_panel"
_PING_ROLES_KEY = "party_ping_roles"
_GLOBAL_GUILD_ID = 0

_WORDLIST = [
    "abyssal", "ancient", "anvil", "arcane", "armadyl", "arrow", "axe",
    "bandos", "barrows", "berserker", "brimstone", "bronze", "brutal",
    "cannonball", "chaos", "chimera", "coffer", "coral", "crystal",
    "dagannoth", "dark", "death", "defender", "demon", "divine", "dragon",
    "dragonfire", "dusk", "dwarf", "elder", "eternal", "fighter", "fire",
    "flask", "forest", "fury", "ghost", "giant", "gloves", "goblin",
    "golem", "granite", "guthix", "hammer", "helm", "hunter", "hydra",
    "infernal", "iron", "jad", "justiciar", "karambwan", "kraken", "lance",
    "lava", "lobster", "magic", "manta", "maple", "marble", "master",
    "monk", "mortar", "mud", "mystic", "nature", "needle", "nex",
    "nightmare", "oak", "obsidian", "onyx", "oracle", "pegasian", "pickaxe",
    "prayer", "quartz", "quest", "ranger", "rapier", "rune", "sacred",
    "saradomin", "scimitar", "seed", "shark", "shield", "silver", "skeleton",
    "slayer", "smoke", "snow", "soul", "spade", "spectral", "staff", "steel",
    "storm", "sword", "teak", "thorn", "titan", "toad", "tome", "torch",
    "torva", "toxic", "trident", "tuna", "twisted", "vanguard", "venom",
    "vigour", "viper", "void", "vorkath", "warhammer", "warped", "water",
    "whip", "willow", "wings", "witch", "wolf", "wrath", "yew",
    "zamorak", "zenyte", "zulrah",
]


def _generate_hub_code() -> str:
    return "-".join(random.choices(_WORDLIST, k=3))


def _with_members(q):  # type: ignore[no-untyped-def]
    return q.options(selectinload(PartyDB.members))


class PgPartyRepository:
    """PostgreSQL persistence for the party panel and party records."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        self._factory = session_factory

    # ── Queries ────────────────────────────────────────────────────────────

    async def get_active_parties(self) -> list[PartyDB]:
        """Return all non-closed parties ordered by expiry (soonest first)."""
        async with self._factory() as session:
            result = await session.execute(
                _with_members(
                    select(PartyDB)
                    .where(PartyDB.status != "closed")
                    .order_by(PartyDB.expires_at.asc())
                )
            )
            return list(result.scalars().all())

    async def get_user_active_party(self, user_id: str) -> PartyDB | None:
        """Return any active party the user belongs to (as leader or member)."""
        async with self._factory() as session:
            result = await session.execute(
                _with_members(
                    select(PartyDB)
                    .join(
                        PartyMemberDB,
                        (PartyMemberDB.party_id == PartyDB.id)
                        & (PartyMemberDB.user_id == user_id),
                    )
                    .where(PartyDB.status != "closed")
                )
            )
            return result.scalar_one_or_none()

    async def add_member(
        self,
        party_id: str,
        *,
        user_id: str,
        username: str,
        rsn: str | None,
    ) -> PartyDB | None:
        """Add a member to the party and return the updated party."""
        now = datetime.now(timezone.utc)
        async with self._factory() as session:
            result = await session.execute(
                _with_members(
                    select(PartyDB).where(PartyDB.id == party_id)
                )
            )
            party = result.scalar_one_or_none()
            if not party or party.status == "closed":
                return None
            if any(m.user_id == user_id for m in party.members):
                raise ValueError("already_member")
            member = PartyMemberDB(
                id=str(uuid.uuid4()),
                party_id=party_id,
                user_id=user_id,
                username=username,
                rsn=rsn,
                joined_at=now,
            )
            session.add(member)
            await session.flush()
            await session.refresh(party, attribute_names=["members"])
            # Update full/open status
            if len(party.members) >= party.max_size:
                party.status = "full"
            await session.commit()
            logger.info(
                "PartyRepository: {} joined party {}", user_id, party_id
            )
            return party

    async def get_leader_party(self, leader_id: str) -> PartyDB | None:
        """Return the active party led by this user, if any."""
        async with self._factory() as session:
            result = await session.execute(
                _with_members(
                    select(PartyDB).where(
                        PartyDB.leader_id == leader_id,
                        PartyDB.status != "closed",
                    )
                )
            )
            return result.scalar_one_or_none()

    async def get_user_rsn(self, discord_user_id: str) -> str | None:
        """Return the linked RSN for a Discord user, or None."""
        from core.db.models import User

        async with self._factory() as session:
            result = await session.execute(
                select(User.rsn).where(
                    User.discord_user_id == int(discord_user_id)
                )
            )
            return result.scalar_one_or_none()

    async def get_ping_roles(self) -> list[dict]:
        """Return the configured party ping roles from global config."""
        async with self._factory() as session:
            result = await session.execute(
                select(Config.value).where(
                    Config.guild_id == _GLOBAL_GUILD_ID,
                    Config.key == _PING_ROLES_KEY,
                )
            )
            data = result.scalar_one_or_none() or {}
            return data.get("roles", [])  # type: ignore[return-value]

    # ── Mutations ──────────────────────────────────────────────────────────

    async def create_party(
        self,
        *,
        leader_id: str,
        leader_username: str,
        leader_rsn: str | None,
        activity: str,
        description: str | None,
        vibe: str,
        max_size: int,
        ttl_hours: float,
        ping_role_ids: list[str],
    ) -> PartyDB:
        """Create a party record and add the leader as first member."""
        now = datetime.now(timezone.utc)
        party_id = str(uuid.uuid4())
        party = PartyDB(
            id=party_id,
            leader_id=leader_id,
            leader_username=leader_username,
            leader_rsn=leader_rsn,
            activity=activity,
            description=description,
            vibe=vibe,
            max_size=max_size,
            ping_role_ids=ping_role_ids,
            hub_code=_generate_hub_code(),
            status="open",
            created_at=now,
            expires_at=now + timedelta(hours=ttl_hours),
        )
        member = PartyMemberDB(
            id=str(uuid.uuid4()),
            party_id=party_id,
            user_id=leader_id,
            username=leader_username,
            rsn=leader_rsn,
            joined_at=now,
        )
        async with self._factory() as session:
            session.add(party)
            session.add(member)
            await session.commit()
            await session.refresh(party, attribute_names=["members"])
            logger.info("PartyRepository: created party {} ({})", party_id, activity)
            return party

    async def close_party(self, party_id: str) -> PartyDB | None:
        """Mark a party as closed. Returns the updated party or None."""
        async with self._factory() as session:
            result = await session.execute(
                _with_members(
                    select(PartyDB).where(PartyDB.id == party_id)
                )
            )
            party = result.scalar_one_or_none()
            if party and party.status != "closed":
                party.status = "closed"
                await session.commit()
                logger.info("PartyRepository: closed party {}", party_id)
            return party

    # ── Panel config ───────────────────────────────────────────────────────

    async def save_panel_config(
        self, guild_id: int, channel_id: int, message_id: int
    ) -> None:
        """Persist the panel channel and message IDs."""
        value = {"channel_id": channel_id, "message_id": message_id}
        async with self._factory() as session:
            stmt = (
                pg_insert(Config)
                .values(guild_id=guild_id, key=_PANEL_KEY, value=value)
                .on_conflict_do_update(
                    index_elements=["guild_id", "key"],
                    set_={"value": value},
                )
            )
            await session.execute(stmt)
            await session.commit()

    async def get_panel_config(
        self, guild_id: int
    ) -> tuple[int, int] | None:
        """Return (channel_id, message_id) or None if not configured."""
        async with self._factory() as session:
            result = await session.execute(
                select(Config.value).where(
                    Config.guild_id == guild_id,
                    Config.key == _PANEL_KEY,
                )
            )
            data = result.scalar_one_or_none()
            if data:
                return (int(data["channel_id"]), int(data["message_id"]))
            return None

    async def clear_panel_config(self, guild_id: int) -> None:
        """Remove stored panel config (e.g. message was deleted)."""
        from sqlalchemy import delete

        async with self._factory() as session:
            await session.execute(
                delete(Config).where(
                    Config.guild_id == guild_id,
                    Config.key == _PANEL_KEY,
                )
            )
            await session.commit()
