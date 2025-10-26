from enum import Enum
from dotenv import load_dotenv
from loguru import logger
import os


class ConfigVars(str, Enum):
    """Environment variable keys"""

    DISCORD_TOKEN = "DISCORD_TOKEN"
    GUILD_ID = "GUILD_ID"
    MONGO_URI = "MONGO_URI"
    DEBUG_MODE = "DEBUG_MODE"
    CHANNELS = "CHANNEL_COLLECTION"
    ROLES = "ROLE_COLLECTION"
    USERS = "USER_COLLECTION"


class ConfigInterface:
    """Interface class for handling environment variable loading"""

    def __init__(self) -> None:
        load_dotenv()

    def load_environment(self) -> None:
        logger.info("Reloading Environment")
        load_dotenv()

    def get_variable(self, variable: ConfigVars) -> str | None:
        logger.info(f"Fetching environment variable: {variable.value}")
        return os.getenv(variable.value, None)
