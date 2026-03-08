# join_roles

Automatic join role assignment — assigns a configured set of roles to every new member
the moment they join the server.

## Key files

| File | Purpose |
|---|---|
| `service.py` | `JoinRolesService` — listens for `on_member_join` and applies roles |
| `events.py` | Event handler wired into the Discord client |
| `commands.py` | `/join-roles` slash commands — configure which roles are assigned on join |
| `models.py` | Pydantic models for join role config |
| `repository.py` | MongoDB persistence for service configuration |
