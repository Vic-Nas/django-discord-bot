"""
Thin Discord bot — pure listener + executor.

Receives Discord events, converts to simple dicts, calls Django services,
then executes the returned actions on Discord.

Zero business logic here. All decisions made by core.services.
"""

import os
import sys
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
import django
from asgiref.sync import sync_to_async

# Setup Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project.settings')
django.setup()

# Run pending migrations on startup (bot service has no Procfile)
from django.core.management import call_command
try:
    call_command('migrate', '--noinput', verbosity=1)
except Exception as e:
    print(f'⚠️ Migration failed: {e}')

from django.db import close_old_connections
from core.services import handle_member_join, handle_member_remove, handle_reaction, handle_command
from bot.handlers.guild_setup import setup_guild, ensure_required_resources

load_dotenv()

# Bot setup
intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.invites = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot.remove_command('help')

# Invite cache (purely Discord gateway state — stays in bot)
invite_cache = {}


async def db_call(func, *args, **kwargs):
    """Call a sync Django function safely: close stale connections, run via sync_to_async."""
    await sync_to_async(close_old_connections)()
    return await sync_to_async(func)(*args, **kwargs)


# ── Action executor ──────────────────────────────────────────────────────────

async def _get_guild_language(actions, context):
    """Determine the guild's auto-translate language from action context."""
    guild_id = None
    for a in actions:
        if a.get('guild_id'):
            guild_id = a['guild_id']
            break
        ch_id = a.get('channel_id')
        if ch_id:
            ch = bot.get_channel(ch_id)
            if ch and hasattr(ch, 'guild'):
                guild_id = ch.guild.id
                break
    if not guild_id and context and 'channel' in context:
        ch = context['channel']
        if hasattr(ch, 'guild') and ch.guild:
            guild_id = ch.guild.id
    if not guild_id:
        return None
    try:
        from core.models import GuildSettings
        gs = await db_call(GuildSettings.objects.get, guild_id=guild_id)
        return gs.language
    except Exception:
        return None


async def execute_actions(actions, context=None):
    """Execute a list of action dicts returned by Django services."""
    # Auto-translate if guild has a language set
    lang = await _get_guild_language(actions, context)
    if lang and lang != 'en':
        from bot.handlers.translate import translate_actions
        actions = await translate_actions(actions, lang)

    for action in actions:
        try:
            await _execute_one(action, context)
        except Exception as e:
            print(f'⚠️ Action failed ({action.get("type")}): {e}')


