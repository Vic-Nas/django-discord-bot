"""
Pytest configuration and fixtures for integration tests
"""
import os
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
