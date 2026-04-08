# tickets

Full ticket system — creation, moderation, transcripts, stats, and 7 ticket types.

Members open tickets via a panel embed with a select menu; staff manage them through
slash commands and a persistent tools panel with buttons for closing, freezing timeouts,
posting rank details, and reclassifying the ticket type. Tickets close automatically
after 24 hours of inactivity unless frozen.

## Key files

| File | Purpose |
|---|---|
| `ticket_service.py` | `TicketService` — central orchestrator for the full ticket lifecycle |
| `commands.py` | `/ticket` and `/tickettype` slash commands |
| `types/` | One module per ticket type, defining its form fields, permissions, and embeds |
| `handlers/database.py` | `MongoTicketRepository` — all MongoDB persistence (tickets, transcripts, panel config, rank details config) |
| `handlers/archive_channel.py` | `ArchiveChannelTicketRepository` — posts transcript file to a Discord archive channel on close |
| `handlers/embed.py` | `EmbedBuilder` — fluent builder for Discord embeds with API limit validation |
| `views/ticket_tools.py` | `TicketToolsView` — staff tools panel (Close, Freeze, Rank Details, Change Type buttons) |
| `views/panel.py` | `TicketPanelView` — the public-facing panel embed and type select menu |
| `views/reopen.py` | Reopen confirmation view |
| `views/stats.py` | Stats embed and chart views for `/ticket stats`, `/ticket leaderboard`, `/ticket system` |
| `charts.py` | Generates statistics charts (volume, resolution time, type breakdown) via Plotly/Kaleido |
| `models/ticket.py` | `TicketRecord`, `Ticket`, `TicketTypeConfig`, `TicketTypeRegistry` |
| `models/transcript.py` | `Transcript`, `TranscriptEntry`, `StaffAction`, `StaffActionType` |
| `models/stats.py` | `HandlerStats`, `LeaderboardEntry`, `SystemStats` |
