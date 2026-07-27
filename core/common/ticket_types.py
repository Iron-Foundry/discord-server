from enum import StrEnum


class TicketTypeId(StrEnum):
    GENERAL = "general"
    RANKUP = "rankup"
    JOIN_CC = "join_cc"
    CONTACT_MENTOR = "contact_mentor"
    SENSITIVE = "sensitive"
