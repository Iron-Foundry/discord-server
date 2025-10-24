from enum import StrEnum
import os

from loguru import logger
from dotenv import load_dotenv


class ConfigVars(StrEnum):
    discord_token: str = "DISCORD_TOKEN"
    guild_id: str = "GUILD_ID"
    mongo_uri: str = "MONGO_URI"
    debug_mode: str = "DEBUG_MODE"
    channels: str = "CHANNEL_COLLECTION"
    roles: str = "ROLE_COLLECTION"
    users: str = "USER_COLLECTION"


class ConfigInterface:
    """Interface class for handling environment variable loading"""

    def __init__(self) -> None:
        load_dotenv()

    def load_environment(self):
        logger.info("Reloading Environment")
        load_dotenv()

    def get_variable(self, variable: ConfigVars) -> str | None:
        logger.info(f"Fetching environment variable: {variable.value}")
        return os.getenv(variable.value, None)
