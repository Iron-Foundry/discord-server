from pydantic import BaseModel


class BroadcastConfig(BaseModel):
    """Persisted configuration for the broadcast service."""

    guild_id: int
    role_id: int | None = None
