# Discord Role Bot

Auto-assign roles via invite links with web admin panel. Two modes: **AUTO** (instant) or **APPROVAL** (with forms).

## [🔗 Invite Bot](https://discord.com/oauth2/authorize?client_id=1430005122917990410&permissions=268504112&integration_type=0&scope=bot)

---

## Architecture

```
Discord ← bot/main.py (single gateway)
              ↓ events as dicts
         core/services.py (all business logic)
              ↓ action dicts
         bot/main.py (executes on Discord)
```

Two systems in `services.py`:

1. **Automations** (data-driven) — `Automation` → `Action` models, configured via admin panel.
   Handles: member join flows, custom commands, form events.
2. **Built-in commands** (code) — `approve`, `reject`, `addrule`, etc.
   Complex stateful logic that doesn't fit in JSON config.

The bot never contains business logic — it translates Discord events to dicts, calls `handle_*()`, and executes the returned action dicts.

---

## Deploy to Railway

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app)

### Setup (2 services):
1. **Web Service** (auto-deployed from Dockerfile)
   - Runs Django admin & API
   
2. **Bot Service** (create manually)
   - In Railway dashboard → New Service
   - Connect your GitHub repo
   - Set custom start command: `python bot/main.py`
   
3. Add PostgreSQL database (Railway plugin)

4. Set `.env` variables:
   ```
   DISCORD_TOKEN=your_bot_token
   APP_URL=https://your-railway-app.up.railway.app
   ```

5. **Invite bot to Discord server**
   - Go to Developer Portal → OAuth2 → URL Generator
   - Permissions: `268504112`
   - Copy URL and invite bot

6. **Initialize database** (runs once):
   ```bash
   python manage.py init_defaults --guild_id YOUR_GUILD_ID
   ```
   Or kick/re-invite bot to trigger auto-init on server

7. Configure via web admin panel

---

## Local Development

### Setup
```bash
git clone https://github.com/Vic-Nas/django-discord-bot
cd django-discord-bot
python -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
python manage.py migrate
python manage.py init_defaults
```

### Run Tests
```bash
# All tests (42 tests: unit + integration)
pytest tests/ -v

# Unit tests only
pytest tests/test_handlers.py -v

# Integration tests only
pytest tests/test_integration.py -v
```

### Run Bot Locally
```bash
python bot/main.py
```

---

## Features

- 🎯 **AUTO Mode** — Instant role assignment via invite rules
- 📝 **APPROVAL Mode** — Forms + admin review (approve/reject via command or reaction)
- ⚙️ **Automation Engine** — Data-driven triggers + actions, configurable in admin
- 🌐 **Web Admin** — Manage guilds, automations, forms, templates
- 🔧 **Customizable Templates** — Per-guild message overrides
- 🔒 **Secure** — Token-based web panel access
- 🏢 **Multi-Server** — Per-guild config, roles, channels, rules

---

## Commands

### Setup & Maintenance
```
@Bot reload
  Sync roles/channels with Discord, ensure resources exist, create missing applications
```

### Server Configuration
```
@Bot setmode AUTO|APPROVAL
  AUTO: Instant role assignment based on invite code
  APPROVAL: Require manual admin approval via form submissions

@Bot addrule <code> <role1,role2,...> [description]
  Map an invite code to Discord roles (assigned on join in AUTO mode)

@Bot delrule <code>
  Remove an invite rule

@Bot listrules
  Show all configured invite rules for this server

@Bot listfields
  List all custom form fields (configured in admin panel)
```

### Application Management (APPROVAL mode)
```
@Bot approve @user [@role ...]
  Approve user's application, assign roles from rules + form, remove Pending role

@Bot approve @Role
  Bulk approve all members with that role who have submitted their form

@Bot reject @user [reason]
  Reject user's application, remove Pending role, notify user via DM
```

### General
```
@Bot help
  Show available commands (including custom automation commands)

@Bot getaccess
  Generate a 24-hour web panel access token (DM only)
```

---

## Models

| Model | Purpose |
|---|---|
| `GuildSettings` | Per-guild config (mode, channels, admin role) |
| `Automation` | Trigger → Actions pipeline (MEMBER_JOIN, COMMAND, etc.) |
| `Action` | Single step in an automation (SEND_EMBED, ADD_ROLE, etc.) |
| `InviteRule` | Invite code → role mapping |
| `Application` | Pending/rejected user applications |
| `FormField` | Custom form fields per guild |
| `Dropdown` | Dropdown options (roles, channels, custom) |
| `MessageTemplate` | Default message templates |
| `GuildMessageTemplate` | Per-guild template overrides |
| `DiscordRole` / `DiscordChannel` | Cached Discord entities |
| `AccessToken` | Web panel auth tokens |
