from dataclasses import dataclass, field


@dataclass
class HandlerStats:
    """Aggregated ticket handling statistics for a single staff member."""

    staff_id: int
    tickets_closed: int
    tickets_participated: int  # tickets with ≥1 message from this staff member
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


@dataclass
class SystemStats:
    """Aggregated system-wide ticket statistics for a given period."""

    total_opened: int  # tickets created in the period (any status)
    total_closed: int  # tickets created in period that are now closed/archived
    currently_open: int  # currently open tickets (no time filter)
    avg_response_seconds: float | None  # avg (first_staff_response_at - created_at)
    avg_resolution_seconds: float | None  # avg (closed_at - created_at)
    type_breakdown: dict[str, int]  # ticket_type → count of opened tickets in period
