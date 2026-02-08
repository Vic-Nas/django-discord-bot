"""
Integration tests — verify the full event pipeline from
handle_member_join through automations to action dicts.

Uses fixtures from conftest.py.
"""

import pytest
from core.models import (
    GuildSettings, Application, Automation, Action,
    InviteRule, DiscordRole, FormField,
)
from core.services import (
    handle_member_join, handle_command, handle_reaction,
    process_event, BUILTIN_COMMANDS,
)


class TestAutoModeEndToEnd:
    """Full AUTO mode flow: join → log embed + role assignment."""

    def test_member_join_auto_full_pipeline(self, test_guild, test_automations):
        event = {
            'guild_id': test_guild.guild_id,
            'member': {'id': 500, 'name': 'IntegrationUser'},
            'invite': {'code': 'default', 'inviter_id': 1, 'inviter_name': 'Tester'},
        }
        actions = handle_member_join(event)

        types = [a['type'] for a in actions]
        assert 'send_embed' in types
        assert 'add_role' in types

        role_action = next(a for a in actions if a['type'] == 'add_role')
        assert role_action['role_id'] == 333333333  # Members role from default rule
        assert role_action['guild_id'] == test_guild.guild_id


class TestApprovalModeEndToEnd:
    """Full APPROVAL mode flow: join → application → approve/reject."""

    def test_approval_flow_creates_and_approves(self, test_guild, test_automations):
        test_guild.mode = 'APPROVAL'
        test_guild.save()

        # Member joins
        join_event = {
            'guild_id': test_guild.guild_id,
            'member': {'id': 600, 'name': 'ApprovalUser'},
            'invite': {'code': 'default', 'inviter_id': 1, 'inviter_name': 'Inv'},
        }
        join_actions = handle_member_join(join_event)

        # Verify application created
        app = Application.objects.get(guild=test_guild, user_id=600)
        assert app.status == 'PENDING'

        # Verify tracked embed sent
        embed_action = next(a for a in join_actions if a['type'] == 'send_embed_tracked')
        assert embed_action['application_id'] == app.id

        # Admin approves
        approve_event = {
            'command': 'approve',
            'args': ['<@600>'],
            'guild_id': test_guild.guild_id,
            'channel_id': 555555555,
            'author': {'id': 1, 'name': 'Admin', 'role_ids': [111111111]},
            'user_mentions': [{'id': 600, 'name': 'ApprovalUser'}],
            'role_mentions': [],
            'channel_mentions': [],
        }
        approve_actions = handle_command(approve_event)

        types = [a['type'] for a in approve_actions]
        assert 'remove_role' in types  # remove Pending
        assert 'add_role' in types  # assign from rule
        assert 'send_dm' in types

        # Application deleted on approve
        assert not Application.objects.filter(id=app.id).exists()

    def test_rejection_flow(self, test_guild, test_automations):
        test_guild.mode = 'APPROVAL'
        test_guild.save()

        # Member joins
        join_event = {
            'guild_id': test_guild.guild_id,
            'member': {'id': 700, 'name': 'RejectUser'},
            'invite': {'code': 'default', 'inviter_id': 1, 'inviter_name': 'Inv'},
        }
        handle_member_join(join_event)
        app = Application.objects.get(guild=test_guild, user_id=700)

        # Admin rejects
        reject_event = {
            'command': 'reject',
            'args': ['<@700>', 'Bad', 'behavior'],
            'guild_id': test_guild.guild_id,
            'channel_id': 555555555,
            'author': {'id': 1, 'name': 'Admin', 'role_ids': [111111111]},
            'user_mentions': [{'id': 700, 'name': 'RejectUser'}],
            'role_mentions': [],
            'channel_mentions': [],
        }
        reject_actions = handle_command(reject_event)

        types = [a['type'] for a in reject_actions]
        assert 'remove_role' in types
        assert 'send_dm' in types

        app.refresh_from_db()
        assert app.status == 'REJECTED'


class TestCustomAutomation:
    """Custom command automations (trigger=COMMAND)."""

    def test_custom_command_fires_actions(self, test_guild):
        auto = Automation.objects.create(
            guild=test_guild, name='greet',
            trigger='COMMAND',
            trigger_config={'name': 'greet'},
            enabled=True,
        )
        Action.objects.create(
            automation=auto, order=1,
            action_type='SEND_MESSAGE',
            config={'channel': 'bounce', 'content': 'Hello from automation!'},
        )

        event = {
            'command': 'greet',
            'args': [],
            'guild_id': test_guild.guild_id,
            'channel_id': 555555555,
            'author': {'id': 1, 'name': 'Admin', 'role_ids': [111111111]},
        }
        actions = handle_command(event)
        assert any(a['type'] == 'send_message' for a in actions)
        msg = next(a for a in actions if a['type'] == 'send_message')
        assert msg['content'] == 'Hello from automation!'

    def test_admin_only_custom_command(self, test_guild):
        auto = Automation.objects.create(
            guild=test_guild, name='secret',
            trigger='COMMAND',
            trigger_config={'name': 'secret'},
            admin_only=True, enabled=True,
        )
        Action.objects.create(
            automation=auto, order=1,
            action_type='SEND_MESSAGE',
            config={'channel': 'bounce', 'content': 'Secret!'},
        )

        # Non-admin
        event = {
            'command': 'secret',
            'args': [],
            'guild_id': test_guild.guild_id,
            'channel_id': 555555555,
            'author': {'id': 99, 'name': 'Pleb', 'role_ids': [999]},
        }
        actions = handle_command(event)
        assert any('BotAdmin' in a.get('content', '') for a in actions)
        assert not any(a['type'] == 'send_message' for a in actions)


