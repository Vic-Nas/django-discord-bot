"""
Unit tests for core.services — event handlers and command routing.

Uses the test_guild + test_automations fixtures from conftest.py.
All business logic tested through the public API (handle_* functions).
"""

import pytest
from core.models import Application, Automation
from core.services import (
    handle_member_join, handle_member_remove, handle_command, handle_reaction,
    process_event, BUILTIN_COMMANDS,
)


class TestMemberJoinAuto:
    """Tests for AUTO mode member joins."""

    def test_auto_join_returns_embed_and_role(self, test_guild, test_automations):
        event = {
            'guild_id': test_guild.guild_id,
            'member': {'id': 42, 'name': 'NewUser'},
            'invite': {'code': 'default', 'inviter_id': 1, 'inviter_name': 'Someone'},
        }
        actions = handle_member_join(event)

        types = [a['type'] for a in actions]
        assert 'send_embed' in types
        assert 'add_role' in types

    def test_auto_join_no_matching_rule(self, test_guild, test_automations):
        event = {
            'guild_id': test_guild.guild_id,
            'member': {'id': 42, 'name': 'NewUser'},
            'invite': {'code': 'unknown_code', 'inviter_id': 1, 'inviter_name': 'Someone'},
        }
        actions = handle_member_join(event)
        # Falls back to 'default' rule
        role_actions = [a for a in actions if a['type'] == 'add_role']
        assert len(role_actions) >= 1

    @pytest.mark.django_db
    def test_no_guild_returns_empty(self):
        event = {
            'guild_id': 999999,
            'member': {'id': 42, 'name': 'Ghost'},
            'invite': {},
        }
        assert handle_member_join(event) == []


class TestMemberJoinApproval:
    """Tests for APPROVAL mode member joins."""

    def test_approval_creates_application(self, test_guild, test_automations):
        test_guild.mode = 'APPROVAL'
        test_guild.save()

        event = {
            'guild_id': test_guild.guild_id,
            'member': {'id': 42, 'name': 'PendingUser'},
            'invite': {'code': 'abc', 'inviter_id': 1, 'inviter_name': 'Inv'},
        }
        actions = handle_member_join(event)

        types = [a['type'] for a in actions]
        assert 'add_role' in types  # pending role
        assert 'send_embed_tracked' in types  # application embed
        assert Application.objects.filter(guild=test_guild, user_id=42).exists()


class TestMemberRemove:
    def test_cancels_pending_applications(self, test_guild, test_application):
        event = {'guild_id': test_guild.guild_id, 'user_id': test_application.user_id}
        handle_member_remove(event)

        test_application.refresh_from_db()
        assert test_application.status == 'REJECTED'


class TestHandleCommand:
    """Tests for built-in command routing."""

    def test_all_builtins_registered(self):
        expected = {'help', 'addrule', 'delrule', 'listrules', 'setmode',
                    'listfields', 'reload', 'approve', 'reject',
                    'cleanup', 'cleanall', 'auto-translate'}
        assert expected == set(BUILTIN_COMMANDS.keys())

    def test_help_returns_reply(self, test_guild):
        event = {
            'command': 'help',
            'args': [],
            'guild_id': test_guild.guild_id,
            'channel_id': 555555555,
            'author': {'id': 1, 'name': 'Admin', 'role_ids': [111111111]},
        }
        actions = handle_command(event)
        assert any(a['type'] == 'reply' for a in actions)
        assert 'Bot Commands' in actions[0]['content']

    def test_setmode_changes_mode(self, test_guild):
        event = {
            'command': 'setmode',
            'args': ['APPROVAL'],
            'guild_id': test_guild.guild_id,
            'channel_id': 555555555,
            'author': {'id': 1, 'name': 'Admin', 'role_ids': [111111111]},
        }
        actions = handle_command(event)
        test_guild.refresh_from_db()
        assert test_guild.mode == 'APPROVAL'

    def test_non_admin_rejected(self, test_guild):
        event = {
            'command': 'setmode',
            'args': ['AUTO'],
            'guild_id': test_guild.guild_id,
            'channel_id': 555555555,
            'author': {'id': 99, 'name': 'Pleb', 'role_ids': [999]},
        }
        actions = handle_command(event)
        assert any('BotAdmin' in a.get('content', '') for a in actions)

    def test_unknown_command_shows_list(self, test_guild):
        event = {
            'command': 'nonexistent',
            'args': [],
            'guild_id': test_guild.guild_id,
            'channel_id': 555555555,
            'author': {'id': 1, 'name': 'Admin', 'role_ids': [111111111]},
        }
        actions = handle_command(event)
        assert any(a['type'] == 'reply' for a in actions)

    def test_listrules_returns_embed(self, test_guild):
        event = {
            'command': 'listrules',
            'args': [],
            'guild_id': test_guild.guild_id,
            'channel_id': 555555555,
            'author': {'id': 1, 'name': 'Admin', 'role_ids': [111111111]},
        }
        actions = handle_command(event)
        assert any(a['type'] == 'send_embed' for a in actions)

    def test_approve_no_application(self, test_guild):
        event = {
            'command': 'approve',
            'args': ['<@42>'],
            'guild_id': test_guild.guild_id,
            'channel_id': 555555555,
            'author': {'id': 1, 'name': 'Admin', 'role_ids': [111111111]},
            'user_mentions': [{'id': 42, 'name': 'Nobody'}],
            'role_mentions': [],
        }
        actions = handle_command(event)
        assert any('No pending application' in a.get('content', '') for a in actions)


