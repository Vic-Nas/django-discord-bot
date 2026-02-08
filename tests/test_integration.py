"""
Integration tests with real Discord connection using TEST_GUILD_ID from .env

These tests use on the real Discord connection but test the full flow:
bot event → core.services → action list → verify

Setup required:
- TEST_GUILD_ID in .env (your test server ID)
- DISCORD_TOKEN in .env (already exists)
- Bot must be Admin in test server
"""

import os
import asyncio
import pytest
import discord
from unittest.mock import AsyncMock, MagicMock, patch
from asgiref.sync import sync_to_async
from core.models import (
    GuildSettings, BotCommand, CommandAction, InviteRule,
    DiscordRole, FormField, AccessToken, Application, Dropdown,
)
from core.services import handle_command, handle_member_join, handle_member_remove


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestServicesWithRealGuild:  # needs transaction=True for async
    """Test core.services against a real Discord guild's data."""

    @pytest.fixture(autouse=True)
    async def setup_guild_connection(self, integration_bot):
        test_guild_id = int(os.getenv('TEST_GUILD_ID', '0'))
        if test_guild_id == 0:
            pytest.skip("TEST_GUILD_ID not set in .env")

        self.bot = integration_bot
        self.guild = self.bot.get_guild(test_guild_id)
        if not self.guild:
            pytest.skip(f"Bot not in guild {test_guild_id}")

        self.gs, _ = await sync_to_async(GuildSettings.objects.get_or_create)(
            guild_id=self.guild.id,
            defaults={'guild_name': f'Test-{self.guild.name}'}
        )

        # Pick a non-managed role as BotAdmin
        non_managed = [r for r in self.guild.roles if not r.is_bot_managed() and not r.is_default()]
        if non_managed:
            self.admin_role = non_managed[0]
            self.gs.bot_admin_role_id = self.admin_role.id
            await sync_to_async(self.gs.save)()
        else:
            self.admin_role = None

        # Ensure commands exist
        for name, action_type in [
            ('addrule', 'ADD_INVITE_RULE'),
            ('delrule', 'DELETE_INVITE_RULE'),
            ('listrules', 'LIST_INVITE_RULES'),
            ('setmode', 'SET_SERVER_MODE'),
            ('help', 'LIST_COMMANDS'),
            ('listfields', 'LIST_FORM_FIELDS'),
            ('reload', 'RELOAD_CONFIG'),
            ('approve', 'APPROVE_APPLICATION'),
            ('reject', 'REJECT_APPLICATION'),
            ('getaccess', 'GENERATE_ACCESS_TOKEN'),
        ]:
            cmd, _ = await sync_to_async(BotCommand.objects.get_or_create)(
                guild=self.gs, name=name, defaults={'enabled': True, 'description': f'{name} cmd'}
            )
            await sync_to_async(CommandAction.objects.get_or_create)(
                command=cmd, defaults={'type': action_type, 'parameters': {}, 'order': 1, 'enabled': True}
            )

        yield

    def _admin_event(self, command, args=None, **extra):
        event = {
            'command': command,
            'args': args or [],
            'guild_id': self.gs.guild_id,
            'channel_id': self.gs.logs_channel_id or 123456,
            'author': {
                'id': 999999999999999999,
                'name': 'TestAdmin',
                'role_ids': [self.admin_role.id] if self.admin_role else [],
            },
            'user_mentions': [],
            'role_mentions': [],
        }
        event.update(extra)
        return event

    @pytest.mark.asyncio
    async def test_addrule_with_real_roles(self):
        """Test adding invite rule using real Discord role names."""
        test_roles = [r for r in self.guild.roles if not r.is_bot_managed() and not r.is_default()]
        if not test_roles:
            pytest.skip("No roles in guild")

        role = test_roles[0]
        # Ensure role is in DB
        await sync_to_async(DiscordRole.objects.update_or_create)(
            discord_id=role.id, guild=self.gs, defaults={'name': role.name}
        )

        guild_roles = [{'id': r.id, 'name': r.name} for r in self.guild.roles]
        event = self._admin_event('addrule', ['realrulecode', role.name], guild_roles=guild_roles)
        actions = await sync_to_async(handle_command)(event)
        assert any('realrulecode' in a.get('content', '') for a in actions)

        rule = await sync_to_async(InviteRule.objects.get)(guild=self.gs, invite_code='realrulecode')
        assert await sync_to_async(lambda: rule.roles.count())() > 0
        await sync_to_async(rule.delete)()

    @pytest.mark.asyncio
    async def test_delete_invite_rule(self):
        rule = await sync_to_async(InviteRule.objects.create)(guild=self.gs, invite_code='ruleto_delete')
        event = self._admin_event('delrule', ['ruleto_delete'])
        await sync_to_async(handle_command)(event)

        exists = await sync_to_async(lambda: InviteRule.objects.filter(invite_code='ruleto_delete').exists())()
        assert not exists

    @pytest.mark.asyncio
    async def test_list_invite_rules(self):
        r1 = await sync_to_async(InviteRule.objects.create)(guild=self.gs, invite_code='t1', description='Rule 1')
        r2 = await sync_to_async(InviteRule.objects.create)(guild=self.gs, invite_code='t2', description='Rule 2')

        actions = await sync_to_async(handle_command)(self._admin_event('listrules'))
        assert any(a['type'] == 'send_embed' for a in actions)

        await sync_to_async(r1.delete)()
        await sync_to_async(r2.delete)()

    @pytest.mark.asyncio
    async def test_approve_application(self):
        app = await sync_to_async(Application.objects.create)(
            guild=self.gs, user_id=888888888888888888,
            user_name='TestApplicant', invite_code='testinvite',
            status='PENDING', responses={'1': 'Answer 1'}
        )

        event = self._admin_event(
            'approve', [f'<@888888888888888888>'],
            user_mentions=[{'id': 888888888888888888, 'name': 'TestApplicant'}]
        )
        actions = await sync_to_async(handle_command)(event)

        # Should be deleted
        exists = await sync_to_async(lambda: Application.objects.filter(id=app.id).exists())()
        assert not exists
        assert any(a['type'] == 'send_dm' for a in actions)

    @pytest.mark.asyncio
    async def test_set_server_mode(self):
        event = self._admin_event('setmode', ['AUTO'])
        await sync_to_async(handle_command)(event)
        gs = await sync_to_async(GuildSettings.objects.get)(guild_id=self.gs.guild_id)
        assert gs.mode == 'AUTO'

        # Pre-set channels to avoid real resource creation
        self.gs.approvals_channel_id = 123456789
        self.gs.pending_channel_id = 987654321
        await sync_to_async(self.gs.save)()

        event = self._admin_event('setmode', ['APPROVAL'])
        actions = await sync_to_async(handle_command)(event)
        gs = await sync_to_async(GuildSettings.objects.get)(guild_id=self.gs.guild_id)
        assert gs.mode == 'APPROVAL'

    @pytest.mark.asyncio
    async def test_list_form_fields(self):
        dropdown = await sync_to_async(Dropdown.objects.create)(
            guild=self.gs, name='Role Picker', source_type='ROLES', multiselect=False
        )
        f1 = await sync_to_async(FormField.objects.create)(
            guild=self.gs, label='Your Name', field_type='text', placeholder='Enter your name', order=1
        )
        f2 = await sync_to_async(FormField.objects.create)(
            guild=self.gs, label='Desired Role', field_type='dropdown', dropdown=dropdown, order=2
        )

        actions = await sync_to_async(handle_command)(self._admin_event('listfields'))
        assert any(a['type'] == 'send_embed' for a in actions)

        await sync_to_async(f2.delete)()
        await sync_to_async(f1.delete)()
        await sync_to_async(dropdown.delete)()

    @pytest.mark.asyncio
    async def test_reload_config(self):
        guild_roles = [{'id': r.id, 'name': r.name} for r in self.guild.roles]
        guild_channels = [{'id': c.id, 'name': c.name} for c in self.guild.text_channels]

        event = self._admin_event('reload', guild_roles=guild_roles, guild_channels=guild_channels, guild_members=[])
        actions = await sync_to_async(handle_command)(event)
        assert any(a['type'] == 'ensure_resources' for a in actions)


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestCommandDatabase:  # needs transaction=True for async
    """Verify commands match database state."""

    @pytest.fixture(autouse=True)
    async def setup_database(self, integration_bot):
        test_guild_id = int(os.getenv('TEST_GUILD_ID', '0'))
        if test_guild_id == 0:
            pytest.skip("TEST_GUILD_ID not set")

        self.guild_settings, _ = await sync_to_async(GuildSettings.objects.get_or_create)(
            guild_id=test_guild_id, defaults={'guild_name': 'Test Guild'}
        )
        yield

    def test_all_10_commands_configured(self):
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
            gs = GuildSettings.objects.get(guild_id=test_guild_id)
        except GuildSettings.DoesNotExist:
            pytest.skip(f"Guild {test_guild_id} not in database")

        call_command('init_defaults', guild_id=test_guild_id, stdout=StringIO())

        for cmd_name, expected_type in expected.items():
            cmd = BotCommand.objects.filter(guild=gs, name=cmd_name, enabled=True).first()
            assert cmd is not None, f"'{cmd_name}' command not found"
            action = cmd.actions.filter(enabled=True).first()
            assert action is not None, f"'{cmd_name}' has no action"
            assert action.type == expected_type, f"'{cmd_name}' action is {action.type}, expected {expected_type}"
