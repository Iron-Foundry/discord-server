from __future__ import annotations

import asyncio

import discord
from loguru import logger


class MessageThrottle:
    """Rate-limited queue for sending Discord embeds to forum threads."""

    def __init__(self, rate: float = 1.0) -> None:
        self._rate = rate
        self._queue: asyncio.Queue[tuple[int, discord.Embed]] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None
        self._client: discord.Client | None = None

    def start(self, client: discord.Client) -> None:
        """Spawn the consumer task."""
        self._client = client
        self._task = asyncio.create_task(self._consumer(), name="action_log_throttle")
        logger.info(f"MessageThrottle started (rate={self._rate}/s)")

    def stop(self) -> None:
        """Cancel the consumer task."""
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("MessageThrottle stopped")

    async def enqueue(self, thread_id: int, embed: discord.Embed) -> None:
        """Add an embed to the send queue."""
        await self._queue.put((thread_id, embed))

    async def _consumer(self) -> None:
        while True:
            try:
                thread_id, embed = await self._queue.get()
                await self._send(thread_id, embed)
                await asyncio.sleep(1.0 / self._rate)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"MessageThrottle consumer error: {e}")

    async def _send(self, thread_id: int, embed: discord.Embed) -> None:
        if self._client is None:
            return
        try:
            channel = self._client.get_channel(thread_id)
            if not isinstance(channel, discord.Thread):
                logger.warning(
                    f"MessageThrottle: {thread_id} not found or not a thread"
                )
                return
            await channel.send(embed=embed)
        except discord.NotFound:
            logger.warning(f"MessageThrottle: thread {thread_id} not found")
        except discord.HTTPException as e:
            logger.warning(
                f"MessageThrottle: failed to send to thread {thread_id}: {e}"
            )
