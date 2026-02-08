# Discord Role Bot

Auto-assign roles via invite links with web admin panel. Two modes: **AUTO** (instant) or **APPROVAL** (with forms).

## [🔗 Invite Bot](https://discord.com/oauth2/authorize?client_id=1430005122917990410&permissions=268504112&integration_type=0&scope=bot)

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

## Deploy to Railway

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.com?referralCode=ZIdvo-)

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

5. **Invite bot to Discord server** — bot auto-creates roles, channels, and default automations on join.

6. Configure via web admin panel (`@Bot getaccess` in DMs for a login link).

---

## Commands

### Setup & Maintenance
```
@Bot reload          — Sync roles/channels, ensure resources exist
@Bot setmode AUTO|APPROVAL — Switch server mode
```

### Invite Rules
```
@Bot addrule <code> <role1,role2,...> [description]
@Bot delrule <code>
@Bot listrules
```

### Application Management (APPROVAL mode)
```
@Bot approve @user [@role ...]
@Bot approve @Role              — Bulk approve members with that role
@Bot reject @user [reason]
```

### General
```
@Bot help       — Show all commands (built-in + custom automations)
@Bot getaccess  — Get web panel link (DM only)
@Bot cleanup    — Delete resolved bot messages in current channel (Admin)
@Bot cleanall   — Delete ALL bot messages except pending apps in current channel (Admin)
@Bot listfields — List form fields
```
