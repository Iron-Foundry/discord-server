# broadcast

Member broadcast service — sends a DM to every member that holds a configured role.

Useful for clan-wide announcements that need to reach members who may not be watching
a specific channel.

## Key files

| File | Purpose |
|---|---|
| `service.py` | `BroadcastService` — orchestrates the DM send loop with rate limiting |
| `commands.py` | `/broadcast` slash commands — compose and send a broadcast |
| `models.py` | Pydantic models for broadcast config and message payloads |
| `repository.py` | MongoDB persistence for service configuration |