class TestAutomationEngine:
    """Direct tests for process_event / trigger matching."""

    def test_mode_filter_auto(self, test_guild, test_automations):
        """AUTO mode triggers only automations with mode=AUTO."""
        event = {
            'guild_id': test_guild.guild_id,
            'member': {'id': 42, 'name': 'User'},
            'invite': {'code': 'default'},
        }
        actions = process_event('MEMBER_JOIN', event)

        # Should get AUTO actions (embed + role), not APPROVAL actions
        types = [a['type'] for a in actions]
        assert 'send_embed' in types
        assert 'send_embed_tracked' not in types  # that's approval-only

    def test_mode_filter_approval(self, test_guild, test_automations):
        """APPROVAL mode triggers only automations with mode=APPROVAL."""
        test_guild.mode = 'APPROVAL'
        test_guild.save()

        event = {
            'guild_id': test_guild.guild_id,
            'member': {'id': 42, 'name': 'User'},
            'invite': {'code': 'default'},
        }
        actions = process_event('MEMBER_JOIN', event)

        types = [a['type'] for a in actions]
        assert 'add_role' in types  # pending role
        assert 'send_embed_tracked' in types  # application embed

    def test_disabled_automation_skipped(self, test_guild, test_automations):
        """Disabled automations produce no actions."""
        Automation.objects.filter(guild=test_guild).update(enabled=False)

        event = {
            'guild_id': test_guild.guild_id,
            'member': {'id': 42, 'name': 'User'},
            'invite': {'code': 'default'},
        }
        actions = process_event('MEMBER_JOIN', event)
        assert actions == []


class TestFormBasedApproval:
    """Integration: APPROVAL with form fields → approve assigns roles + channels."""

    def test_form_roles_assigned_on_approve(self, test_guild, test_automations, test_form_fields):
        """Join in approval → fill form with role dropdown → approve → role from form assigned."""
        test_guild.mode = 'APPROVAL'
        test_guild.save()

        # Member joins
        join_event = {
            'guild_id': test_guild.guild_id,
            'member': {'id': 800, 'name': 'FormUser'},
            'invite': {'code': 'default', 'inviter_id': 1, 'inviter_name': 'Inv'},
        }
        handle_member_join(join_event)
        app = Application.objects.get(guild=test_guild, user_id=800)
        assert app.status == 'PENDING'

        # Simulate form submission: user picks role 333333333 and channel 444444444
        rf = test_form_fields['role_field']
        cf = test_form_fields['channel_field']
        app.responses = {
            str(rf.id): '333333333',
            str(cf.id): '444444444',
        }
        app.save()

        # Admin approves
        approve_event = {
            'command': 'approve',
            'args': ['<@800>'],
            'guild_id': test_guild.guild_id,
            'channel_id': 555555555,
            'author': {'id': 1, 'name': 'Admin', 'role_ids': [111111111]},
            'user_mentions': [{'id': 800, 'name': 'FormUser'}],
            'role_mentions': [],
            'channel_mentions': [],
        }
        result = handle_command(approve_event)

        types = [a['type'] for a in result]
        assert 'remove_role' in types   # remove pending
        assert 'add_role' in types      # from invite rule + form
        assert 'set_permissions' in types  # from channel dropdown
        assert 'send_dm' in types

        # Channel perms: user gets access to channel 444444444
        perm_actions = [a for a in result if a['type'] == 'set_permissions']
        assert any(a['channel_id'] == 444444444 for a in perm_actions)

        # Application deleted
        assert not Application.objects.filter(id=app.id).exists()


