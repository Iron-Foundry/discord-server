import asyncio

from loguru import logger

from discord_client import DiscordClient
from config import ConfigInterface, ConfigVars


async def main():
    logger.info("Starting Service: Discord-Server")
    config = ConfigInterface()
    discord_token, debug_mode = (
        config.get_variable(ConfigVars.discord_token),
        config.get_variable(ConfigVars.debug_mode),
    )
    if discord_token is not None:
        client = DiscordClient(debug=debug_mode)
        await client.start(token=discord_token)

    logger.warning("Environment file or token key missing.")
    exit(code=1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting Down Discord-Server")
        exit(code=0)
