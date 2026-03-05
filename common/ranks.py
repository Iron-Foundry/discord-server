from enum import Enum

import discord


class OsrsRank(str, Enum):
    SAPPHIRE = "Sapphire"
    EMERALD = "Emerald"
    RUBY = "Ruby"
    DIAMOND = "Diamond"
    DRAGONSTONE = "Dragonstone"
    ONYX = "Onyx"
    ZENYTE = "Zenyte"


RANK_OPTIONS: list[discord.SelectOption] = [
    discord.SelectOption(label=rank.value, value=rank.value) for rank in OsrsRank
]