class TestHandleReaction:
    def test_approve_via_reaction(self, test_guild, test_application):
        test_guild.mode = 'APPROVAL'
        test_guild.save()

        event = {
            'guild_id': test_guild.guild_id,
            'channel_id': 555555555,
            'message_id': 12345,
            'emoji': '\u2705',
            'application_id': test_application.id,
            'admin': {'id': 1, 'name': 'Admin'},
            'original_embed': {'title': 'App', 'fields': []},
        }
        actions = handle_reaction(event)

        types = [a['type'] for a in actions]
        assert 'remove_role' in types  # remove pending
        assert 'send_dm' in types  # DM user
        assert not Application.objects.filter(id=test_application.id).exists()  # deleted on approve

    def test_reject_via_reaction(self, test_guild, test_application):
        event = {
            'guild_id': test_guild.guild_id,
            'channel_id': 555555555,
            'message_id': 12345,
            'emoji': '\u274c',
            'application_id': test_application.id,
            'admin': {'id': 1, 'name': 'Admin'},
            'original_embed': {'title': 'App', 'fields': []},
        }
        actions = handle_reaction(event)
        test_application.refresh_from_db()
        assert test_application.status == 'REJECTED'

    def test_invalid_emoji_ignored(self, test_guild, test_application):
        event = {
            'guild_id': test_guild.guild_id,
            'emoji': '\U0001f44d',
            'application_id': test_application.id,
            'admin': {'id': 1, 'name': 'Admin'},
        }
        assert handle_reaction(event) == []


class TestAddruleDelrule:
    """Tests for addrule / delrule built-in commands."""

    def test_addrule_creates_rule(self, test_guild):
        event = {
            'command': 'addrule',
            'args': ['mycode', 'Members', 'Test rule'],
            'guild_id': test_guild.guild_id,
            'channel_id': 555555555,
            'author': {'id': 1, 'name': 'Admin', 'role_ids': [111111111]},
            'guild_roles': [{'id': 333333333, 'name': 'Members'}],
        }
        actions = handle_command(event)
        assert any('mycode' in a.get('content', '') for a in actions)

        from core.models import InviteRule
        rule = InviteRule.objects.get(guild=test_guild, invite_code='mycode')
        assert rule.roles.count() == 1
        assert rule.roles.first().discord_id == 333333333

    def test_addrule_requires_admin(self, test_guild):
        event = {
            'command': 'addrule',
            'args': ['mycode', 'Members'],
            'guild_id': test_guild.guild_id,
            'channel_id': 555555555,
            'author': {'id': 99, 'name': 'Pleb', 'role_ids': [999]},
        }
        actions = handle_command(event)
        assert any('BotAdmin' in a.get('content', '') for a in actions)

    def test_addrule_missing_args(self, test_guild):
        event = {
            'command': 'addrule',
            'args': ['mycode'],
            'guild_id': test_guild.guild_id,
            'channel_id': 555555555,
            'author': {'id': 1, 'name': 'Admin', 'role_ids': [111111111]},
        }
        actions = handle_command(event)
        assert any('Usage' in a.get('content', '') for a in actions)

    def test_delrule_removes_rule(self, test_guild):
        from core.models import InviteRule
        rule = InviteRule.objects.create(guild=test_guild, invite_code='temp')
        event = {
            'command': 'delrule',
            'args': ['temp'],
            'guild_id': test_guild.guild_id,
            'channel_id': 555555555,
            'author': {'id': 1, 'name': 'Admin', 'role_ids': [111111111]},
        }
        actions = handle_command(event)
        assert any('deleted' in a.get('content', '') for a in actions)
        assert not InviteRule.objects.filter(guild=test_guild, invite_code='temp').exists()

    def test_delrule_not_found(self, test_guild):
        event = {
            'command': 'delrule',
            'args': ['noexist'],
            'guild_id': test_guild.guild_id,
            'channel_id': 555555555,
            'author': {'id': 1, 'name': 'Admin', 'role_ids': [111111111]},
        }
        actions = handle_command(event)
        assert any('not found' in a.get('content', '').lower() for a in actions)


