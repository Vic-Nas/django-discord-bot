# Discord Role Bot

Manage Discord roles via invite links with web admin. Two modes: **AUTO** (instant role assignment) or **APPROVAL** (application forms with admin review).

## [🔗 Invite Bot](#) | [📖 Documentation](#commands)

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

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/your-template)

1. Click Deploy on Railway ([referral link](https://railway.app?referralCode=YOUR_CODE))
2. Add PostgreSQL database
3. Set environment variables (see `.env.example`)
4. Run in Railway terminal:
   ```bash
   python manage.py makemigrations
   python manage.py migrate
   python manage.py init_defaults
   ```
5. Invite bot to your Discord server
6. Give yourself `@BotAdmin` role
7. DM bot: `@BotName getaccess`
8. Configure via web panel

### Self-Host

**Requirements:** Python 3.10+, PostgreSQL, Cloudinary account

```bash
git clone https://github.com/yourusername/discord-role-bot.git
cd discord-role-bot
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your credentials
python manage.py makemigrations
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

---

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

- 📖 Full docs in `/docs` folder
- 🐛 Issues: GitHub Issues
- 💬 Questions: GitHub Discussions

---

## License

MIT