async def _execute_one(action, context=None):
    """Execute a single action dict."""
    t = action['type']

    if t == 'send_message':
        channel = bot.get_channel(action['channel_id'])
        if channel:
            await channel.send(action['content'])

    elif t == 'send_embed':
        channel = bot.get_channel(action['channel_id'])
        if channel:
            embed = _dict_to_embed(action['embed'])
            await channel.send(embed=embed)

    elif t == 'send_dm':
        user = bot.get_user(action['user_id'])
        if not user:
            try:
                user = await bot.fetch_user(action['user_id'])
            except:
                return
        try:
            await user.send(action['content'])
        except discord.Forbidden:
            pass

    elif t == 'reply':
        # Reply in the same channel as the triggering message
        if context and 'channel' in context:
            await context['channel'].send(action['content'])

    elif t == 'add_role':
        guild = bot.get_guild(action['guild_id'])
        if guild:
            member = guild.get_member(action['user_id'])
            role = guild.get_role(action['role_id'])
            if member and role:
                try:
                    await member.add_roles(role, reason=action.get('reason', ''))
                except discord.Forbidden:
                    print(f'⚠️ No permission to assign role {role.name}')

    elif t == 'remove_role':
        guild = bot.get_guild(action['guild_id'])
        if guild:
            member = guild.get_member(action['user_id'])
            role = guild.get_role(action['role_id'])
            if member and role and role in member.roles:
                try:
                    await member.remove_roles(role)
                except discord.Forbidden:
                    pass

    elif t == 'edit_message':
        channel = bot.get_channel(action['channel_id'])
        if channel:
            try:
                msg = await channel.fetch_message(action['message_id'])
                embed = _dict_to_embed(action['embed'])
                await msg.edit(embed=embed)
            except:
                pass

    elif t == 'clear_reactions':
        channel = bot.get_channel(action['channel_id'])
        if channel:
            try:
                msg = await channel.fetch_message(action['message_id'])
                await msg.clear_reactions()
            except:
                pass

    elif t == 'set_permissions':
        channel = bot.get_channel(action['channel_id'])
        if channel:
            guild = channel.guild
            member = guild.get_member(action['user_id'])
            if member:
                perms = {}
                for perm in action.get('allow', []):
                    perms[perm] = True
                try:
                    await channel.set_permissions(member, **perms)
                except discord.Forbidden:
                    pass

    elif t == 'set_topic':
        channel = bot.get_channel(action['channel_id'])
        if channel:
            try:
                await channel.edit(topic=action['topic'])
            except:
                pass

    elif t == 'send_embed_tracked':
        channel = bot.get_channel(action['channel_id'])
        if channel:
            embed = _dict_to_embed(action['embed'])
            msg = await channel.send(embed=embed)
            # Save message_id to Application for in-place editing later
            app_id = action.get('application_id')
            if app_id and msg:
                from core.models import Application
                await db_call(
                    Application.objects.filter(id=app_id).update,
                    message_id=msg.id,
                )
            # Add reaction buttons
            try:
                await msg.add_reaction('\u2705')
                await msg.add_reaction('\u274c')
            except:
                pass

    elif t == 'cleanup_channel':
        channel = bot.get_channel(action['channel_id'])
        if channel:
            from core.models import Application
            # Get message IDs of pending applications (protected)
            protected = set(await db_call(
                lambda: list(Application.objects.filter(
                    guild__guild_id=action['guild_id'],
                    status='PENDING',
                    message_id__isnull=False,
                ).values_list('message_id', flat=True))
            ))
            count = action.get('count', 50)
            deleted = 0
            async for msg in channel.history(limit=count * 3):
                if msg.author.id != bot.user.id:
                    continue
                if msg.id in protected:
                    continue
                # Don't delete messages with pending embeds
                if msg.embeds and msg.embeds[0].title and 'Application #' in msg.embeds[0].title:
                    if msg.embeds[0].color and msg.embeds[0].color.value == 0xFFA500:
                        continue  # orange = still pending
                try:
                    await msg.delete()
                    deleted += 1
                    if deleted >= count:
                        break
                    await asyncio.sleep(0.5)  # avoid Discord rate limits
                except:
                    pass

    elif t == 'ensure_resources':
        from core.models import GuildSettings
        gs = await db_call(GuildSettings.objects.get, guild_id=action['guild_id'])
        await ensure_required_resources(bot, gs)


def _dict_to_embed(d):
    """Convert a dict to a discord.Embed."""
    embed = discord.Embed(
        title=d.get('title'),
        description=d.get('description'),
        color=d.get('color'),
    )
    for field in d.get('fields', []):
        embed.add_field(
            name=field['name'],
            value=field['value'],
            inline=field.get('inline', False),
        )
    return embed


# ── Invite detection (stays in bot — gateway state) ─────────────────────────

async def detect_invite_used(guild):
    """Compare cached invites to detect which was used."""
    try:
        current_invites = await guild.invites()
        current_uses = {inv.code: inv.uses for inv in current_invites}

        if guild.id not in invite_cache:
            invite_cache[guild.id] = current_uses
            return None

        for code, uses in current_uses.items():
            if uses > invite_cache[guild.id].get(code, 0):
                invite = discord.utils.get(current_invites, code=code)
                invite_cache[guild.id] = current_uses
                return {
                    'code': code,
                    'inviter_id': invite.inviter.id if invite and invite.inviter else None,
                    'inviter_name': invite.inviter.name if invite and invite.inviter else 'Unknown',
                }

        invite_cache[guild.id] = current_uses
        return None
    except Exception as e:
        print(f'❌ Error detecting invite: {e}')
        return None


