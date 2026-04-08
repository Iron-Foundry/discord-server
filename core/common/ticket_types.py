from enum import Enum


class TicketTypeId(str, Enum):
    GENERAL = "general"
    RANKUP = "rankup"
    JOIN_CC = "join_cc"
    APPLY_STAFF = "apply_staff"
    APPLY_MENTOR = "apply_mentor"
    APPLY_EVENT_TEAM = "apply_event_team"
    CONTACT_MENTOR = "contact_mentor"
    SENSITIVE = "sensitive"
    SURVEY = "survey"
