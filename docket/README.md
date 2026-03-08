# docket

Live community dashboard — a self-updating channel that displays the clan's current
events, table of contents, donations, and achievements in pinned panel embeds.

Panels are refreshed automatically whenever the underlying data changes.

## Key files

| File | Purpose |
|---|---|
| `service.py` | `DocketService` — manages panel lifecycle and schedules refreshes |
| `commands.py` | `/docket` slash commands — configure the dashboard channel and trigger manual updates |
| `panels/` | One module per panel type (events, TOC, donations, achievements) |
| `providers/` | Data-fetching layer — pulls content from MongoDB and external sources |
| `views/` | Discord UI components (buttons, selects) attached to panels |
| `models.py` | Pydantic models for panel config and data payloads |
| `repository.py` | MongoDB persistence for service configuration and panel message IDs |
