# command_infra

Slash command infrastructure — checks, help system, and handler commands.

Nothing here defines a feature service; this folder holds the shared plumbing that every
service's command module imports, plus the admin handler commands.

## Key files

| File | Purpose |
|---|---|
| `checks.py` | Permission check decorators (`is_staff`, `is_senior_staff`) and failure handler |
| `help_registry.py` | `HelpRegistry` — collects `HelpEntry`/`HelpGroup` objects from every service |
| `help.py` | `/help` slash command — renders the registry into an embed |
| `handlers.py` | `/handler` commands — admin controls to enable/disable/reload services at runtime |
