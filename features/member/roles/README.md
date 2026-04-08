# roles

Self-assign role panels — interactive select-menu embeds that let members pick their
own roles without staff intervention.

Multiple panels can be configured, each covering a different role category
(e.g. regions, game modes, interests).

## Key files

| File | Purpose |
|---|---|
| `service.py` | `RolesService` — creates and maintains panel messages |
| `commands.py` | `/rolepanel` slash commands — create, edit, and manage role panels |
| `views/` | Discord UI components — `Select` menus and their interaction callbacks |
| `models.py` | Pydantic models for panel config and role entries |
| `repository.py` | MongoDB persistence for panel configuration and message IDs |
