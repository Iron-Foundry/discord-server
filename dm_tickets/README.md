# dm_tickets

DM-based ticket interface — lets members open and reopen tickets by messaging the bot
directly, without needing access to the ticket panel in the server.

When the bot receives a DM from a guild member it replies with an interactive embed
containing two buttons.  Non-members receive a rejection message.

## Flow

```
Member DMs bot
  └─ Open Ticket  ──► type select menu
  │                     └─ type with modal ──► modal (e.g. rank/target)
  │                     └─ type without modal ──► ticket created immediately
  └─ Reopen Ticket ──► closed-ticket select menu (up to 25, newest first)
                          └─ ticket reopened, channel link returned in DM
```

Ticket channels and all side-effects (team pings, transcript, timeout) behave
identically to tickets opened through the server panel.

## Key files

| File | Purpose |
|---|---|
| `service.py` | `DMTicketService` — receives `on_message` from `DiscordClient` and dispatches the menu |
| `views.py` | All Discord UI components: `DMMenuView`, `OpenTypeSelectView`, `ReopenSelectView` and their child items |
