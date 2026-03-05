# Iron Foundry — Discord Bot

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
| `MONGO_URI` | MongoDB connection string. |
| `STAFF_ROLE_ID` | Role ID for Staff. Required for staff-gated commands. |
| `SENIOR_STAFF_ROLE_ID` | Role ID for Senior Staff. Required for senior-staff-gated commands, staff applications, and sensitive tickets. |
| `OWNER_ROLE_ID` | Role ID for Owners. Used for sensitive tickets. |
| `MENTOR_ROLE_ID` | Role ID for Mentors. Used for mentor contact tickets. |

### Optional

| Variable | Default | Description |
|---|---|---|
| `MONGO_DB_NAME` | `foundry` | MongoDB database name. |
| `ARCHIVE_CHANNEL_ID` | — | Channel ID where closed ticket transcripts are posted. If unset, the archive handler is not registered. |
| `CHANNEL_COLLECTION` | — | MongoDB collection name for channel records. |
| `ROLE_COLLECTION` | — | MongoDB collection name for role records. |
| `USER_COLLECTION` | — | MongoDB collection name for user records. |
| `DEBUG_MODE` | — | Set to any truthy value to enable debug logging. |

---

## Commands

### /ticket

Ticket lifecycle and management.

| Command | Description | Access |
|---|---|---|
| `/ticket open <type>` | Open a new ticket of the specified type. | Everyone |
| `/ticket close` | Close the current ticket (prompts for a reason). | Everyone |
| `/ticket reopen <id>` | Reopen a previously closed ticket. | Everyone |
| `/ticket tools` | Post the moderator tools panel in the current ticket. | Staff |
| `/ticket add <user>` | Add a member to the current ticket channel. | Staff |
| `/ticket remove <user>` | Remove a member from the current ticket channel. | Staff |
| `/ticket freeze` | Freeze the 24-hour inactivity timeout on the current ticket. | Staff |
| `/ticket unfreeze` | Resume the 24-hour inactivity timeout. | Staff |
| `/ticket list <user>` | List a member's recent tickets. | Staff |
| `/ticket stats [user] [period]` | View handler statistics for a staff member (type breakdown, avg response/resolution time). Defaults to the invoking user and all-time. | Staff |
| `/ticket leaderboard [period]` | Show top handlers ranked by tickets closed. Excludes bot auto-closures. | Staff |
| `/ticket system [period]` | View overall system stats (volume, avg wait/response/resolution time). | Staff |
| `/ticket panel <channel>` | Post the ticket creation panel to a channel. | Senior Staff |

The `open` and `reopen` commands support autocomplete.

### /tickettype

Enable or disable ticket types. Changes take effect on the panel immediately.

| Command | Description | Access |
|---|---|---|
| `/tickettype list` | Show all registered ticket types and whether they are enabled. | Everyone |
| `/tickettype enable <type>` | Enable a ticket type. | Senior Staff |
| `/tickettype disable <type>` | Disable a ticket type. | Senior Staff |

### /handler

Manage transcript persistence handlers.

| Command | Description | Access |
|---|---|---|
| `/handler list` | Show all registered transcript handlers and their status. | Senior Staff |
| `/handler enable <name>` | Enable a transcript handler. | Senior Staff |
| `/handler disable <name>` | Disable a transcript handler. | Senior Staff |

The `mongodb` handler is protected and cannot be disabled.

### /actionlog

Configure and manage the action log service. Log entries are posted as embeds into categorised
threads inside a Discord ForumChannel.

| Command | Description | Access |
|---|---|---|
| `/actionlog setup <forum>` | Create or reuse category threads in the given forum channel. | Senior Staff |
| `/actionlog status` | Show current configuration: enabled state, forum, thread count, and ignore lists. | Staff |
| `/actionlog toggle` | Enable or disable the action log. | Senior Staff |
| `/actionlog ignore channel <channel>` | Exclude a channel from action log entries. | Senior Staff |
| `/actionlog ignore thread <thread_id>` | Exclude a thread (by ID) from action log entries. | Senior Staff |
| `/actionlog unignore channel <channel>` | Remove a channel from the ignore list. | Senior Staff |
| `/actionlog unignore thread <thread_id>` | Remove a thread from the ignore list. | Senior Staff |

#### Log categories

| Thread | Colour | Events (planned) |
|---|---|---|
| Messages | Gold | Edit, delete, bulk-delete |
| Members | Green | Join, leave, nick/role/timeout updates |
| Roles | Blue | Create, delete, update |
| Channels | Purple | Create, delete, update, pins |
| Guild | Teal | Guild update, emoji, stickers, integrations |
| Moderation | Red | Ban, unban, audit entries |
| Scheduled Events | Orange | Create, delete, update |

All writes go through a rate-limited queue (1 message/second) to stay safely within Discord limits.

---

## Ticket Types

| Identifier | Name | Description |
|---|---|---|
| `general` | General Support | General questions and miscellaneous requests. |
| `rankup` | Rank Up | Rank-up applications. Prompts for current and target rank. |
| `join_cc` | Join the CC | Applications to join the clan chat. |
| `apply_staff` | Apply to Staff | Staff applications. Prompts for RSN, experience, region, and motivation. |
| `apply_mentor` | Apply to Mentor | Mentor applications. Prompts for RSN, experience, and motivation. |
| `contact_mentor` | Contact a Mentor | PVM help requests. Prompts for RSN, content, and experience level. |
| `sensitive` | Sensitive | Sensitive matters visible only to Senior Staff and Owners. |

Tickets close automatically after 24 hours of inactivity unless the timeout has been frozen.

---

## Architecture

```
core/
  discord_client.py   — DiscordClient: event handling and startup orchestration
  service_loader.py   — pure async functions that initialise each service in parallel
  command_handler.py  — CommandHandler singleton, owns the slash-command tree
  config.py           — ConfigInterface, env-var access
```

On startup `setup_hook` (or `on_ready` if the guild was not yet available) calls
`load_all_services`, which runs the four service initialisers concurrently via
`asyncio.gather`, then registers `/help` once all command groups are in place.

---

## Development

Run the linter and formatter:

```bash
uv run ruff check .
uv run ruff format .
```

Pre-commit hooks run Ruff and Prettier automatically on commit.
