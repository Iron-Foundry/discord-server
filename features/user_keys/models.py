from datetime import datetime, timezone

from pydantic import BaseModel, Field


class UserKey(BaseModel):
    """A per-user API key granting access to the Foundry API."""

    discord_user_id: int
    discord_username: str
    guild_id: int
    guild_name: str
    key: str
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
