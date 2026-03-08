# action_log

Server audit logging — captures and posts a structured embed for every significant
server event across 9 event categories.

Tracked events include message edits and deletions, member joins/leaves/bans,
role and channel changes, thread activity, invite tracking, and voice/moderation events.
All writes go through a rate-limited queue to stay safely within Discord limits.

## Key files

| File | Purpose |
|---|---|
| `service.py` | `ActionLogService` — registers all event listeners and routes them to handlers |
| `events/` | One module per event category (messages, members, roles, channels, threads, invites, scheduled, guild, moderation) |
| `commands.py` | `/actionlog` slash commands — configure the forum channel and manage ignore lists |
| `models.py` | Pydantic models for log config and event payloads |
| `repository.py` | MongoDB persistence for service configuration |
| `registrar.py` | Maps Discord event names to handler functions |
| `throttle.py` | Per-guild rate limiting to prevent log spam |