# ── Events ───────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f'✅ Bot logged in as {bot.user.name}')
    for guild in bot.guilds:
        try:
            invites = await guild.invites()
            invite_cache[guild.id] = {inv.code: inv.uses for inv in invites}
            print(f'📋 Cached {len(invites)} invites for {guild.name}')
        except Exception as e:
            print(f'❌ Failed to cache invites for {guild.name}: {e}')
    print('🚀 Bot is ready!')


@bot.event
async def on_guild_join(guild):
    print(f'🆕 Joined guild: {guild.name}')
    await setup_guild(bot, guild)
    try:
        invites = await guild.invites()
        invite_cache[guild.id] = {inv.code: inv.uses for inv in invites}
    except:
        invite_cache[guild.id] = {}


@bot.event
async def on_guild_remove(guild):
    print(f'👋 Left guild: {guild.name}')
    invite_cache.pop(guild.id, None)


@bot.event
async def on_member_join(member):
    invite_data = await detect_invite_used(member.guild) or {'code': 'unknown', 'inviter_id': None, 'inviter_name': 'Unknown'}

    event = {
        'guild_id': member.guild.id,
        'member': {'id': member.id, 'name': str(member)},
        'invite': invite_data,
    }

    actions = await db_call(handle_member_join, event)
    await execute_actions(actions)


@bot.event
async def on_member_remove(member):
    event = {'guild_id': member.guild.id, 'user_id': member.id}
    await db_call(handle_member_remove, event)


@bot.event
async def on_invite_create(invite):
    if invite.guild.id not in invite_cache:
        invite_cache[invite.guild.id] = {}
    invite_cache[invite.guild.id][invite.code] = invite.uses or 0


@bot.event
async def on_invite_delete(invite):
    if invite.guild.id in invite_cache:
        invite_cache[invite.guild.id].pop(invite.code, None)


