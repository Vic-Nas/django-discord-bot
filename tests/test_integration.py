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
from unittest.mock import AsyncMock, MagicMock, patch
from django.test import TestCase
from asgiref.sync import sync_to_async
from core.models import GuildSettings, BotCommand, InviteRule, FormField, AccessToken, Application
from bot.execution.action_executor import (
    handle_add_invite_rule,
    handle_delete_invite_rule,
    handle_list_invite_rules,
    handle_set_server_mode,
    handle_list_commands,
    handle_list_form_fields,
    handle_generate_access_token,
    handle_approve_application,
    handle_reject_application,
    handle_reload_config,
)



@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestHandlersWithRealGuild:
    """Test handlers with real Discord guild objects"""
    
    @pytest.fixture(autouse=True)
    async def setup_guild_connection(self, integration_bot):
        """Use the real Discord bot connection"""
        test_guild_id = int(os.getenv('TEST_GUILD_ID', '0'))
        
        if test_guild_id == 0:
            pytest.skip("TEST_GUILD_ID not set in .env")
        
        # Get real guild from connected bot
        self.bot = integration_bot
        self.guild = self.bot.get_guild(test_guild_id)
        
        if not self.guild:
            pytest.skip(
                f"Bot not in guild {test_guild_id}.\n"
                f"Make sure bot is in the Discord guild."
            )
        
        # Get or create test guild settings
        self.guild_settings, _ = await sync_to_async(GuildSettings.objects.get_or_create)(
            guild_id=self.guild.id,
            defaults={'guild_name': f'Test-{self.guild.name}'}
        )
        
        # Pick a real role to use as BotAdmin for admin-gated tests
        non_managed_roles = [r for r in self.guild.roles if not r.is_bot_managed() and not r.is_default()]
        if non_managed_roles:
            self.admin_role = non_managed_roles[0]
            self.guild_settings.bot_admin_role_id = self.admin_role.id
            await sync_to_async(self.guild_settings.save)()
        else:
            self.admin_role = None
        
        yield
    
    @pytest.mark.asyncio
    async def test_add_invite_rule_with_real_roles(self):
        """Test adding invite rule using real Discord roles"""
        # Get available roles
        test_roles = [r for r in self.guild.roles if not r.is_bot_managed() and not r.is_default()]
        
        if len(test_roles) < 1:
            pytest.skip("Not enough roles in guild")
        
        test_role = test_roles[0]
        
        # Create mock message with REAL guild object and BotAdmin role
        message = AsyncMock()
        message.guild = self.guild  # Real Discord guild - already has roles
        message.channel = AsyncMock()
        message.author = MagicMock()
        message.author.id = 999999999999999999
        message.author.roles = [self.admin_role] if self.admin_role else []
        
        # Test handler with real data
        params = {}
        args = ['realrulecode', test_role.name]
        
        await handle_add_invite_rule(self.bot, message, params, args, self.guild_settings)
        
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
        message.guild = self.guild
        message.channel = AsyncMock()
        message.author = MagicMock()
        message.author.roles = [self.admin_role] if self.admin_role else []
        
        params = {}
        args = ['ruleto_delete']
        
        await handle_delete_invite_rule(self.bot, message, params, args, self.guild_settings)
        
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
        
        await handle_list_invite_rules(self.bot, message, {}, self.guild_settings)
        
        # Verify send was called
        assert message.channel.send.called
        
        # Cleanup
        await sync_to_async(rule1.delete)()
        await sync_to_async(rule2.delete)()
    
    @pytest.mark.asyncio
    async def test_approve_application(self):
        """Test approving a pending application"""
        # Create a pending application
        app = await sync_to_async(Application.objects.create)(
            guild=self.guild_settings,
            user_id=888888888888888888,
            user_name='TestApplicant',
            invite_code='testinvite',
            status='PENDING',
            responses={'1': 'Answer 1'}
        )

        # Get a real role from the guild
        test_roles = [r for r in self.guild.roles if not r.is_bot_managed() and not r.is_default()]
        if not test_roles:
            pytest.skip("No roles in guild")

        # Create mock targets
        target_user = AsyncMock()
        target_user.id = 888888888888888888
        target_user.name = 'TestApplicant'
        target_user.display_name = 'TestApplicant'
        target_user.send = AsyncMock()

        mock_member = AsyncMock()
        mock_member.id = 888888888888888888
        mock_member.roles = []
        mock_member.add_roles = AsyncMock()
        mock_member.remove_roles = AsyncMock()

        # Use a fully mocked guild (real Guild has read-only get_member)
        mock_guild = MagicMock()
        mock_guild.id = self.guild.id
        mock_guild.name = self.guild.name
        mock_guild.roles = self.guild.roles  # Real roles for name lookup
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(side_effect=lambda rid: self.guild.get_role(rid))

        message = AsyncMock()
        message.guild = mock_guild
        message.channel = AsyncMock()
        message.author = MagicMock()
        message.author.id = 999999999999999999
        message.author.name = 'TestAdmin'
        message.author.roles = [self.admin_role] if self.admin_role else []
        message.mentions = [target_user]

        args = [f'<@{target_user.id}>', test_roles[0].name]

        await handle_approve_application(self.bot, message, {}, args, self.guild_settings)

        # Verify application was approved
        updated_app = await sync_to_async(Application.objects.get)(id=app.id)
        assert updated_app.status == 'APPROVED' or updated_app.status == 'approved'
        assert message.channel.send.called

        # Cleanup
        await sync_to_async(updated_app.delete)()
    
    @pytest.mark.asyncio
    async def test_generate_access_token_dm_only(self):
        """Test token generation is DM-only (rejects server context)"""
        # Server context should be rejected
        message = AsyncMock()
        message.guild = self.guild  # Server context
        message.channel = AsyncMock()
        message.author = AsyncMock()
        message.author.id = 111111111111111111
        message.author.name = 'TestUser'

        await handle_generate_access_token(self.bot, message, {}, self.guild_settings)

        # Should tell user to go to DMs
        message.channel.send.assert_called_once()
        call_args = message.channel.send.call_args[0][0]
        assert 'DM' in call_args or 'direct message' in call_args.lower()

    @pytest.mark.asyncio
    async def test_generate_access_token_dm_flow(self):
        """Test full DM flow: find BotAdmin guilds, generate token"""
        # Pick a real role to be BotAdmin
        test_roles = [r for r in self.guild.roles if not r.is_bot_managed() and not r.is_default()]
        if not test_roles:
            pytest.skip("No roles available for BotAdmin")

        bot_admin_role = test_roles[0]

        # Set bot_admin_role_id on guild settings
        self.guild_settings.bot_admin_role_id = bot_admin_role.id
        await sync_to_async(self.guild_settings.save)()

        # Find a real member who has that role (or the bot owner)
        member_with_role = None
        for member in self.guild.members:
            if bot_admin_role in member.roles:
                member_with_role = member
                break

        if not member_with_role:
            pytest.skip(f"No member has role '{bot_admin_role.name}' in test guild")

        # Simulate DM context: guild is None, author is the member
        message = AsyncMock()
        message.guild = None  # DM context
        message.author = AsyncMock()
        message.author.id = member_with_role.id
        message.author.name = member_with_role.name
        message.author.send = AsyncMock()

        # Clean up any existing tokens first
        await sync_to_async(
            lambda: AccessToken.objects.filter(
                user_id=member_with_role.id, guild=self.guild_settings
            ).delete()
        )()

        await handle_generate_access_token(self.bot, message, {}, self.guild_settings)

        # Should have sent a DM with the token URL (single guild = no picker)
        message.author.send.assert_called()
        dm_text = message.author.send.call_args[0][0]
        assert 'access' in dm_text.lower() or '/access/' in dm_text

        # Verify token was created in DB
        token = await sync_to_async(
            lambda: AccessToken.objects.filter(
                user_id=member_with_role.id, guild=self.guild_settings
            ).first()
        )()
        assert token is not None, "AccessToken was not created in DB"
        assert token.token  # non-empty token string

        # Calling again should return existing token
        message.author.send.reset_mock()
        await handle_generate_access_token(self.bot, message, {}, self.guild_settings)
        message.author.send.assert_called()
        dm_text_2 = message.author.send.call_args[0][0]
        assert 'already' in dm_text_2.lower() or token.token in dm_text_2

        # Clean up
        await sync_to_async(
            lambda: AccessToken.objects.filter(
                user_id=member_with_role.id, guild=self.guild_settings
            ).delete()
        )()

    @pytest.mark.asyncio
    async def test_generate_access_token_dm_no_admin(self):
        """Test DM flow when user is not BotAdmin in any guild"""
        # Set bot_admin_role_id to a role that nobody has
        self.guild_settings.bot_admin_role_id = 1  # non-existent role
        await sync_to_async(self.guild_settings.save)()

        message = AsyncMock()
        message.guild = None  # DM context
        message.author = AsyncMock()
        message.author.id = 999999999999999999  # Fake user
        message.author.name = 'FakeUser'
        message.author.send = AsyncMock()

        await handle_generate_access_token(self.bot, message, {}, self.guild_settings)

        # Should tell user they're not admin anywhere
        message.author.send.assert_called_once()
        dm_text = message.author.send.call_args[0][0]
        assert 'not' in dm_text.lower() and 'admin' in dm_text.lower()
    
    @pytest.mark.asyncio
    async def test_set_server_mode(self):
        """Test setting server mode (AUTO/APPROVAL)"""
        message = AsyncMock()
        message.guild = self.guild  # Use real guild
        message.channel = AsyncMock()
        message.author = MagicMock()
        message.author.roles = [self.admin_role] if self.admin_role else []
        
        params = {}
        args = ['AUTO']
        
        await handle_set_server_mode(self.bot, message, params, args, self.guild_settings)
        
        # Verify mode was set
        updated_settings = await sync_to_async(GuildSettings.objects.get)(
            guild_id=self.guild_settings.guild_id
        )
        assert updated_settings.mode == 'AUTO'
        
        # Pre-set channel IDs so APPROVAL mode doesn't try to create real channels
        self.guild_settings.approvals_channel_id = 123456789
        self.guild_settings.pending_channel_id = 987654321
        await sync_to_async(self.guild_settings.save)()
        
        # Test APPROVAL mode
        args = ['APPROVAL']
        await handle_set_server_mode(self.bot, message, params, args, self.guild_settings)
        
        updated_settings = await sync_to_async(GuildSettings.objects.get)(
            guild_id=self.guild_settings.guild_id
        )
        assert updated_settings.mode == 'APPROVAL'
    
    @pytest.mark.asyncio
    async def test_list_form_fields(self):
        """Test listing form fields"""
        # Create test fields
        field1 = await sync_to_async(FormField.objects.create)(
            guild=self.guild_settings,
            label='Field1',
            field_type='text',
            order=1
        )
        field2 = await sync_to_async(FormField.objects.create)(
            guild=self.guild_settings,
            label='Field2',
            field_type='textarea',
            order=2
        )
        
        message = AsyncMock()
        message.channel = AsyncMock()
        
        await handle_list_form_fields(self.bot, message, {}, self.guild_settings)
        
        # Verify send was called
        assert message.channel.send.called
        
        # Cleanup
        await sync_to_async(field1.delete)()
        await sync_to_async(field2.delete)()
    
    @pytest.mark.asyncio
    async def test_reload_config(self):
        """Test reloading bot configuration"""
        message = AsyncMock()
        message.guild = self.guild
        message.channel = AsyncMock()
        message.author = MagicMock()
        message.author.roles = [self.admin_role] if self.admin_role else []
        
        # Mock ensure_required_resources to avoid real Discord API calls
        with patch('bot.handlers.guild_setup.ensure_required_resources', new_callable=AsyncMock):
            await handle_reload_config(self.bot, message, {}, self.guild_settings)
        
        # Verify send was called
        assert message.channel.send.called
    
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
        await handle_list_commands(self.bot, message_dm, {}, self.guild_settings)
        assert message_dm.channel.send.called
        
        # Server context
        message_server = AsyncMock()
        message_server.guild = self.guild  # Real guild
        message_server.channel = AsyncMock()
        
        # Should also work in server
        await handle_list_commands(self.bot, message_server, {}, self.guild_settings)
        assert message_server.channel.send.called


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestCommandDatabase:
    """Verify commands match database state"""
    
    @pytest.fixture(autouse=True)
    async def setup_database(self, integration_bot):
        """Setup: ensure guild exists in database"""
        test_guild_id = int(os.getenv('TEST_GUILD_ID', '0'))
        if test_guild_id == 0:
            pytest.skip("TEST_GUILD_ID not set")
        
        # Get or create test guild settings
        self.guild_settings, _ = await sync_to_async(GuildSettings.objects.get_or_create)(
            guild_id=test_guild_id,
            defaults={'guild_name': f'Test Guild'}
        )
        yield
    
    def test_all_10_commands_configured(self):
        """Verify all 10 commands can be created with correct actions via init_defaults"""
        from django.core.management import call_command
        from io import StringIO

        expected = {
            'help': 'LIST_COMMANDS',
            'listrules': 'LIST_INVITE_RULES',
            'addrule': 'ADD_INVITE_RULE',
            'delrule': 'DELETE_INVITE_RULE',
            'setmode': 'SET_SERVER_MODE',
            'getaccess': 'GENERATE_ACCESS_TOKEN',
            'approve': 'APPROVE_APPLICATION',
            'reject': 'REJECT_APPLICATION',
            'listfields': 'LIST_FORM_FIELDS',
            'reload': 'RELOAD_CONFIG',
        }
        
        test_guild_id = int(os.getenv('TEST_GUILD_ID', '0'))
        if test_guild_id == 0:
            pytest.skip("TEST_GUILD_ID not set")
        
        try:
            guild_settings = GuildSettings.objects.get(guild_id=test_guild_id)
        except GuildSettings.DoesNotExist:
            pytest.skip(f"Guild {test_guild_id} not in database")
        
        # Run init_defaults to create commands
        call_command('init_defaults', guild_id=test_guild_id, stdout=StringIO())
        
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
