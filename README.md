# Iron Foundry — Discord Bot

The main Discord bot for the Iron Foundry OSRS clan. Handles the ticket system, role management,
action logging, community dashboard panels, and general server automation.

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
| `WOM_GROUP_ID` | — | Wise Old Man group ID. Enables the Achievements panel in the docket. If unset, the panel is disabled. |

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
| `/ticket transcript <ticket_id>` | Retrieve the transcript for a ticket. Staff can view any ticket; members can only view their own. | Everyone |
| `/ticket panel <channel>` | Post the ticket creation panel to a channel. | Senior Staff |
| `/ticket setrankimage <type> <attachment>` | Upload the rank requirements or rank upgrades image shown by the Rank Details button. | Senior Staff |
| `/ticket setrankjointext` | Edit the welcome text posted into join tickets when Rank Details is clicked. | Senior Staff |

The `open`, `reopen`, and `transcript` commands support autocomplete.

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

### /broadcast

Forward a message to all members with the configured broadcast role via DM.

| Command | Description | Access |
|---|---|---|
| `/broadcast setrole <role>` | Set the role whose members receive forwarded messages. | Senior Staff |
| `/broadcast status` | Show the current broadcast role and eligible member count. | Staff |
| Right-click message → Forward to Members | DM the message to all members with the broadcast role. | Staff |

### /rolepanel

Create and manage self-assign role panels posted as Discord embeds with select menus.

| Command | Description | Access |
|---|---|---|
| `/rolepanel list` | List all active role panels. | Staff |
| `/rolepanel refresh <panel_id>` | Force-sync a panel message with current state. | Staff |
| `/rolepanel create <channel> <title>` | Post a new role panel to a channel. | Senior Staff |
| `/rolepanel edit <panel_id>` | Edit a panel's title or description via a modal. | Senior Staff |
| `/rolepanel addrole <panel_id> <role>` | Add a role to a panel. | Senior Staff |
| `/rolepanel removerole <panel_id> <role>` | Remove a role from a panel. | Senior Staff |
| `/rolepanel setemoji <panel_id> <role> <emoji>` | Set the emoji for a role on a panel. | Senior Staff |
| `/rolepanel setmax <panel_id> <max>` | Set the maximum number of selectable roles (0 = unlimited). | Senior Staff |
| `/rolepanel refreshall` | Push the current button layout to all live panel messages. | Senior Staff |
| `/rolepanel delete <panel_id>` | Delete a role panel and its message. | Senior Staff |

All commands that take a `panel_id` support autocomplete.

### /joinrole

Manage roles that are automatically assigned to every new member when they join the server.

| Command | Description | Access |
|---|---|---|
| `/joinrole add <role>` | Add a role to the join roles list. | Senior Staff |
| `/joinrole remove <role>` | Remove a role from the join roles list. | Senior Staff |
| `/joinrole list` | List all configured join roles. | Staff |

### /docket

Manage a persistent community dashboard channel. Each panel is a live Discord message that
is edited in-place when its data changes. Run `/docket setup` once to create the channel and
post all panels; subsequent restarts re-attach to the existing messages automatically.

| Command | Description | Access |
|---|---|---|
| `/docket setup <channel>` | Configure the docket channel and post all panels. | Senior Staff |
| `/docket refresh [panel_type]` | Force-refresh one or all API-backed panels. | Staff |
| `/docket reset` | Delete and re-post all panels in their original order (confirm dialog). | Senior Staff |
| `/docket events add <title> <description>` | Add a clan event (optional: host, starts, ends, image_url). | Staff |
| `/docket events remove <event_id>` | Remove a clan event (autocompletes from live entries). | Staff |
| `/docket events list` | List all events with their IDs. | Staff |
| `/docket toc add <channel> <description>` | Add a server guide entry (optional: position). | Staff |
| `/docket toc remove <entry_id>` | Remove a server guide entry. | Staff |
| `/docket toc move <entry_id> <position>` | Reorder a server guide entry. | Staff |
| `/docket toc list` | List all TOC entries with their IDs. | Staff |
| `/docket donations add <donor> <amount>` | Record a clan donation (optional: note). | Staff |
| `/docket donations remove <entry_id>` | Remove a donation entry. | Staff |
| `/docket donations list` | List all donations with their IDs. | Staff |

#### Panels

| Panel | Refresh | Description |
|---|---|---|
| Events | Manual | One embed per event — title, description, host, relative timestamps, optional banner. |
| Server Guide | Manual | Numbered channel list sorted by position. |
| Achievements | Hourly (WOM API) | Paginated recent clan achievements. Prev/Next buttons persist across restarts. Requires `WOM_GROUP_ID`. |
| Donations | Manual | Most recent 15 donations sorted by date. |

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
| `/actionlog ignore category <category>` | Exclude all channels in a category from action log entries. | Senior Staff |
| `/actionlog unignore channel <channel>` | Remove a channel from the ignore list. | Senior Staff |
| `/actionlog unignore thread <thread_id>` | Remove a thread from the ignore list. | Senior Staff |
| `/actionlog unignore category <category>` | Remove a category from the ignore list. | Senior Staff |

#### Log categories

| Thread | Events |
|---|---|
| Messages | Edit, delete, bulk-delete |
| Members | Join, leave, nick/role/timeout updates |
| Roles | Create, delete, update |
| Channels | Create, delete, update, pins |
| Threads | Create, delete, update, archive |
| Invites | Create, delete |
| Guild | Guild update, emoji, stickers, integrations |
| Moderation | Ban, unban, audit entries |
| Scheduled Events | Create, delete, update |

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
| `sensitive` | Sensitive | Sensitive matters visible only to Senior Staff and Owners. No transcript is stored. |

Tickets close automatically after 24 hours of inactivity unless the timeout has been frozen.

### Ticket Tools Panel

When staff run `/ticket tools`, a persistent panel is posted with the following buttons:

| Button | Ticket Types | Description |
|---|---|---|
| Close Ticket | All | Opens a modal to close with a reason (DM'd to creator) and an internal staff note. |
| Freeze Timeout | All | Prevents the 24-hour inactivity timer from firing. Toggles to Unfreeze. |
| Rank Details | `join_cc`, `rankup` | Posts the configured rank requirements and upgrades images. In join tickets, also posts the welcome text. |
| Change Type | All | Opens an ephemeral select menu to reclassify the ticket. Updates channel name, permissions, and transcript. |

---

## Architecture

```
core/
  discord_client.py   — DiscordClient: event handling and startup orchestration
  service_loader.py   — pure async functions that initialise each service in parallel
  command_handler.py  — CommandHandler singleton, owns the slash-command tree
  config.py           — ConfigInterface, env-var access
  service_base.py     — Service abstract base class
  service_handler.py  — ServiceHandler lifecycle manager
```

On startup `setup_hook` resolves the guild and calls `load_all_services`, which runs all
service initialisers concurrently via `asyncio.gather`, then registers `/help` once all
command groups are in place.

Services with a `post_ready` hook (e.g. `TicketService`, `DocketService`) are called after
`on_ready` once the live guild cache is available, allowing them to re-attach to existing
channel messages and start background refresh loops.

---

## Development

Run the linter and formatter:

```bash
uv run ruff check .
uv run ruff format .
```

Pre-commit hooks run Ruff and Prettier automatically on commit.