class TestRejectCommand:
    """Tests for the reject built-in command."""

    def test_reject_marks_rejected(self, test_guild, test_application):
        event = {
            'command': 'reject',
            'args': ['<@999888777>', 'Spam', 'account'],
            'guild_id': test_guild.guild_id,
            'channel_id': 555555555,
            'author': {'id': 1, 'name': 'Admin', 'role_ids': [111111111]},
            'user_mentions': [{'id': 999888777, 'name': 'TestUser#1234'}],
            'role_mentions': [],
        }
        actions = handle_command(event)
        test_application.refresh_from_db()
        assert test_application.status == 'REJECTED'
        assert any(a['type'] == 'send_dm' for a in actions)

    def test_reject_no_pending(self, test_guild):
        event = {
            'command': 'reject',
            'args': ['<@42>'],
            'guild_id': test_guild.guild_id,
            'channel_id': 555555555,
            'author': {'id': 1, 'name': 'Admin', 'role_ids': [111111111]},
            'user_mentions': [{'id': 42, 'name': 'Nobody'}],
            'role_mentions': [],
        }
        actions = handle_command(event)
        assert any('No pending application' in a.get('content', '') for a in actions)


class TestListfieldsCommand:
    def test_listfields_empty(self, test_guild):
        event = {
            'command': 'listfields',
            'args': [],
            'guild_id': test_guild.guild_id,
            'channel_id': 555555555,
            'author': {'id': 1, 'name': 'Admin', 'role_ids': [111111111]},
        }
        actions = handle_command(event)
        assert any('No form fields' in a.get('content', '') for a in actions)

    def test_listfields_with_fields(self, test_guild, test_form_fields):
        event = {
            'command': 'listfields',
            'args': [],
            'guild_id': test_guild.guild_id,
            'channel_id': 555555555,
            'author': {'id': 1, 'name': 'Admin', 'role_ids': [111111111]},
        }
        actions = handle_command(event)
        embed_action = next(a for a in actions if a['type'] == 'send_embed')
        field_names = [f['name'] for f in embed_action['embed']['fields']]
        assert 'Name' in field_names
        assert 'Pick Role' in field_names


class TestReloadCommand:
    def test_reload_syncs_roles_and_channels(self, test_guild):
        from core.models import DiscordChannel
        event = {
            'command': 'reload',
            'args': [],
            'guild_id': test_guild.guild_id,
            'channel_id': 555555555,
            'author': {'id': 1, 'name': 'Admin', 'role_ids': [111111111]},
            'guild_roles': [
                {'id': 111111111, 'name': 'BotAdmin'},
                {'id': 333333333, 'name': 'Members'},
                {'id': 444444444, 'name': 'NewRole'},
            ],
            'guild_channels': [
                {'id': 555555555, 'name': 'general'},
            ],
            'guild_members': [],
        }
        actions = handle_command(event)
        assert any('Reloaded' in a.get('content', '') for a in actions)
        from core.models import DiscordRole
        assert DiscordRole.objects.filter(guild=test_guild, discord_id=444444444).exists()
        assert DiscordChannel.objects.filter(guild=test_guild, discord_id=555555555).exists()


