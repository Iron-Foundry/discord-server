from pydantic import BaseModel, Field


class JoinRoleConfig(BaseModel):
    """Persisted configuration for join roles."""

    guild_id: int
    role_ids: list[int] = Field(default_factory=list)
