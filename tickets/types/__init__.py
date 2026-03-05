from __future__ import annotations

from typing import TYPE_CHECKING

from .general import GeneralTicket
from .rankup import RankupTicket, RankupModal
from .join_cc import JoinCCTicket
from .apply_staff import ApplyStaffTicket, ApplyStaffModal
from .apply_mentor import ApplyMentorTicket, ApplyMentorModal
from .sensitive import SensitiveTicket
from .contact_mentor import ContactMentorTicket, ContactMentorModal

if TYPE_CHECKING:
    from tickets.ticket_service import TicketService

__all__ = [
    "GeneralTicket",
    "RankupTicket",
    "RankupModal",
    "JoinCCTicket",
    "ApplyStaffTicket",
    "ApplyStaffModal",
    "ApplyMentorTicket",
    "ApplyMentorModal",
    "SensitiveTicket",
    "ContactMentorTicket",
    "ContactMentorModal",
    "register_all_types",
]


def register_all_types(service: "TicketService") -> None:
    """
    Register all ticket types with the TicketService.
    Role IDs are read from environment variables:

      STAFF_ROLE_ID        — Handles General, Rankup, Join CC, Apply Mentor
      SENIOR_STAFF_ROLE_ID — Handles Apply to Staff
      SENIOR_STAFF_ROLE_ID — Handles Apply to Staff and Sensitive tickets
      OWNER_ROLE_ID        — Handles Sensitive tickets
    """
    from core.config import ConfigInterface, ConfigVars

    cfg = ConfigInterface()

    def role_id(var: ConfigVars) -> int:
        val = cfg.get_variable(var)
        if not val:
            raise RuntimeError(f"Missing env var: {var.value}")
        return int(val)

    staff = role_id(ConfigVars.STAFF_ROLE_ID)

    service.type_registry.register(GeneralTicket(staff_role_id=staff))
    service.type_registry.register(RankupTicket(staff_role_id=staff))
    service.type_registry.register(JoinCCTicket(staff_role_id=staff))
    service.type_registry.register(
        ApplyStaffTicket(senior_staff_role_id=role_id(ConfigVars.SENIOR_STAFF_ROLE_ID))
    )
    service.type_registry.register(ApplyMentorTicket(staff_role_id=staff))
    service.type_registry.register(
        ContactMentorTicket(
            mentor_role_id=role_id(ConfigVars.MENTOR_ROLE_ID), staff_role_id=staff
        )
    )
    service.type_registry.register(
        SensitiveTicket(
            senior_staff_role_id=role_id(ConfigVars.SENIOR_STAFF_ROLE_ID),
            owner_role_id=role_id(ConfigVars.OWNER_ROLE_ID),
        )
    )