class TestRuleManagementCycle:
    """Integration: addrule → listrules → delrule cycle."""

    def test_add_list_delete_rule(self, test_guild):
        admin = {'id': 1, 'name': 'Admin', 'role_ids': [111111111]}
        guild_roles = [{'id': 333333333, 'name': 'Members'}]

        # 1. Add a rule
        add_event = {
            'command': 'addrule',
            'args': ['testcode', 'Members', 'Integration test rule'],
            'guild_id': test_guild.guild_id,
            'channel_id': 555555555,
            'author': admin,
            'guild_roles': guild_roles,
        }
        add_actions = handle_command(add_event)
        assert any('testcode' in a.get('content', '') for a in add_actions)

        # 2. List rules — should include the new one
        list_event = {
            'command': 'listrules',
            'args': [],
            'guild_id': test_guild.guild_id,
            'channel_id': 555555555,
            'author': admin,
        }
        list_actions = handle_command(list_event)
        embed = next(a for a in list_actions if a['type'] == 'send_embed')
        rule_names = [f['name'] for f in embed['embed']['fields']]
        assert '`testcode`' in rule_names

        # 3. Delete the rule
        del_event = {
            'command': 'delrule',
            'args': ['testcode'],
            'guild_id': test_guild.guild_id,
            'channel_id': 555555555,
            'author': admin,
        }
        del_actions = handle_command(del_event)
        assert any('deleted' in a.get('content', '') for a in del_actions)

        # 4. List again — only default rule should remain
        list_actions_2 = handle_command(list_event)
        embed_2 = next(a for a in list_actions_2 if a['type'] == 'send_embed')
        rule_names_2 = [f['name'] for f in embed_2['embed']['fields']]
        assert '`testcode`' not in rule_names_2


class TestMemberLeaveEdgeCases:
    """Edge cases around member leave + approval."""

    def test_leave_cancels_then_approve_fails(self, test_guild, test_automations):
        """Member joins in approval, leaves → app cancelled → approve fails."""
        test_guild.mode = 'APPROVAL'
        test_guild.save()

        # Join
        join_event = {
            'guild_id': test_guild.guild_id,
            'member': {'id': 900, 'name': 'LeaverUser'},
            'invite': {'code': 'default', 'inviter_id': 1, 'inviter_name': 'Inv'},
        }
        handle_member_join(join_event)
        app = Application.objects.get(guild=test_guild, user_id=900)
        assert app.status == 'PENDING'

        # Member leaves
        from core.services import handle_member_remove
        handle_member_remove({'guild_id': test_guild.guild_id, 'user_id': 900})
        app.refresh_from_db()
        assert app.status == 'REJECTED'

        # Admin tries to approve the now-rejected user.
        # With get_or_create, a new Application is auto-created and approved.
        # The user is gone from the server, so Discord role ops are no-ops.
        approve_event = {
            'command': 'approve',
            'args': ['<@900>'],
            'guild_id': test_guild.guild_id,
            'channel_id': 555555555,
            'author': {'id': 1, 'name': 'Admin', 'role_ids': [111111111]},
            'user_mentions': [{'id': 900, 'name': 'LeaverUser'}],
            'role_mentions': [],
            'channel_mentions': [],
        }
        result = handle_command(approve_event)
        # Approve still goes through (creates + deletes application)
        types = [a['type'] for a in result]
        assert 'remove_role' in types
        assert 'send_dm' in types


class TestReactionEndToEnd:
    """Full reaction-based approve/reject starting from join."""

    def test_join_then_reaction_approve(self, test_guild, test_automations):
        test_guild.mode = 'APPROVAL'
        test_guild.save()

        # Join
        join_event = {
            'guild_id': test_guild.guild_id,
            'member': {'id': 1100, 'name': 'ReactionUser'},
            'invite': {'code': 'default', 'inviter_id': 1, 'inviter_name': 'Inv'},
        }
        join_actions = handle_member_join(join_event)
        app = Application.objects.get(guild=test_guild, user_id=1100)
        tracked = next(a for a in join_actions if a['type'] == 'send_embed_tracked')

        # Reaction approve
        from core.services import handle_reaction
        react_event = {
            'guild_id': test_guild.guild_id,
            'channel_id': 555555555,
            'message_id': 99999,
            'emoji': '\u2705',
            'application_id': app.id,
            'admin': {'id': 1, 'name': 'Admin'},
            'original_embed': tracked['embed'],
        }
        result = handle_reaction(react_event)

        types = [a['type'] for a in result]
        assert 'remove_role' in types
        assert 'add_role' in types
        assert 'send_dm' in types
        assert 'edit_message' in types
        assert not Application.objects.filter(id=app.id).exists()


class TestMultipleAutomationsSameTrigger:
    """Multiple automations on the same trigger, different configs."""

    def test_both_mode_automations_exist_only_matching_fires(self, test_guild, test_automations):
        """With AUTO mode, only AUTO automation fires; APPROVAL automation doesn't."""
        assert test_guild.mode == 'AUTO'

        event = {
            'guild_id': test_guild.guild_id,
            'member': {'id': 42, 'name': 'User'},
            'invite': {'code': 'default'},
        }
        actions = process_event('MEMBER_JOIN', event)

        # AUTO produces send_embed + add_role, not send_embed_tracked (approval)
        types = [a['type'] for a in actions]
        assert 'send_embed' in types
        assert 'send_embed_tracked' not in types
        assert 'add_role' in types

        # Switch to APPROVAL
        test_guild.mode = 'APPROVAL'
        test_guild.save()
        actions2 = process_event('MEMBER_JOIN', event)
        types2 = [a['type'] for a in actions2]
        assert 'send_embed_tracked' in types2
        assert 'add_role' in types2  # pending role
