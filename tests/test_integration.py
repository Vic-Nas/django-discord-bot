"""
Integration tests with real Discord connection using TEST_GUILD_ID from .env

These tests:
1. Connect to a real test Discord server (uses BOT_TOKEN from .env)
2. Use real guild objects, roles, and channels
3. Test handlers with actual Discord data
4. Verify database changes
5. Test both server and DM contexts
6. Clean up after themselves

Setup required:
- TEST_GUILD_ID in .env (your test server ID)
- BOT_TOKEN in .env (already exists)
- Bot must be Admin in test server
"""

import os
import asyncio
import pytest
import discord
from unittest.mock import AsyncMock, MagicMock
from django.test import TestCase
from asgiref.sync import sync_to_async
from core.models import GuildSettings, BotCommand, InviteRule, FormField, AccessToken
from bot.execution.action_executor import (
    handle_add_invite_rule,
    handle_delete_invite_rule,
    handle_list_invite_rules,
    handle_set_server_mode,
    handle_list_commands,
    handle_add_form_field,
    handle_generate_access_token,
)
from bot.main import bot as main_bot


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestHandlersWithRealGuild:
    """Test handlers with real Discord guild objects"""
    
    @pytest.fixture(scope="class", autouse=True)
    async def setup_guild_connection(self):
        """Connect to Discord and get real guild"""
        test_guild_id = int(os.getenv('TEST_GUILD_ID', '0'))
        
        if test_guild_id == 0:
            pytest.skip("TEST_GUILD_ID not set in .env")
        
        # Connect bot to Discord
        self.connected = False
        try:
            await main_bot.login()
            self.connected = True
            await asyncio.sleep(2)
        except Exception as e:
            pytest.skip(f"Could not connect to Discord: {e}")
        
        # Get real guild
        self.guild = main_bot.get_guild(test_guild_id)
        if not self.guild:
            pytest.skip(f"Guild {test_guild_id} not found")
        
        # Get or create test guild settings
        self.guild_settings, _ = await sync_to_async(GuildSettings.objects.get_or_create)(
            guild_id=self.guild.id,
            defaults={'guild_name': f'Test-{self.guild.name}'}
        )
        
        yield
        
        # Cleanup
        if self.connected:
            await main_bot.close()
    
    @pytest.mark.asyncio
    async def test_add_invite_rule_with_real_roles(self):
        """Test adding invite rule using real Discord roles"""
        # Get available roles
        test_roles = [r for r in self.guild.roles if not r.is_bot_managed() and not r.is_default()]
        
        if len(test_roles) < 1:
            pytest.skip("Not enough roles in guild")
        
        test_role = test_roles[0]
        
        # Create mock message with REAL guild object
        message = AsyncMock()
        message.guild = self.guild  # Real Discord guild
        message.guild.roles = self.guild.roles  # Real roles
        message.channel = AsyncMock()
        message.author = AsyncMock()
        message.author.id = 999999999999999999
        
        # Test handler with real data
        params = {}
        args = ['realrulecode', test_role.name]
        
        await handle_add_invite_rule(main_bot, message, params, args, self.guild_settings)
        
        # Verify rule was created with real role
        rule = await sync_to_async(InviteRule.objects.get)(
            guild=self.guild_settings,
            invite_code='realrulecode'
        )
        
        # Verify the role is linked
        assert await sync_to_async(lambda: rule.roles.count())() > 0
        
        # Cleanup
        await sync_to_async(rule.delete)()
    
    @pytest.mark.asyncio
    async def test_delete_invite_rule(self):
        """Test deleting invite rule"""
        # Create rule first
        rule = await sync_to_async(InviteRule.objects.create)(
            guild=self.guild_settings,
            invite_code='ruleto_delete'
        )
        
        message = AsyncMock()
        message.channel = AsyncMock()
        
        params = {}
        args = ['ruleto_delete']
        
        await handle_delete_invite_rule(main_bot, message, params, args, self.guild_settings)
        
        # Verify deleted
        exists = await sync_to_async(
            lambda: InviteRule.objects.filter(invite_code='ruleto_delete').exists()
        )()
        assert not exists
    
    @pytest.mark.asyncio
    async def test_list_invite_rules(self):
        """Test listing rules"""
        # Create test rules
        rule1 = await sync_to_async(InviteRule.objects.create)(
            guild=self.guild_settings,
            invite_code='test1',
            description='Test Rule 1'
        )
        rule2 = await sync_to_async(InviteRule.objects.create)(
            guild=self.guild_settings,
            invite_code='test2',
            description='Test Rule 2'
        )
        
        message = AsyncMock()
        message.channel = AsyncMock()
        
        await handle_list_invite_rules(main_bot, message, {}, self.guild_settings)
        
        # Verify send was called
        assert message.channel.send.called
        
        # Cleanup
        await sync_to_async(rule1.delete)()
        await sync_to_async(rule2.delete)()
    
    @pytest.mark.asyncio
    async def test_add_form_field(self):
        """Test adding form field"""
        message = AsyncMock()
        message.channel = AsyncMock()
        
        params = {}
        args = ['TestField', 'text']
        
        await handle_add_form_field(main_bot, message, params, args, self.guild_settings)
        
        # Verify field was created
        field = await sync_to_async(FormField.objects.filter)(
            guild=self.guild_settings,
            label='TestField'
        ).first()
        
        assert field is not None
        
        # Cleanup
        await sync_to_async(field.delete)()
    
    @pytest.mark.asyncio
    async def test_generate_access_token(self):
        """Test token generation"""
        message = AsyncMock()
        message.channel = AsyncMock()
        message.author = AsyncMock()
        message.author.id = 111111111111111111
        message.author.mention = '<@111111111111111111>'
        
        await handle_generate_access_token(main_bot, message, {}, self.guild_settings)
        
        # Verify token was created
        token = await sync_to_async(
            lambda: AccessToken.objects.filter(guild=self.guild_settings).last()
        )()
        
        assert token is not None
        
        # Cleanup
        await sync_to_async(token.delete)()
    
    @pytest.mark.asyncio
    async def test_handler_in_dm_context(self):
        """Test handler detects DM vs server context"""
        # DM context (no guild)
        message_dm = AsyncMock()
        message_dm.guild = None
        message_dm.channel = AsyncMock()
        message_dm.author = AsyncMock()
        message_dm.author.id = 222222222222222222
        message_dm.author.mention = '<@222222222222222222>'
        
        # Should work fine in DM
        await handle_list_commands(main_bot, message_dm, {}, self.guild_settings)
        assert message_dm.channel.send.called
        
        # Server context
        message_server = AsyncMock()
        message_server.guild = self.guild  # Real guild
        message_server.channel = AsyncMock()
        
        # Should also work in server
        await handle_list_commands(main_bot, message_server, {}, self.guild_settings)
        assert message_server.channel.send.called