class TestProcessAction:
    """Test individual action types via the automation engine."""

    def test_send_message_action(self, test_guild):
        auto = Automation.objects.create(
            guild=test_guild, name='test_msg', trigger='MEMBER_JOIN',
            trigger_config={}, enabled=True,
        )
        from core.models import Action
        Action.objects.create(
            automation=auto, order=1, action_type='SEND_MESSAGE',
            config={'channel': 'bounce', 'content': 'Welcome!'},
        )
        event = {
            'guild_id': test_guild.guild_id,
            'member': {'id': 42, 'name': 'User'},
            'invite': {'code': 'default'},
        }
        actions = process_event('MEMBER_JOIN', event)
        msg = next((a for a in actions if a['type'] == 'send_message'), None)
        assert msg is not None
        assert msg['content'] == 'Welcome!'
        assert msg['channel_id'] == test_guild.bounce_channel_id

    def test_cleanup_action(self, test_guild):
        auto = Automation.objects.create(
            guild=test_guild, name='test_cleanup', trigger='MEMBER_JOIN',
            trigger_config={}, enabled=True,
        )
        from core.models import Action
        Action.objects.create(
            automation=auto, order=1, action_type='CLEANUP',
            config={'channel': 'bounce', 'count': 5},
        )
        event = {
            'guild_id': test_guild.guild_id,
            'member': {'id': 42, 'name': 'User'},
            'invite': {'code': 'default'},
        }
        actions = process_event('MEMBER_JOIN', event)
        cleanup = next((a for a in actions if a['type'] == 'cleanup_channel'), None)
        assert cleanup is not None
        assert cleanup['count'] == 5

    def test_remove_role_action(self, test_guild):
        auto = Automation.objects.create(
            guild=test_guild, name='test_rr', trigger='MEMBER_JOIN',
            trigger_config={}, enabled=True,
        )
        from core.models import Action
        Action.objects.create(
            automation=auto, order=1, action_type='REMOVE_ROLE',
            config={'role': 'pending'},
        )
        event = {
            'guild_id': test_guild.guild_id,
            'member': {'id': 42, 'name': 'User'},
            'invite': {'code': 'default'},
        }
        actions = process_event('MEMBER_JOIN', event)
        rr = next((a for a in actions if a['type'] == 'remove_role'), None)
        assert rr is not None
        assert rr['role_id'] == test_guild.pending_role_id

    def test_set_topic_action(self, test_guild):
        auto = Automation.objects.create(
            guild=test_guild, name='test_topic', trigger='MEMBER_JOIN',
            trigger_config={}, enabled=True,
        )
        from core.models import Action
        Action.objects.create(
            automation=auto, order=1, action_type='SET_TOPIC',
            config={'channel': 'pending', 'content': 'New topic'},
        )
        event = {
            'guild_id': test_guild.guild_id,
            'member': {'id': 42, 'name': 'User'},
            'invite': {'code': 'default'},
        }
        actions = process_event('MEMBER_JOIN', event)
        topic = next((a for a in actions if a['type'] == 'set_topic'), None)
        assert topic is not None
        assert topic['topic'] == 'New topic'
        assert topic['channel_id'] == test_guild.pending_channel_id


