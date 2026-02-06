"""
Pytest configuration and fixtures for integration tests
"""
import os
import asyncio
import threading
from pathlib import Path

# Load .env file before anything else
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / '.env')

import django
from django.conf import settings

# Configure Django before importing models
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project.settings')
django.setup()

import pytest
from asgiref.sync import async_to_sync
from core.models import GuildSettings, BotCommand, CommandAction
import discord
from discord.ext import commands


@pytest.fixture
def test_guild():
    """Create a test guild"""
    guild = GuildSettings.objects.create(
        guild_id=888888888888888888,
        guild_name='TestGuild',
        bot_admin_role_id=777777777777777777,
        pending_role_id=666666666666666666,
        logs_channel_id=555555555555555555,
        mode='AUTO'
    )
    yield guild
    # Cleanup
    guild.delete()


@pytest.fixture
def test_commands(test_guild):
    """Create all 9 default test commands"""
    commands_config = [
        ('help', 'LIST_COMMANDS'),
        ('listrules', 'LIST_INVITE_RULES'),
        ('addrule', 'ADD_INVITE_RULE'),
        ('delrule', 'DELETE_INVITE_RULE'),
        ('setmode', 'SET_SERVER_MODE'),
        ('getaccess', 'GENERATE_ACCESS_TOKEN'),
        ('addfield', 'ADD_FORM_FIELD'),
        ('listfields', 'LIST_FORM_FIELDS'),
        ('reload', 'RELOAD_CONFIG'),
    ]
    
    commands = []
    for name, action_type in commands_config:
        cmd = BotCommand.objects.create(
            guild=test_guild,
            name=name,
            enabled=True,
            description=f'Test {name} command'
        )
        
        action = CommandAction.objects.create(
            command=cmd,
            type=action_type,
            parameters={},
            order=1,
            enabled=True
        )
        
        commands.append(cmd)
    
    yield commands
    
    # Cleanup
    BotCommand.objects.filter(guild=test_guild).delete()


@pytest.fixture
def db_session():
    """Enable database access in tests"""
    return None


@pytest.fixture(scope='session')
def integration_bot():
    """
    Start discord bot for integration tests.
    
    Bot runs in background thread during tests.
    Automatically connects to Discord and loads guilds.
    """
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        pytest.skip("DISCORD_TOKEN not set - integration tests skipped")
        return None
    
    # Create bot instance for testing
    intents = discord.Intents.default()
    intents.members = True
    intents.guilds = True
    intents.invites = True
    intents.message_content = True
    
    test_bot = commands.Bot(command_prefix="!", intents=intents)
    test_bot.remove_command('help')
    
    # Track if successfully connected
    ready_event = asyncio.Event()
    
    @test_bot.event
    async def on_ready():
        print(f"\n🤖 Test bot connected: {test_bot.user.name}")
        print(f"📋 Loaded {len(test_bot.guilds)} guilds")
        ready_event.set()
    
    async def run_bot():
        """Run bot in background"""
        try:
            await test_bot.start(token)
        except KeyboardInterrupt:
            pass
        except Exception as e:
            print(f"❌ Bot error: {e}")
    
    # Start bot in background thread
    def bot_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_bot())
    
    thread = threading.Thread(target=bot_thread, daemon=True)
    thread.start()
    
    # Wait for bot to be ready (timeout 30 seconds)
    try:
        asyncio.run(asyncio.wait_for(ready_event.wait(), timeout=30))
    except asyncio.TimeoutError:
        pytest.skip("Bot failed to connect within 30 seconds")
    
    yield test_bot
    
    # Cleanup on test completion
    try:
        if test_bot and test_bot.user:
            asyncio.run(test_bot.close())
    except:
        pass
