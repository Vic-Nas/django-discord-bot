import os
import sys
import discord
from discord.ext import commands
from dotenv import load_dotenv
import django
from asgiref.sync import sync_to_async

# Setup Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project.settings')
django.setup()

from core.models import GuildSettings, AccessToken
from handlers.guild_setup import setup_guild
from handlers.member_join import handle_member_join
from handlers.sync import sync_guild_data
from commands import command_registry

load_dotenv()

# Bot setup
intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.invites = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot.remove_command('help')  # We'll make our own


# Cache for invite tracking
invite_cache = {}


@bot.event
async def on_ready():
    print(f'✅ Bot logged in as {bot.user.name}')
    
    # Cache all invites on startup
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
    """When bot joins a new server"""
    print(f'🆕 Joined guild: {guild.name}')
    await setup_guild(bot, guild)
    
    # Cache invites
    try:
        invites = await guild.invites()
        invite_cache[guild.id] = {inv.code: inv.uses for inv in invites}
    except:
        invite_cache[guild.id] = {}


@bot.event
async def on_guild_remove(guild):
    """When bot is removed from a server"""
    print(f'👋 Left guild: {guild.name}')
    if guild.id in invite_cache:
        del invite_cache[guild.id]


@bot.event
async def on_member_join(member):
    """When a member joins the server"""
    await handle_member_join(bot, member, invite_cache)


@bot.event
async def on_invite_create(invite):
    """Track new invites"""
    if invite.guild.id not in invite_cache:
        invite_cache[invite.guild.id] = {}
    invite_cache[invite.guild.id][invite.code] = invite.uses or 0


@bot.event
async def on_invite_delete(invite):
    """Track deleted invites"""
    if invite.guild.id in invite_cache and invite.code in invite_cache[invite.guild.id]:
        del invite_cache[invite.guild.id][invite.code]


@bot.event
async def on_message(message):
    """Handle mentions as commands"""
    if message.author.bot:
        return
    
    # Check if bot is mentioned
    if bot.user in message.mentions:
        # Remove mention and get command
        content = message.content.replace(f'<@{bot.user.id}>', '').replace(f'<@!{bot.user.id}>', '').strip()
        
        if not content:
            return
        
        parts = content.split()
        command_name = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []
        
        # Handle commands
        await command_registry.execute(bot, message, command_name, args, invite_cache)


@bot.event
async def on_raw_reaction_add(payload):
    """Handle reactions for application approval/rejection"""
    if payload.user_id == bot.user.id:
        return
    
    from handlers.application_review import handle_reaction
    await handle_reaction(bot, payload)


if __name__ == '__main__':
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        print('❌ DISCORD_TOKEN not found in environment')
        sys.exit(1)
    
    bot.run(token)