@bot.event
async def on_raw_reaction_add(payload):
    """Handle reactions on application embeds."""
    if payload.user_id == bot.user.id:
        return

    channel = bot.get_channel(payload.channel_id)
    if not channel:
        return

    try:
        message = await channel.fetch_message(payload.message_id)
    except:
        return

    # Quick check: is this an application embed?
    if not message.embeds or not message.embeds[0].title or 'Application #' not in message.embeds[0].title:
        return

    # Extract application ID from embed title
    try:
        title_part = message.embeds[0].title.split('#')[1]
        app_id = int(title_part.split()[0].strip(' ——-'))
    except:
        return

    guild = bot.get_guild(payload.guild_id) if payload.guild_id else None
    if not guild:
        return

    member = guild.get_member(payload.user_id)
    if not member:
        return

    # Check admin role before calling service
    from core.models import GuildSettings
    try:
        gs = await db_call(GuildSettings.objects.get, guild_id=guild.id)
    except:
        return

    admin_role = guild.get_role(gs.bot_admin_role_id)
    if not admin_role or admin_role not in member.roles:
        try:
            await message.remove_reaction(payload.emoji, member)
        except:
            pass
        return

    # Check applicant is still in guild
    from core.models import Application
    try:
        app = await db_call(Application.objects.get, id=app_id, status='PENDING')
    except:
        return

    applicant = guild.get_member(app.user_id)
    if not applicant:
        from bot.handlers.templates import get_template_async
        try:
            gs_for_tpl = await db_call(GuildSettings.objects.get, guild_id=guild.id)
            msg_text = await get_template_async(gs_for_tpl, 'USER_LEFT_SERVER')
        except Exception:
            msg_text = "❌ User has left the server."
        await channel.send(msg_text)
        return

    # Convert embed to dict for service
    original_embed = {
        'title': message.embeds[0].title,
        'color': message.embeds[0].color.value if message.embeds[0].color else None,
        'fields': [{'name': f.name, 'value': f.value, 'inline': f.inline} for f in message.embeds[0].fields],
    }

    event = {
        'guild_id': guild.id,
        'channel_id': channel.id,
        'message_id': message.id,
        'emoji': str(payload.emoji),
        'application_id': app_id,
        'admin': {'id': member.id, 'name': member.name},
        'original_embed': original_embed,
    }

    actions = await db_call(handle_reaction, event)
    await execute_actions(actions)


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if bot.user not in message.mentions:
        return

    content = message.content.replace(f'<@{bot.user.id}>', '').replace(f'<@!{bot.user.id}>', '').strip()
    if not content:
        return

    parts = content.split()
    command_name = parts[0].lower()
    args = parts[1:] if len(parts) > 1 else []

    # Build event dict with all data Django needs
    event = {
        'command': command_name,
        'args': args,
        'channel_id': message.channel.id,
        'author': {
            'id': message.author.id,
            'name': message.author.name,
            'role_ids': [r.id for r in message.author.roles] if message.guild else [],
        },
    }

    if message.guild:
        event['guild_id'] = message.guild.id
        # User mentions (excluding bot)
        event['user_mentions'] = [
            {'id': u.id, 'name': u.display_name}
            for u in message.mentions if u.id != bot.user.id
        ]
        # Role mentions
        event['role_mentions'] = [
            {'id': r.id, 'name': r.name}
            for r in message.role_mentions
        ]
        # Channel mentions
        event['channel_mentions'] = [
            {'id': c.id, 'name': c.name}
            for c in message.channel_mentions
        ]

        # For commands that need guild data (reload, addrule)
        if command_name in ('reload', 'addrule'):
            event['guild_roles'] = [{'id': r.id, 'name': r.name} for r in message.guild.roles]
            event['guild_channels'] = [{'id': c.id, 'name': c.name} for c in message.guild.text_channels]
        if command_name == 'reload':
            event['guild_members'] = [{'id': m.id, 'name': str(m), 'bot': m.bot} for m in message.guild.members]

        # For bulk approve: members with the mentioned role
        if command_name == 'approve' and message.role_mentions:
            target_role = message.role_mentions[0]
            event['members_with_role'] = [
                {'id': m.id, 'name': m.display_name}
                for m in message.guild.members if target_role in m.roles
            ]
    else:
        event['guild_id'] = None

    # For getaccess: find guilds where user is admin
    if command_name == 'getaccess' and not message.guild:
        admin_guilds = []
        from core.models import GuildSettings
        all_gs = await db_call(lambda: list(GuildSettings.objects.filter(bot_admin_role_id__isnull=False)))
        for gs in all_gs:
            guild = bot.get_guild(gs.guild_id)
            if not guild:
                continue
            member = guild.get_member(message.author.id)
            if not member:
                continue
            if any(r.id == gs.bot_admin_role_id for r in member.roles):
                admin_guilds.append({'guild_id': gs.guild_id, 'guild_name': guild.name})

        if len(admin_guilds) > 1:
            # Multi-guild selection flow
            guild_list = '\n'.join(f'**{i+1}.** {g["guild_name"]}' for i, g in enumerate(admin_guilds))
            from bot.handlers.templates import get_template_async
            tpl = await get_template_async(None, 'GETACCESS_PICK_SERVER')
            await message.author.send(tpl.format(guild_list=guild_list))

            def check(m):
                return m.author.id == message.author.id and m.guild is None and m.content.isdigit()

            try:
                reply = await bot.wait_for('message', check=check, timeout=30.0)
                choice = int(reply.content)
                if choice < 1 or choice > len(admin_guilds):
                    await message.author.send("❌ Invalid choice.")
                    return
                event['admin_guilds'] = [admin_guilds[choice - 1]]
            except:
                await message.author.send("⏰ Timed out. Please try again.")
                return
        else:
            event['admin_guilds'] = admin_guilds

    context = {'channel': message.channel}
    actions = await db_call(handle_command, event)
    await execute_actions(actions, context)


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        print('❌ DISCORD_TOKEN not found in environment')
        sys.exit(1)
    bot.run(token)
