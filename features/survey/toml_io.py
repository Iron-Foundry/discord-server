from __future__ import annotations

import tomllib
from datetime import UTC, datetime

from features.survey.models import SurveyField, SurveyTemplate

EXAMPLE_TOML = """\
[survey]
title       = "Monthly Clan Feedback"
description = "Help us improve the clan by sharing your thoughts each month."

[[fields]]
id          = "recommend"
type        = "yes_no"
label       = "Would you recommend Iron Foundry to a friend?"
required    = true

[[fields]]
id          = "overall"
type        = "select"
label       = "Overall experience this month"
required    = true
max_choices = 1
options     = ["Excellent", "Good", "Average", "Poor"]

[[fields]]
id          = "highlights"
type        = "select"
label       = "What did you enjoy? (pick up to 3)"
description = "Select all that apply."
required    = false
max_choices = 3
options     = ["Events", "Community", "PVM content", "Skilling", "Staff support", "Discord activity"]

[[fields]]
id          = "highlight_text"
type        = "short_text"
label       = "Best moment this month"
description = "One sentence is fine."
required    = false

[[fields]]
id          = "feedback"
type        = "long_text"
label       = "Any other thoughts or suggestions?"
description = "Be as detailed as you like — we read every response."
required    = false

# ---------------------------------------------------------------------------
# FIELD REFERENCE
# ---------------------------------------------------------------------------
#
# Every [[fields]] block requires three keys:
#
#   id       Unique snake_case identifier for this field within the template.
#            Used as the column header in CSV exports. No spaces or special chars.
#            Example: "overall_rating"
#
#   type     Controls the UI shown to the respondent. One of:
#
#              yes_no      Two buttons — Yes and No.
#                          Stored as true / false.
#
#              short_text  A single-line text input (up to 1 024 characters).
#                          Opens a modal when the respondent clicks "Answer".
#
#              long_text   A multi-line paragraph input (up to 4 000 characters).
#                          Same modal flow as short_text, larger box.
#
#              select      A dropdown menu built from the options list below.
#                          Use max_choices > 1 to allow multiple selections.
#
#   label    The question text shown to the respondent. Keep it concise.
#
# Optional keys (all fields):
#
#   description  Subtitle shown beneath the label for extra context.
#                Default: none.
#
#   required     true (default) — the field cannot be skipped.
#                false          — a "Skip" button is shown alongside the answer UI.
#
# Optional keys (select fields only):
#
#   options      Array of choice strings shown in the dropdown.
#                Required when type = "select".
#                Example: ["Option A", "Option B", "Option C"]
#
#   max_choices  Maximum number of options a respondent may select.
#                Default: 1. Must not exceed the number of options.
#                Set to more than 1 to allow multi-select.
#
# ---------------------------------------------------------------------------
# NOTES
# ---------------------------------------------------------------------------
#
# - Field ids must be unique within the file.
# - Fields are presented in the order they appear here.
# - Activate the template with /survey activate <name> to open it to members.
# - Only one survey can be active at a time.
# - Import this file with /survey template import <name> <this file>.
# ---------------------------------------------------------------------------
"""

_VALID_TYPES = frozenset({"yes_no", "short_text", "long_text", "select"})


class SurveyValidationError(Exception):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("\n".join(f"• {e}" for e in errors))


def parse_toml(
    data: bytes,
    *,
    name: str,
    guild_id: int,
    created_by_id: int,
) -> SurveyTemplate:
    """Parse TOML bytes into a SurveyTemplate.

    Raises :class:`SurveyValidationError` if any field is invalid, collecting
    all errors before raising so the caller can report them all at once.
    """
    errors: list[str] = []

    try:
        raw = tomllib.loads(data.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise SurveyValidationError([f"Could not parse TOML: {exc}"]) from exc

    survey_section = raw.get("survey", {})
    title = str(survey_section.get("title", "")).strip()
    if not title:
        errors.append("[survey] title is required")
    description = str(survey_section.get("description", "")).strip() or None

    raw_fields = raw.get("fields", [])
    if not isinstance(raw_fields, list) or not raw_fields:
        errors.append("At least one [[fields]] entry is required")
        raise SurveyValidationError(errors)

    seen_ids: set[str] = set()
    parsed_fields: list[SurveyField] = []

    for i, rf in enumerate(raw_fields):
        prefix = f"Field #{i + 1}"

        fid = str(rf.get("id", "")).strip()
        ftype = str(rf.get("type", "")).strip()
        flabel = str(rf.get("label", "")).strip()

        if not fid:
            errors.append(f"{prefix}: 'id' is required")
        elif fid in seen_ids:
            errors.append(f"{prefix}: duplicate id '{fid}'")
        else:
            seen_ids.add(fid)
            prefix = f"Field '{fid}'"

        if not ftype:
            errors.append(f"{prefix}: 'type' is required")
        elif ftype not in _VALID_TYPES:
            valid = ", ".join(sorted(_VALID_TYPES))
            errors.append(f"{prefix}: unknown type '{ftype}' — must be one of {valid}")

        if not flabel:
            errors.append(f"{prefix}: 'label' is required")

        options: list[str] = [str(o) for o in rf.get("options", [])]
        max_choices: int = rf.get("max_choices", 1)
        required: bool = rf.get("required", True)

        if ftype == "select":
            if not options:
                errors.append(f"{prefix}: select type requires at least one option")
            if not isinstance(max_choices, int) or max_choices < 1:
                errors.append(f"{prefix}: max_choices must be a positive integer")
            elif options and max_choices > len(options):
                errors.append(
                    f"{prefix}: max_choices ({max_choices}) exceeds option count ({len(options)})"
                )

        if not errors:
            parsed_fields.append(
                SurveyField(
                    id=fid,
                    type=ftype,  # type: ignore[arg-type]
                    label=flabel,
                    description=str(rf.get("description", "")).strip() or None,
                    required=bool(required),
                    options=options,
                    max_choices=int(max_choices) if isinstance(max_choices, int) else 1,
                )
            )

    if errors:
        raise SurveyValidationError(errors)

    return SurveyTemplate(
        template_id=name,
        guild_id=guild_id,
        title=title,
        description=description,
        fields=parsed_fields,
        created_at=datetime.now(UTC),
        created_by_id=created_by_id,
    )


def _esc(s: str) -> str:
    """Escape a string for use inside a TOML double-quoted string."""
    return (
        s.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "")
    )


def export_toml(template: SurveyTemplate) -> bytes:
    """Serialise a SurveyTemplate to TOML bytes."""
    lines: list[str] = [
        "[survey]",
        f'title       = "{_esc(template.title)}"',
    ]
    if template.description:
        lines.append(f'description = "{_esc(template.description)}"')
    lines.append("")

    for field in template.fields:
        lines.append("[[fields]]")
        lines.append(f'id          = "{_esc(field.id)}"')
        lines.append(f'type        = "{field.type}"')
        lines.append(f'label       = "{_esc(field.label)}"')
        if field.description:
            lines.append(f'description = "{_esc(field.description)}"')
        lines.append(f"required    = {'true' if field.required else 'false'}")
        if field.type == "select":
            opts = ", ".join(f'"{_esc(o)}"' for o in field.options)
            lines.append(f"options     = [{opts}]")
            if field.max_choices != 1:
                lines.append(f"max_choices = {field.max_choices}")
        lines.append("")

    return "\n".join(lines).encode("utf-8")
