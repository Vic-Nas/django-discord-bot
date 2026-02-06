# Discord Role Bot

Manage Discord roles via invite links with web admin. Two modes: **AUTO** (instant role assignment) or **APPROVAL** (application forms with admin review).

## [🔗 Invite Bot](https://discord.com/oauth2/authorize?client_id=1430005122917990410&permissions=268504080&integration_type=0&scope=bot) | [📖 Documentation](#commands)

---

## Features

- 🎯 **AUTO Mode** - Assign roles instantly based on invite link
- 📝 **APPROVAL Mode** - Application forms with admin review
- 🌐 **Web Admin Panel** - Manage everything visually
- 🔧 **Customizable** - Edit messages, forms, permissions
- 🔒 **Secure** - Token-based admin access
- 🏢 **Multi-Server** - Independent config per server

---

## Quick Start

### Deploy to Railway

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.com?referralCode=ZIdvo-)

1. Click Deploy on Railway
2. Add PostgreSQL database
3. Set environment variables (see `.env.example`)
4. Wait for the web service to deploy successfully
5. **Create a second service for the bot:**
   - In Railway dashboard, create a new service from your repo
   - Give it a name (e.g., "discord-bot")
   - In the service settings, add a custom start command: `python bot/main.py`
   - Deploy
6. Invite bot to your Discord server
7. Give yourself `@BotAdmin` role
8. DM bot: `@BotName getaccess`
9. Configure via web panel

### Self-Host

**Requirements:** Python 3.10+, PostgreSQL, Cloudinary account

```bash
git clone https://github.com/Vic-Nas/django-discord-bot
cd discord-discord-bot
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your credentials
python manage.py migrate
python manage.py init_defaults
python bot/main.py
```

**Environment variables needed:**
- `DISCORD_TOKEN` - From Discord Developer Portal
- `DATABASE_URL` - PostgreSQL connection string
- `CLOUDINARY_*` - From Cloudinary dashboard
- `SECRET_KEY` - Random string for Django
- `APP_URL` - Your deployment URL

**Bot Permissions Required:**

When creating the OAuth2 invite URL in Discord Developer Portal, grant these permissions:
- **Manage Roles** - Assign roles to members
- **Manage Channels** - Create/update logs and approvals channels
- **Send Messages** - Post in logs and approvals channels
- **Read Messages/View Channels** - Access channel content
- **Read Message History** - Log historical messages


## Commands

All commands use `@BotName command` format.

**Setup (Admin):**
```
@BotName setmode AUTO|APPROVAL
@BotName addrule <code> <roles> [description]
@BotName delrule <code>
@BotName listrules
@BotName reload
```

**Forms (Admin, APPROVAL mode):**
```
@BotName addfield "Question" text required
@BotName listfields
```

**General:**
```
@BotName help
@BotName getaccess (DM only)
```

---

## Usage Examples

### AUTO Mode
```
@BotName setmode AUTO
@BotName addrule premium123 Premium,VIP Premium members
@BotName addrule free456 Member Free tier
@BotName addrule default Guest Fallback
```
→ User joins via invite → roles assigned instantly

### APPROVAL Mode
```
@BotName setmode APPROVAL
@BotName addfield "Your name?" text required
@BotName addfield "Why join?" textarea required
@BotName addrule premium123 Premium,VIP
```
→ User joins → fills form → admin reviews in `#approvals` → react ✅/❌

---

## Web Admin

Get access: DM bot `@BotName getaccess`

**Features:**
- Manage invite rules
- Build application forms
- Review applications
- Edit message templates
- Configure command permissions

---

## Support

- 🐛 Issues: GitHub Issues
- 💬 Questions: GitHub Discussions

---

## License

MIT
