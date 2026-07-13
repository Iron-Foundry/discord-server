from __future__ import annotations

from core.common.ranks import OsrsRank

_GEM_RANKS: frozenset[str] = frozenset(r.value for r in OsrsRank)
_GEM_RANK_ORDER: list[str] = list(reversed([r.value for r in OsrsRank]))


def is_gem_rank(rank: str | None) -> bool:
    return rank in _GEM_RANKS


def highest_gem_rank(role_ids: list[str], role_to_rank: dict[str, str]) -> str | None:
    """Return the highest gem rank found among role_ids, or None."""
    held = {
        role_to_rank[rid] for rid in role_ids if role_to_rank.get(rid) in _GEM_RANKS
    }
    for rank in _GEM_RANK_ORDER:
        if rank in held:
            return rank
    return None
