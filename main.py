import asyncio

from loguru import logger

from core.discord_client import DiscordClient
from core.config import ConfigInterface, ConfigVars
from core.metrics_reporter import MetricsReporter


async def main():
    logger.info("Starting Service: Discord-Server")
    config = ConfigInterface()
    discord_token = config.get_variable(ConfigVars.DISCORD_TOKEN)
    debug_mode = config.get_variable(ConfigVars.DEBUG_MODE)

    if discord_token is None:
        logger.warning("Environment file or DISCORD_TOKEN key missing.")
        exit(code=1)

    client = DiscordClient(debug=debug_mode == "true")
    reporter = MetricsReporter(client)

    try:
        await client.login(token=discord_token)
        await reporter.start()
        await client.connect()
    finally:
        await reporter.stop()
        await client.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting Down Discord-Server")
        exit(code=0)
