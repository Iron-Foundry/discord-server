from __future__ import annotations

import os
from enum import Enum

from dotenv import load_dotenv
from loguru import logger


class ConfigVars(str, Enum):
    """Environment variable keys"""

    DISCORD_TOKEN = "DISCORD_TOKEN"
    GUILD_ID = "GUILD_ID"
    DATABASE_URL = "DATABASE_URL"
    DEBUG_MODE = "DEBUG_MODE"
    STAFF_ROLE_ID = "STAFF_ROLE_ID"
    SENIOR_STAFF_ROLE_ID = "SENIOR_STAFF_ROLE_ID"
    OWNER_ROLE_ID = "OWNER_ROLE_ID"
    MENTOR_ROLE_ID = "MENTOR_ROLE_ID"
    UPLOADTHING_SECRET = "UPLOADTHING_SECRET"
    API_BACKEND_URL = "API_BACKEND_URL"
    METRICS_API_KEY = "METRICS_API_KEY"


class ConfigInterface:
    """Interface class for handling environment variable loading"""

    def __init__(self) -> None:
        load_dotenv()

    def load_environment(self) -> None:
        logger.info("Reloading Environment")
        load_dotenv()

    def get_variable(self, variable: "ConfigVars | str") -> str | None:
        key = variable.value if isinstance(variable, ConfigVars) else variable
        logger.info(f"Fetching environment variable: {key}")
        return os.getenv(key, None)


async def get_staff_role_ids() -> dict[str, int | None]:
    """Return staff role IDs from Config DB, falling back to env vars.

    Reads from the shared 'discord_roles' config key (guild_id=0) written by
    the web admin UI. Falls back to env vars so the bot works before first save.
    """
    from sqlalchemy import select

    from core.db import get_session_factory
    from core.db.models import Config

    data: dict = {}
    try:
        async with get_session_factory()() as session:
            result = await session.execute(
                select(Config.value).where(
                    Config.guild_id == 0, Config.key == "discord_roles"
                )
            )
            data = result.scalar_one_or_none() or {}
    except Exception:
        pass

    def _resolve(db_val: str, env_key: str) -> int | None:
        val = db_val or os.getenv(env_key)
        return int(val) if val else None

    return {
        "staff_role_id": _resolve(data.get("staff_role_id", ""), "STAFF_ROLE_ID"),
        "senior_staff_role_id": _resolve(
            data.get("senior_staff_role_id", ""), "SENIOR_STAFF_ROLE_ID"
        ),
        "owner_role_id": _resolve(data.get("owner_role_id", ""), "OWNER_ROLE_ID"),
        "mentor_role_id": _resolve(data.get("mentor_role_id", ""), "MENTOR_ROLE_ID"),
    }
