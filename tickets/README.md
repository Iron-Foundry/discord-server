# tickets

Full ticket system — creation, moderation, transcripts, stats, and 7 ticket types.

Members open tickets via a panel embed; staff manage them through thread-based
workflows with buttons for claiming, closing, reopening, and exporting transcripts.

## Key files

| File | Purpose |
|---|---|
| `ticket_service.py` | `TicketService` — central orchestrator for the full ticket lifecycle |
| `commands.py` | `/ticket` slash commands — staff commands (setup, close, reopen, stats, …) |
| `types/` | One module per ticket type defining its form fields and routing logic |
| `handlers/` | Step handlers — creation flow, moderation actions, transcript export |
| `views/` | Discord UI components — creation panels, moderation buttons, forms |
| `charts.py` | Generates statistics charts (ticket volume, resolution time, type breakdown) |
| `models/` | Pydantic models for ticket state, config, and transcript data |
