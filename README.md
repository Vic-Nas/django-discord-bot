# Discord Role Bot

Auto-assign roles via invite links with web admin panel. Two modes: **AUTO** (instant) or **APPROVAL** (with forms).

## [🔗 Invite Bot](https://discord.com/oauth2/authorize?client_id=1430005122917990410&permissions=268504112&integration_type=0&scope=bot)

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
# Unit tests (fast, ~30 seconds)
pytest tests/test_handlers.py -v

# Integration tests (with real Discord, ~3 minutes)
# Stop Railway bot first, then:
pytest tests/test_integration.py -m integration -v
```

### Run Bot Locally
```bash
python bot/main.py
```

---

## Features

- 🎯 **AUTO Mode** — Instant role assignment  
- 📝 **APPROVAL Mode** — Forms + admin review  
- 🌐 **Web Admin** — Manage visually  
- 🔧 **Customizable** — Edit all messages  
- 🔒 **Secure** — Token-based access  
- 🏢 **Multi-Server** — Per-guild config  

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

@Bot addrule <code> @role [@role2 ...]
  Map an invite code to Discord roles (assigned on join in AUTO mode)

@Bot delrule <code>
  Remove an invite rule

@Bot listrules
  Show all configured invite rules for this server

@Bot addfield "Label" text|textarea|dropdown|checkbox
  Add a custom form field (shown in APPROVAL mode)
  
@Bot listfields
  List all custom form fields
```

### Application Management (APPROVAL mode)
```
@Bot approve @user [@role ...]
  Approve user's application, assign roles, remove Pending role, delete application record

@Bot reject @user [reason]
  Reject user's application, remove Pending role, keep rejection in database
```

### General
```
@Bot help
  Show available commands

@Bot getaccess
  Generate a 24-hour web panel access token (DM only)
```