@pytest.mark.integration
@pytest.mark.django_db
class TestCommandDatabase:
    """Verify commands match database state"""
    
    def test_all_9_commands_configured(self):
        """Verify all 9 commands exist with correct actions"""
        expected = {
            'help': 'LIST_COMMANDS',
            'listrules': 'LIST_INVITE_RULES',
            'addrule': 'ADD_INVITE_RULE',
            'delrule': 'DELETE_INVITE_RULE',
            'setmode': 'SET_SERVER_MODE',
            'getaccess': 'GENERATE_ACCESS_TOKEN',
            'addfield': 'ADD_FORM_FIELD',
            'listfields': 'LIST_FORM_FIELDS',
            'reload': 'RELOAD_CONFIG',
        }
        
        # Get test guild
        test_guild_id = int(os.getenv('TEST_GUILD_ID', '0'))
        if test_guild_id == 0:
            pytest.skip("TEST_GUILD_ID not set")
        
        try:
            guild_settings = GuildSettings.objects.get(guild_id=test_guild_id)
        except GuildSettings.DoesNotExist:
            pytest.skip(f"Guild {test_guild_id} not in database")
        
        # Verify each command
        for cmd_name, expected_type in expected.items():
            cmd = BotCommand.objects.filter(
                guild=guild_settings,
                name=cmd_name,
                enabled=True
            ).first()
            
            assert cmd is not None, f"'{cmd_name}' command not found"
            
            action = cmd.actions.filter(enabled=True).first()
            assert action is not None, f"'{cmd_name}' has no action"
            assert action.type == expected_type, \
                f"'{cmd_name}' action is {action.type}, expected {expected_type}"
