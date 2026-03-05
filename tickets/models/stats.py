from dataclasses import dataclass, field


@dataclass
class HandlerStats:
    """Aggregated ticket handling statistics for a single staff member."""

    staff_id: int
    tickets_closed: int
    avg_response_seconds: float | None  # first_staff_response_at - created_at
    avg_resolution_seconds: float | None  # closed_at - created_at
    type_breakdown: dict[str, int] = field(default_factory=dict)  # type → count


@dataclass
class LeaderboardEntry:
    """A single ranked entry in the ticket handler leaderboard."""

    rank: int
    staff_id: int
    tickets_closed: int
    avg_resolution_seconds: float | None
