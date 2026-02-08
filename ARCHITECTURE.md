# Architecture

## Flow

```
Discord ← bot/main.py (gateway listener + action executor)
              ↓ events as dicts
         core/services.py (all business logic)
              ↓ action dicts
         bot/main.py (executes on Discord)
```

The bot has **zero business logic**. It translates Discord events to plain dicts, calls `handle_*()` in `core/services.py`, and executes the returned action dicts back on Discord.

## Two systems in `services.py`

1. **Automations** (data-driven) — `Automation` → `Action` models, fully configurable via admin panel.  
   Handles: member join flows, custom commands, form events. Default definitions live in `core/fixtures/default_automations.json`.

2. **Built-in commands** (code) — `approve`, `reject`, `addrule`, etc.  
   Complex stateful logic that doesn't fit in JSON config.

## Key files

| File | Role |
|---|---|
| `bot/main.py` | Discord gateway, event dispatch, action executor |
| `core/services.py` | All business logic, command routing, automation engine |
| `core/models.py` | Django models (guild config, automations, forms, templates) |
| `core/admin.py` | Django admin panel registration |
| `bot/handlers/guild_setup.py` | On-join setup: creates roles, channels, default automations |
| `bot/handlers/templates.py` | Message template resolution (custom → default → hardcoded fallback) |
| `core/fixtures/default_automations.json` | Default automation definitions (data, not code) |

## Action dict types

Actions returned by `services.py` that the bot executor understands:

`send_message`, `send_embed`, `send_embed_tracked`, `send_dm`, `reply`,
`add_role`, `remove_role`, `edit_message`, `clear_reactions`,
`set_permissions`, `set_topic`, `ensure_resources`, `cleanup_channel`

## Models

| Model | Purpose |
|---|---|
| `GuildSettings` | Per-guild config (mode, channel IDs, role IDs) |
| `Automation` | Trigger → Actions pipeline (MEMBER_JOIN, COMMAND, FORM_SUBMIT, REACTION) |
| `Action` | Single step in an automation (SEND_EMBED, ADD_ROLE, CLEANUP, etc.) |
| `InviteRule` | Invite code → role mapping |
| `Application` | User applications in APPROVAL mode |
| `FormField` / `Dropdown` / `DropdownOption` | Dynamic form builder |
| `MessageTemplate` / `GuildMessageTemplate` | Default + per-guild template overrides |
| `DiscordRole` / `DiscordChannel` | Cached Discord entities |
| `AccessToken` | 24-hour web panel auth tokens |
