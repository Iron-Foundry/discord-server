from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar

import discord

from docket.models import DocketPanelRecord, PanelType

if TYPE_CHECKING:
    pass


class DocketPanel(ABC):
    """Abstract base class for all docket panels."""

    panel_type: ClassVar[PanelType]
    display_name: ClassVar[str]
    refresh_interval_seconds: ClassVar[int]  # 0 = manual-only

    @abstractmethod
    async def build_embeds(self, record: DocketPanelRecord) -> list[discord.Embed]:
        """Build the list of embeds representing this panel's current state."""
        ...

    def build_view(
        self, record: DocketPanelRecord, service: Any
    ) -> discord.ui.View | None:
        """Build an optional interactive view for this panel. Default: None."""
        return None

    async def refresh(self, record: DocketPanelRecord) -> DocketPanelRecord:
        """Fetch fresh data and update the record. Default: no-op (manual panels)."""
        return record
