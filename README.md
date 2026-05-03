# Iron Foundry - Discord Bot

The main Discord bot for the Iron Foundry OSRS clan. Handles the ticket system, role management,
action logging, and general server automation.

---

## Requirements

- Python 3.14+
- [uv](https://docs.astral.sh/uv/) (package manager)
- A running MongoDB instance

---

## Setup

1. Clone the repository and install dependencies:

   ```bash
   uv sync
   ```

2. Copy `.env.example` to `.env` and fill in the values (see [Environment Variables](#environment-variables) below).

3. Run the bot:

   ```bash
   uv run python main.py
   ```

---

## Environment Variables

All configuration is read from a `.env` file in the project root.

### Required

| Variable | Description |
|---|---|
| `DISCORD_TOKEN` | Bot token from the Discord Developer Portal. |
| `GUILD_ID` | The ID of the Discord server the bot operates in. |
| `DATABASE_URL` | PostgreSQL connection string. |
| `STAFF_ROLE_ID` | Role ID for Staff. |
| `SENIOR_STAFF_ROLE_ID` | Role ID for Senior Staff. |
| `OWNER_ROLE_ID` | Role ID for Owners. |
| `MENTOR_ROLE_ID` | Role ID for Mentors. |

### Optional

| Variable | Default | Description |
|---|---|---|
| `DEBUG_MODE` | - | Enable debug logging. |

---

## Commands

| Group | Description |
|---|---|
| `/ticket` | Ticket lifecycle - open, close, reopen, manage, and view stats. |
| `/tickettype` | Enable or disable ticket types on the creation panel. |
| `/handler` | Manage transcript persistence handlers. |
| `/broadcast` | Forward messages to a configured role via DM. |
| `/rolepanel` | Create and manage self-assign role panels. |
| `/joinrole` | Configure roles auto-assigned to new members on join. |
| `/actionlog` | Configure the action log forum and manage ignore lists. |
| `/account` | Link an RSN and view linked account details. |
| `/userkey` | View or regenerate the RuneLite plugin verification key. |
| `/privacy` | Opt out or back in to stats and loot data collection. |

---

## Architecture

```
core/
  discord_client.py   - DiscordClient: event handling and startup orchestration
  service_loader.py   - async functions that initialise each service in parallel
  command_handler.py  - CommandHandler singleton, owns the slash-command tree
  config.py           - ConfigInterface, env-var access
  service_base.py     - Service abstract base class
  service_handler.py  - ServiceHandler lifecycle manager
```

---

## Development

```bash
uv run ruff check .
uv run ruff format .
```

Pre-commit hooks run Ruff and Prettier automatically on commit.