class TestCleanupCommands:
    """Tests for cleanup / cleanall built-in commands."""

    def test_cleanup_cleans_calling_channel(self, test_guild):
        """cleanup should clean the channel where the command was called."""
        event = {
            'command': 'cleanup',
            'args': [],
            'guild_id': test_guild.guild_id,
            'channel_id': 555555555,
            'author': {'id': 1, 'name': 'Admin', 'role_ids': [111111111]},
        }
        actions = handle_command(event)
        cleanup = next((a for a in actions if a['type'] == 'cleanup_channel'), None)
        assert cleanup is not None
        assert cleanup['count'] == 50
        assert cleanup['channel_id'] == 555555555  # the calling channel

    def test_cleanup_different_channel_than_bounce(self, test_guild):
        """cleanup in a non-bounce channel should clean that channel, not bounce."""
        other_channel_id = 888888888
        event = {
            'command': 'cleanup',
            'args': [],
            'guild_id': test_guild.guild_id,
            'channel_id': other_channel_id,
            'author': {'id': 1, 'name': 'Admin', 'role_ids': [111111111]},
        }
        actions = handle_command(event)
        cleanup = next((a for a in actions if a['type'] == 'cleanup_channel'), None)
        assert cleanup is not None
        assert cleanup['channel_id'] == other_channel_id
        assert cleanup['channel_id'] != test_guild.bounce_channel_id

    def test_cleanall_cleans_calling_channel(self, test_guild):
        """cleanall should clean the channel where the command was called."""
        event = {
            'command': 'cleanall',
            'args': [],
            'guild_id': test_guild.guild_id,
            'channel_id': 555555555,
            'author': {'id': 1, 'name': 'Admin', 'role_ids': [111111111]},
        }
        actions = handle_command(event)
        cleanup = next((a for a in actions if a['type'] == 'cleanup_channel'), None)
        assert cleanup is not None
        assert cleanup['count'] == 999

    def test_cleanall_different_channel_than_bounce(self, test_guild):
        """cleanall in a non-bounce channel should clean that channel."""
        other_channel_id = 888888888
        event = {
            'command': 'cleanall',
            'args': [],
            'guild_id': test_guild.guild_id,
            'channel_id': other_channel_id,
            'author': {'id': 1, 'name': 'Admin', 'role_ids': [111111111]},
        }
        actions = handle_command(event)
        cleanup = next((a for a in actions if a['type'] == 'cleanup_channel'), None)
        assert cleanup is not None
        assert cleanup['channel_id'] == other_channel_id

    def test_cleanup_requires_admin(self, test_guild):
        event = {
            'command': 'cleanup',
            'args': [],
            'guild_id': test_guild.guild_id,
            'channel_id': 555555555,
            'author': {'id': 99, 'name': 'Pleb', 'role_ids': [999]},
        }
        actions = handle_command(event)
        assert any('BotAdmin' in a.get('content', '') for a in actions)

    def test_cleanall_requires_admin(self, test_guild):
        event = {
            'command': 'cleanall',
            'args': [],
            'guild_id': test_guild.guild_id,
            'channel_id': 555555555,
            'author': {'id': 99, 'name': 'Pleb', 'role_ids': [999]},
        }
        actions = handle_command(event)
        assert any('BotAdmin' in a.get('content', '') for a in actions)


class TestAutoTranslateCommand:
    """Tests for the auto-translate built-in command."""

    def test_auto_translate_on(self, test_guild):
        event = {
            'command': 'auto-translate',
            'args': ['on', 'fr'],
            'guild_id': test_guild.guild_id,
            'channel_id': 555555555,
            'author': {'id': 1, 'name': 'Admin', 'role_ids': [111111111]},
        }
        actions = handle_command(event)
        test_guild.refresh_from_db()
        assert test_guild.language == 'fr'
        assert any('fr' in a.get('content', '') for a in actions)

    def test_auto_translate_off(self, test_guild):
        test_guild.language = 'fr'
        test_guild.save()

        event = {
            'command': 'auto-translate',
            'args': ['off'],
            'guild_id': test_guild.guild_id,
            'channel_id': 555555555,
            'author': {'id': 1, 'name': 'Admin', 'role_ids': [111111111]},
        }
        actions = handle_command(event)
        test_guild.refresh_from_db()
        assert test_guild.language is None
        assert any('disabled' in a.get('content', '').lower() for a in actions)

    def test_auto_translate_requires_admin(self, test_guild):
        event = {
            'command': 'auto-translate',
            'args': ['on', 'fr'],
            'guild_id': test_guild.guild_id,
            'channel_id': 555555555,
            'author': {'id': 99, 'name': 'Pleb', 'role_ids': [999]},
        }
        actions = handle_command(event)
        assert any('BotAdmin' in a.get('content', '') for a in actions)

    def test_auto_translate_missing_args(self, test_guild):
        event = {
            'command': 'auto-translate',
            'args': [],
            'guild_id': test_guild.guild_id,
            'channel_id': 555555555,
            'author': {'id': 1, 'name': 'Admin', 'role_ids': [111111111]},
        }
        actions = handle_command(event)
        assert any('Usage' in a.get('content', '') for a in actions)

    def test_auto_translate_on_missing_lang(self, test_guild):
        event = {
            'command': 'auto-translate',
            'args': ['on'],
            'guild_id': test_guild.guild_id,
            'channel_id': 555555555,
            'author': {'id': 1, 'name': 'Admin', 'role_ids': [111111111]},
        }
        actions = handle_command(event)
        assert any('Usage' in a.get('content', '') for a in actions)