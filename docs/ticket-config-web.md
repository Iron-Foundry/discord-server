# Ticket Type Config - Web Design

Web-based editor for all ticket type configuration. Staff-gated. Replaces manual DB edits and deprecated slash commands (`/ticket setrankimage`, `/ticket setrankjointext`).

---

## Configurable Fields Per Type

| Field | Type | Description |
|---|---|---|
| `display_name` | string | Panel button label |
| `description` | string | Panel section subtext |
| `emoji` | string | Unicode emoji or Discord emoji string |
| `color_hex` | string | Accent color for ticket channel create message |
| `enabled` | bool | Show/hide in panel |
| `max_open_per_user` | int | 0 = unlimited |
| `team_ids` | int[] | Role IDs that handle this type |
| `category_id` | int | Discord category for new ticket channels |
| `welcome_text` | string (markdown) | Posted on ticket create (Join CC / Rankup) |
| `images` | ImageBlob[] | Uploaded images shown in welcome message |

`ImageBlob` shape: `{ name: string, filename: string, data: base64 string }`.

---

## API Endpoints (api-backend, FastAPI)

All endpoints under `/api/tickets/config`. Require staff auth (Discord OAuth2 JWT).

```
GET    /api/tickets/config
       → 200 { types: TicketTypeConfig[] }

GET    /api/tickets/config/{type_id}
       → 200 TicketTypeConfig
       → 404 if unknown type_id

PATCH  /api/tickets/config/{type_id}
       body: Partial<TicketTypeConfig> (all fields optional)
       → 200 updated TicketTypeConfig
       → 422 on validation error

POST   /api/tickets/config/{type_id}/images
       body: multipart/form-data  { name: string, file: File }
       → 201 { name, filename }
       → 413 if file > 8 MB

DELETE /api/tickets/config/{type_id}/images/{image_name}
       → 204
       → 404 if image not found
```

`TicketTypeConfig` response shape:

```json
{
  "type_id": "rankup",
  "display_name": "Rank Up",
  "description": "Apply for a rank promotion",
  "emoji": "⬆️",
  "color_hex": "#f0b232",
  "enabled": true,
  "max_open_per_user": 1,
  "team_ids": [123456789],
  "category_id": 987654321,
  "welcome_text": "Welcome! Please provide screenshots of all required items.",
  "images": [
    { "name": "rank_reqs", "filename": "rank_reqs.png" },
    { "name": "rank_upgrades", "filename": "rank_upgrades.png" }
  ]
}
```

Images are stored as blobs in the `config` table under key `ticket/{type_id}/images/{name}`. The GET response omits `data` (base64) for list efficiency; the Discord bot reads raw bytes directly from the repo.

---

## Discord-Server Config Refresh

On any `PATCH` or image mutation, api-backend publishes a Valkey message:

```
channel: ticket:config:refresh
payload: { "type_id": "<id>" }   (or "all" for full reload)
```

`ticket_service.py` subscribes via `_valkey_subscriber` (same pattern as `_discord_chat_subscriber` in api-backend). On receive:

```python
async def _on_config_refresh(self, payload: dict) -> None:
    type_id = payload.get("type_id", "all")
    await self.type_registry.reload(type_id)
    await self.refresh_panel()
```

`type_registry.reload(type_id)` re-fetches config from DB for the given type (or all types if `"all"`). Panel refreshes automatically - staff sees updated panel within seconds of saving in the web UI.

---

## Web-App Page: `/admin/tickets`

Route: `src/routes/admin/tickets.tsx`
Auth guard: staff role required (same pattern as other admin routes).

### Layout

```
/admin/tickets
  Header: "Ticket Types"  [Save All button - top right]

  Per-type accordion / tab:
    [General] [Rank Up] [Join CC] [Contact Mentor] [Sensitive]

  Per-type panel (expanded):
    --- Display ---
    Text: display_name
    Text: description
    Emoji picker: emoji
    Color picker: color_hex (hex input + swatch)

    --- Behaviour ---
    Toggle: enabled
    Number: max_open_per_user  (0 = unlimited)
    Multi-select: team_ids  (Discord role picker, fetched from /api/members/roles)
    Number: category_id  (Discord channel ID)

    --- Welcome Message ---
    Markdown editor: welcome_text  (preview pane on the right)

    --- Images ---
    Image upload zones:
      [rank_reqs]   [drag or click to upload]  [current thumbnail if set]  [Remove]
      [rank_upgrades] ...
    Note: only shown for types that support welcome images (Join CC, Rank Up)

    [Save] button per type (PATCH /api/tickets/config/{type_id})
```

### State

- Load on mount: `GET /api/tickets/config` → populate all type forms.
- Per-type save: `PATCH` only changed fields (dirty tracking).
- Image upload: `POST .../images` on file select; `DELETE .../images/{name}` on remove.
- Success toast on save. Error toast with message on 4xx/5xx.

### Components

- `TicketTypeCard` - per-type accordion panel.
- `MarkdownEditor` - textarea + preview (reuse existing markdown renderer if available).
- `ImageUploadZone` - drag-and-drop, calls API directly on drop, shows thumbnail.
- `RolePicker` - multi-select backed by `/api/members/roles` (or static list from bot config).

---

## Implementation Order

1. DB schema: ensure `config` table has blob storage for image data (already used by existing `/ticket setrankimage`).
2. api-backend: `GET` + `PATCH` endpoints, Valkey publish on mutation.
3. api-backend: image `POST` + `DELETE` endpoints.
4. discord-server: `_valkey_subscriber` hook + `type_registry.reload()`.
5. web-app: `/admin/tickets` route + `TicketTypeCard`, `MarkdownEditor`, `ImageUploadZone`.

---

## Notes

- `/ticket setrankimage` and `/ticket setrankjointext` commands remain functional during transition. Mark as deprecated in help text once web UI ships.
- `color_hex` maps to `discord.Color` via `discord.Color.from_str(hex)` in the bot.
- `team_ids` and `category_id` are Discord snowflakes stored as strings in DB to avoid int64 precision issues in JSON.
