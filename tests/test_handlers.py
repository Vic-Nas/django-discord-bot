"""
Unit tests for core.services — pure Django, no Discord mocks needed.

Services take plain dicts and return action lists. Tests verify:
- Correct actions are returned
- Database state changes as expected
- Permission gates work
"""
import pytest
from django.test import TestCase
from core.models import (
    GuildSettings, BotCommand, CommandAction, InviteRule,
    DiscordRole, DiscordChannel, Application,
)
from core.services import handle_command, handle_member_join, handle_member_remove


@pytest.mark.django_db
class TestServiceHandlers(TestCase):
    """Test core.services with plain dicts — no Discord needed."""

    def setUp(self):
        self.gs = GuildSettings.objects.create(
            guild_id=999999999999999999,
            guild_name='TestGuild',
            bot_admin_role_id=111111111111111111,
            pending_role_id=666666666666666666,
            logs_channel_id=555555555555555555,
            mode='AUTO',
        )
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
        ]:
            cmd = BotCommand.objects.create(guild=self.gs, name=name, enabled=True, description=f'{name} cmd')
            CommandAction.objects.create(command=cmd, type=action_type, parameters={}, order=1, enabled=True)

    def tearDown(self):
        self.gs.delete()

    def _admin_event(self, command, args=None, **extra):
        event = {
            'command': command,
            'args': args or [],
            'guild_id': self.gs.guild_id,
            'channel_id': 555555555555555555,
            'author': {'id': 100, 'name': 'Admin', 'role_ids': [self.gs.bot_admin_role_id]},
            'user_mentions': [],
            'role_mentions': [],
        }
        event.update(extra)
        return event

    # ── addrule / delrule / listrules ─────────────────────────────────────

    def test_addrule_success(self):
        DiscordRole.objects.create(guild=self.gs, discord_id=222, name='Member')
        event = self._admin_event('addrule', ['testcode', 'Member', 'A', 'rule'],
                                  guild_roles=[{'id': 222, 'name': 'Member'}])
        actions = handle_command(event)
        assert any('testcode' in a.get('content', '') for a in actions)
        assert InviteRule.objects.filter(guild=self.gs, invite_code='testcode').exists()

    def test_addrule_bad_role(self):
        event = self._admin_event('addrule', ['code', 'Fake'], guild_roles=[])
        actions = handle_command(event)
        assert any('not found' in a.get('content', '').lower() or 'error' in a.get('content', '').lower() for a in actions)

    def test_delrule_success(self):
        InviteRule.objects.create(guild=self.gs, invite_code='todelete')
        actions = handle_command(self._admin_event('delrule', ['todelete']))
        assert not InviteRule.objects.filter(guild=self.gs, invite_code='todelete').exists()

    def test_delrule_not_found(self):
        actions = handle_command(self._admin_event('delrule', ['nope']))
        assert any('not found' in a.get('content', '').lower() or 'error' in a.get('content', '').lower() for a in actions)

    def test_listrules_empty(self):
        actions = handle_command(self._admin_event('listrules'))
        assert any('no rules' in a.get('content', '').lower() for a in actions)

    def test_listrules_with_data(self):
        InviteRule.objects.create(guild=self.gs, invite_code='c1', description='R1')
        actions = handle_command(self._admin_event('listrules'))
        assert any(a['type'] == 'send_embed' for a in actions)

    # ── setmode ──────────────────────────────────────────────────────────

    def test_setmode_approval(self):
        actions = handle_command(self._admin_event('setmode', ['APPROVAL']))
        self.gs.refresh_from_db()
        assert self.gs.mode == 'APPROVAL'
        assert any(a['type'] == 'ensure_resources' for a in actions)

    def test_setmode_auto(self):
        self.gs.mode = 'APPROVAL'
        self.gs.save()
        actions = handle_command(self._admin_event('setmode', ['AUTO']))
        self.gs.refresh_from_db()
        assert self.gs.mode == 'AUTO'

    def test_setmode_invalid(self):
        actions = handle_command(self._admin_event('setmode', ['BANANA']))
        assert any('must be' in a.get('content', '').lower() or 'error' in a.get('content', '').lower() for a in actions)

    # ── listcommands / listfields ────────────────────────────────────────

    def test_listcommands(self):
        actions = handle_command(self._admin_event('help'))
        assert any(a['type'] == 'reply' for a in actions)

    def test_listfields_empty(self):
        actions = handle_command(self._admin_event('listfields'))
        assert any('no form fields' in a.get('content', '').lower() for a in actions)

    # ── permission gate ──────────────────────────────────────────────────

    def test_non_admin_blocked(self):
        event = self._admin_event('addrule', ['code', 'Role'])
        event['author']['role_ids'] = []
        actions = handle_command(event)
        assert any('botadmin' in a.get('content', '').lower() for a in actions)

    def test_unknown_command(self):
        event = self._admin_event('nonexistent')
        actions = handle_command(event)
        assert any('not found' in a.get('content', '').lower() for a in actions)

    # ── member_join ──────────────────────────────────────────────────────

    def test_member_join_auto_with_rule(self):
        role = DiscordRole.objects.create(guild=self.gs, discord_id=333, name='Verified')
        rule = InviteRule.objects.create(guild=self.gs, invite_code='inv1')
        rule.roles.add(role)

        actions = handle_member_join({
            'guild_id': self.gs.guild_id,
            'member': {'id': 400, 'name': 'NewUser'},
            'invite': {'code': 'inv1', 'inviter_id': 500, 'inviter_name': 'Inviter'},
        })
        assert any(a['type'] == 'add_role' and a['role_id'] == 333 for a in actions)

    def test_member_join_auto_default_rule(self):
        role = DiscordRole.objects.create(guild=self.gs, discord_id=444, name='Default')
        rule = InviteRule.objects.create(guild=self.gs, invite_code='default')
        rule.roles.add(role)

        actions = handle_member_join({
            'guild_id': self.gs.guild_id,
            'member': {'id': 401, 'name': 'NewUser2'},
            'invite': {'code': 'unknowncode', 'inviter_id': None, 'inviter_name': 'Unknown'},
        })
        assert any(a['type'] == 'add_role' and a['role_id'] == 444 for a in actions)

    def test_member_join_approval_creates_application(self):
        self.gs.mode = 'APPROVAL'
        self.gs.save()

        actions = handle_member_join({
            'guild_id': self.gs.guild_id,
            'member': {'id': 402, 'name': 'Applicant'},
            'invite': {'code': 'inv2', 'inviter_id': 600, 'inviter_name': 'Ref'},
        })
        assert any(a['type'] == 'add_role' and a['role_id'] == self.gs.pending_role_id for a in actions)
        assert Application.objects.filter(guild=self.gs, user_id=402, status='PENDING').exists()

    # ── member_remove ────────────────────────────────────────────────────

    def test_member_remove_cancels_pending(self):
        Application.objects.create(guild=self.gs, user_id=700, user_name='Leaver', status='PENDING', responses={})
        handle_member_remove({'guild_id': self.gs.guild_id, 'user_id': 700})
        assert Application.objects.get(user_id=700).status == 'REJECTED'

    # ── approve / reject ─────────────────────────────────────────────────

    def test_approve_deletes_application(self):
        app = Application.objects.create(guild=self.gs, user_id=800, user_name='User', status='PENDING', responses={})
        event = self._admin_event('approve', [f'<@800>'], user_mentions=[{'id': 800, 'name': 'User'}])
        actions = handle_command(event)
        assert not Application.objects.filter(id=app.id).exists()
        assert any(a['type'] == 'send_dm' for a in actions)

    def test_reject_updates_application(self):
        app = Application.objects.create(guild=self.gs, user_id=801, user_name='User2', status='PENDING', responses={})
        event = self._admin_event('reject', [f'<@801>', 'bad', 'behavior'], user_mentions=[{'id': 801, 'name': 'User2'}])
        actions = handle_command(event)
        app.refresh_from_db()
        assert app.status == 'REJECTED'
        assert any(a['type'] == 'send_dm' for a in actions)

    # ── reload ───────────────────────────────────────────────────────────

    def test_reload_syncs_data(self):
        event = self._admin_event('reload',
                                  guild_roles=[{'id': 10, 'name': 'R1'}],
                                  guild_channels=[{'id': 20, 'name': 'C1'}],
                                  guild_members=[])
        actions = handle_command(event)
        assert DiscordRole.objects.filter(guild=self.gs, discord_id=10).exists()
        assert DiscordChannel.objects.filter(guild=self.gs, discord_id=20).exists()
        assert any(a['type'] == 'ensure_resources' for a in actions)

    def test_reload_creates_missing_applications(self):
        self.gs.mode = 'APPROVAL'
        self.gs.save()
        event = self._admin_event('reload',
                                  guild_roles=[], guild_channels=[],
                                  guild_members=[{'id': 900, 'name': 'User', 'bot': False}])
        actions = handle_command(event)
        assert Application.objects.filter(guild=self.gs, user_id=900, status='PENDING').exists()
