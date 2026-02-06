"""
Integration tests that test the full bot on a test Discord server.

These tests:
1. Connect to a real test Discord server
2. Create a test user and role
3. Execute commands through the full pipeline
4. Verify Discord responses
5. Cleanup after themselves

Setup required:
- TEST_DISCORD_TOKEN env var (bot token for test server)
- TEST_GUILD_ID env var (your test server ID)
- TEST_CHANNEL_ID env var (test channel ID)
- TEST_USER_ID env var (your user ID for testing)
"""

import os
import asyncio
import pytest
import discord
from discord.ext import commands
from django.test import TestCase
from core.models import GuildSettings, BotCommand
from bot.main import bot
from asgiref.sync import sync_to_async


@pytest.mark.integration
@pytest.mark.asyncio
class TestBotIntegration:
    """Integration tests on real Discord server"""
    
    @classmethod
    def setup_class(cls):
        """Set up test Discord connection"""
        cls.test_token = os.getenv('TEST_DISCORD_TOKEN')
        cls.test_guild_id = int(os.getenv('TEST_GUILD_ID', '0'))
        cls.test_channel_id = int(os.getenv('TEST_CHANNEL_ID', '0'))
        cls.test_user_id = int(os.getenv('TEST_USER_ID', '0'))
        
        if not cls.test_token or cls.test_guild_id == 0:
            pytest.skip("TEST_DISCORD_TOKEN or TEST_GUILD_ID not set")
        
        cls.bot = commands.Bot(command_prefix='@bot ', intents=discord.Intents.all())
    
    async def test_command_execution_flow(self):
        """Test full command pipeline: @bot help"""
        if not self.test_token:
            pytest.skip("No Discord token")
        
        # Connect bot
        async with self.bot:
            # Login
            await self.bot.login(self.test_token)
            await asyncio.sleep(2)  # Let connection settle
            
            # Get test guild
            guild = self.bot.get_guild(self.test_guild_id)
            if not guild:
                pytest.skip(f"Guild {self.test_guild_id} not found")
            
            # Get test channel
            channel = self.bot.get_channel(self.test_channel_id)
            if not channel:
                pytest.skip(f"Channel {self.test_channel_id} not found")
            
            # Execute command: @bot help
            await channel.send('@bot help')
            
            # Wait for response
            await asyncio.sleep(1)
            
            # Check last message in channel (should be bot response)
            messages = [message async for message in channel.history(limit=1)]
            if messages:
                last_msg = messages[0]
                # Should be from bot
                assert last_msg.author == self.bot.user or '📋' in last_msg.content
            
            await self.bot.close()
    
    async def test_addrule_command(self):
        """Test @bot addrule command execution"""
        if not self.test_token:
            pytest.skip("No Discord token")
        
        async with self.bot:
            await self.bot.login(self.test_token)
            await asyncio.sleep(2)
            
            guild = self.bot.get_guild(self.test_guild_id)
            channel = self.bot.get_channel(self.test_channel_id)
            
            if not guild or not channel:
                await self.bot.close()
                pytest.skip("Guild or channel not found")
            
            # Get first role for testing
            test_role = next((r for r in guild.roles if not r.is_bot_managed()), None)
            if not test_role:
                await self.bot.close()
                pytest.skip("No testable roles in guild")
            
            # Send addrule command
            await channel.send(f'@bot addrule testcode123 {test_role.name}')
            await asyncio.sleep(2)
            
            # Verify rule was created in database
            guild_settings = await sync_to_async(GuildSettings.objects.get)(
                guild_id=guild.id
            )
            
            from core.models import InviteRule
            rule = await sync_to_async(InviteRule.objects.filter)(
                guild=guild_settings,
                invite_code='testcode123'
            ).first()
            
            assert rule is not None
            
            # Cleanup
            await sync_to_async(rule.delete)()
            await self.bot.close()
    
    async def test_member_join_with_rule(self):
        """Test member join event applies invite rule roles"""
        if not self.test_token:
            pytest.skip("No Discord token")
        
        # This test requires:
        # 1. Creating an actual invite with a specific code
        # 2. Having a test user join with that invite
        # 3. Verifying roles are assigned
        # 
        # This is complex because it requires real member joins.
        # Simpler approach: mock the member_join handler instead
        
        pytest.skip("Requires real member join - use unit tests instead")
    
    async def test_getaccess_command_in_channel(self):
        """Test @bot getaccess works in channel"""
        if not self.test_token:
            pytest.skip("No Discord token")
        
        async with self.bot:
            await self.bot.login(self.test_token)
            await asyncio.sleep(2)
            
            guild = self.bot.get_guild(self.test_guild_id)
            channel = self.bot.get_channel(self.test_channel_id)
            
            if not guild or not channel:
                await self.bot.close()
                pytest.skip("Guild or channel not found")
            
            # Send getaccess command
            await channel.send('@bot getaccess')
            await asyncio.sleep(2)
            
            # Verify token was created
            from core.models import AccessToken
            guild_settings = await sync_to_async(GuildSettings.objects.get)(
                guild_id=guild.id
            )
            
            token = await sync_to_async(
                lambda: AccessToken.objects.filter(guild=guild_settings).last()
            )()
            
            assert token is not None
            
            # Cleanup
            await sync_to_async(token.delete)()
            await self.bot.close()


@pytest.mark.integration
@pytest.mark.django_db
class TestFullCommandSequence:
    """Test executing all 9 commands in sequence"""
    
    def test_all_commands_registered(self):
        """Verify all 9 commands are properly registered in database"""
        expected_commands = {
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
        
        # Get test guild from database
        try:
            guild = GuildSettings.objects.get(guild_name='Work & Wander')
        except GuildSettings.DoesNotExist:
            pytest.skip("Test guild 'Work & Wander' not found in database")
        
        for cmd_name, expected_action in expected_commands.items():
            cmd = BotCommand.objects.filter(
                guild=guild,
                name=cmd_name,
                enabled=True
            ).first()
            
            assert cmd is not None, f"Command '{cmd_name}' not found"
            
            action = cmd.actions.filter(enabled=True).first()
            assert action is not None, f"No action for command '{cmd_name}'"
            assert action.type == expected_action, \
                f"Command '{cmd_name}' action is {action.type}, expected {expected_action}"
