"""
Unit tests for action handlers using mocked Discord objects
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from django.test import TestCase
from asgiref.sync import sync_to_async
from core.models import GuildSettings, BotCommand, CommandAction, InviteRule, DiscordRole
from bot.execution.action_executor import (
    execute_command_actions,
    handle_add_invite_rule,
    handle_delete_invite_rule,
    handle_list_invite_rules,
    ExecutionError,
)


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestActionHandlers(TestCase):
    """Test command action handlers with mocked Discord"""
    
    def setUp(self):
        """Create test guild and commands - runs in sync context"""
        self.guild_settings = GuildSettings.objects.create(
            guild_id=999999999999999999,
            guild_name='TestGuild',
            bot_admin_role_id=111111111111111111,
            mode='AUTO'
        )
        
        # Create a test command
        self.command = BotCommand.objects.create(
            guild=self.guild_settings,
            name='test',
            enabled=True,
            description='Test command'
        )
        
        # Create test action
        self.action = CommandAction.objects.create(
            command=self.command,
            type='SEND_MESSAGE',
            parameters={'text': 'Hello test'},
            order=1,
            enabled=True
        )
    
    def tearDown(self):
        """Clean up test data"""
        self.guild_settings.delete()
    
    def _make_message_with_admin(self):
        """Create a mock message where author has BotAdmin role"""
        message = AsyncMock()
        message.guild = AsyncMock()
        message.channel = AsyncMock()
        
        # BotAdmin role mock
        bot_admin_role = MagicMock()
        bot_admin_role.id = self.guild_settings.bot_admin_role_id
        bot_admin_role.name = 'BotAdmin'
        
        # Author has BotAdmin role
        message.author = MagicMock()
        message.author.roles = [bot_admin_role]
        
        # guild.get_role returns the admin role when asked for bot_admin_role_id
        def get_role_side_effect(role_id):
            if role_id == self.guild_settings.bot_admin_role_id:
                return bot_admin_role
            return None
        message.guild.get_role = MagicMock(side_effect=get_role_side_effect)
        
        return message, bot_admin_role
    
    @pytest.mark.asyncio
    async def test_add_invite_rule_success(self):
        """Test adding an invite rule"""
        # Create real DiscordRole objects first (in sync context via sync_to_async)
        await sync_to_async(DiscordRole.objects.create)(
            guild=self.guild_settings,
            discord_id=111111111111111111,
            name='Admin'
        )
        await sync_to_async(DiscordRole.objects.create)(
            guild=self.guild_settings,
            discord_id=222222222222222222,
            name='Member'
        )
        
        # Mock Discord objects with BotAdmin
        message, bot_admin_role = self._make_message_with_admin()
        
        # Create proper mock Discord roles that have .name attribute
        discord_admin = MagicMock()
        discord_admin.name = 'Admin'
        discord_admin.id = 111111111111111111
        
        discord_member = MagicMock()
        discord_member.name = 'Member'
        discord_member.id = 222222222222222222
        
        message.guild.roles = [bot_admin_role, discord_admin, discord_member]
        # Override get_role to also return the admin role for admin_role_id
        def get_role(role_id):
            if role_id == self.guild_settings.bot_admin_role_id:
                return bot_admin_role
            if role_id == 111111111111111111:
                return discord_admin
            return None
        message.guild.get_role = MagicMock(side_effect=get_role)
        
        bot = AsyncMock()
        
        # Call handler
        params = {}
        args = ['testcode', 'Admin,Member', 'Test rule']
        
        # Should not raise
        await handle_add_invite_rule(bot, message, params, args, self.guild_settings)
        
        # Verify rule was created in database
        rule = await sync_to_async(InviteRule.objects.get)(
            guild=self.guild_settings, 
            invite_code='testcode'
        )
        assert rule.description == 'Test rule'
        role_count = await sync_to_async(lambda: rule.roles.count())()
        assert role_count == 2  # Both roles attached
        
        # Verify cleanup message was sent
        assert message.channel.send.called
    
    @pytest.mark.asyncio
    async def test_add_invite_rule_invalid_role(self):
        """Test adding rule with non-existent role"""
        message, bot_admin_role = self._make_message_with_admin()
        
        # Create a role that exists in Discord but not the one we're asking for
        discord_admin = MagicMock()
        discord_admin.name = 'Admin'
        discord_admin.id = 111111111111111111
        
        message.guild.roles = [bot_admin_role, discord_admin]
        
        bot = AsyncMock()
        params = {}
        args = ['badcode', 'NonExistent']
        
        # Should raise ExecutionError about missing role
        with pytest.raises(ExecutionError, match="Role not found"):
            await handle_add_invite_rule(bot, message, params, args, self.guild_settings)
    
    @pytest.mark.asyncio
    async def test_delete_invite_rule(self):
        """Test deleting an invite rule"""
        # Create rule first (in sync context)
        await sync_to_async(InviteRule.objects.create)(
            guild=self.guild_settings,
            invite_code='todelete'
        )
        
        message, _ = self._make_message_with_admin()
        bot = AsyncMock()
        
        params = {}
        args = ['todelete']
        
        # Delete it
        await handle_delete_invite_rule(bot, message, params, args, self.guild_settings)
        
        # Verify it's gone from database
        exists = await sync_to_async(
            lambda: InviteRule.objects.filter(guild=self.guild_settings, invite_code='todelete').exists()
        )()
        assert not exists
        
        # Verify confirmation message was sent
        assert message.channel.send.called
    
    @pytest.mark.asyncio
    async def test_delete_nonexistent_rule(self):
        """Test deleting a rule that doesn't exist"""
        message, _ = self._make_message_with_admin()
        bot = AsyncMock()
        
        params = {}
        args = ['doesnotexist']
        
        # Should raise
        with pytest.raises(ExecutionError, match="Rule not found"):
            await handle_delete_invite_rule(bot, message, params, args, self.guild_settings)
    
    @pytest.mark.asyncio
    async def test_list_invite_rules(self):
        """Test listing invite rules"""
        # Create some rules (in sync context)
        await sync_to_async(InviteRule.objects.create)(
            guild=self.guild_settings,
            invite_code='code1',
            description='Rule 1'
        )
        await sync_to_async(InviteRule.objects.create)(
            guild=self.guild_settings,
            invite_code='code2',
            description='Rule 2'
        )
        
        message = AsyncMock()
        message.channel = AsyncMock()
        bot = AsyncMock()
        
        params = {}
        
        # List them
        await handle_list_invite_rules(bot, message, params, self.guild_settings)
        
        # Verify message was sent
        assert message.channel.send.called
        
        # Get the sent message
        call_args = message.channel.send.call_args
        # Should be called with either embed or text
        assert call_args is not None
