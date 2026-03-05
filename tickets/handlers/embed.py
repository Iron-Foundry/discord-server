import discord
from datetime import datetime, UTC


class EmbedBuilder:
    """Fluent builder for discord.Embed with Discord API limit validation."""

    def __init__(self, title: str = "", description: str = "") -> None:
        self._title: str = ""
        self._description: str = ""
        self._color: discord.Color = discord.Color.blurple()
        self._fields: list[dict] = []
        self._footer: str | None = None
        self._thumbnail: str | None = None
        self._timestamp: datetime | None = None

        if title:
            self.set_title(title)
        if description:
            self.set_description(description)

    @property
    def title(self) -> str:
        return self._title

    @property
    def description(self) -> str:
        return self._description

    @property
    def fields(self) -> list[dict]:
        return self._fields

    def set_title(self, value: str) -> "EmbedBuilder":
        if len(value) > 256:
            raise ValueError("Embed title must be 256 characters or fewer")
        self._title = value
        return self

    def set_description(self, value: str) -> "EmbedBuilder":
        if len(value) > 4096:
            raise ValueError("Embed description must be 4096 characters or fewer")
        self._description = value
        return self

    def set_color(self, color: discord.Color) -> "EmbedBuilder":
        self._color = color
        return self

    def set_footer(self, text: str) -> "EmbedBuilder":
        self._footer = text
        return self

    def set_thumbnail(self, url: str) -> "EmbedBuilder":
        self._thumbnail = url
        return self

    def set_timestamp(self, ts: datetime | None = None) -> "EmbedBuilder":
        self._timestamp = ts or datetime.now(UTC)
        return self

    def add_field(self, name: str, value: str, inline: bool = True) -> "EmbedBuilder":
        if len(self._fields) >= 25:
            raise ValueError("Embed cannot have more than 25 fields")
        self._fields.append({"name": name, "value": value, "inline": inline})
        return self

    def clear_fields(self) -> "EmbedBuilder":
        self._fields = []
        return self

    def build(self) -> discord.Embed:
        embed = discord.Embed(
            title=self._title or None,
            description=self._description or None,
            color=self._color,
            timestamp=self._timestamp,
        )
        for field in self._fields:
            embed.add_field(
                name=field["name"], value=field["value"], inline=field["inline"]
            )
        if self._footer:
            embed.set_footer(text=self._footer)
        if self._thumbnail:
            embed.set_thumbnail(url=self._thumbnail)
        return embed
