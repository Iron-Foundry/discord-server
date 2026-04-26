from enum import Enum


class TicketTypeId(str, Enum):
    GENERAL = "general"
    RANKUP = "rankup"
    JOIN_CC = "join_cc"
    CONTACT_MENTOR = "contact_mentor"
    SENSITIVE = "sensitive"
