"""
Shared test fixtures for django-discord-bot.

Provides:
  - test_guild:  A GuildSettings instance with bounce/pending channel IDs
  - test_automations:  Default Automation + Action rows for the test guild
"""

import pytest
from core.models import (
    GuildSettings, DiscordRole, InviteRule,
    Application, Automation, Action,
)
from bot.handlers.templates import init_default_templates


@pytest.fixture
def test_guild(db):
    """Create a GuildSettings with roles and channels configured."""
    gs = GuildSettings.objects.create(
        guild_id=123456789,
        guild_name='Test Server',
        bot_admin_role_id=111111111,
        pending_role_id=222222222,
        bounce_channel_id=555555555,
        pending_channel_id=777777777,
        mode='AUTO',
    )

    # Cache some roles
    DiscordRole.objects.create(discord_id=111111111, guild=gs, name='BotAdmin')
    DiscordRole.objects.create(discord_id=222222222, guild=gs, name='Pending')
    DiscordRole.objects.create(discord_id=333333333, guild=gs, name='Members')

    # Default invite rule
    rule = InviteRule.objects.create(guild=gs, invite_code='default', description='Default rule')
    members_role = DiscordRole.objects.get(discord_id=333333333, guild=gs)
    rule.roles.add(members_role)

    # Seed templates
    init_default_templates()

    return gs


@pytest.fixture
def test_automations(test_guild):
    """Create default automations that mirror guild_setup defaults."""
    gs = test_guild

    # AUTO mode: log + assign roles
    auto_log = Automation.objects.create(
        guild=gs, name='Log Join (Auto)', trigger='MEMBER_JOIN',
        trigger_config={'mode': 'AUTO'}, enabled=True,
    )
    Action.objects.create(
        automation=auto_log, order=1, action_type='SEND_EMBED',
        config={'channel': 'bounce', 'template': 'JOIN_LOG_AUTO', 'color': 0x2ecc71},
    )
    Action.objects.create(
        automation=auto_log, order=2, action_type='ADD_ROLE',
        config={'from_rule': True},
    )

    # APPROVAL mode: pending role + application embed + DM
    auto_approval = Automation.objects.create(
        guild=gs, name='Approval Join', trigger='MEMBER_JOIN',
        trigger_config={'mode': 'APPROVAL'}, enabled=True,
    )
    Action.objects.create(
        automation=auto_approval, order=1, action_type='ADD_ROLE',
        config={'role': 'pending'},
    )
    Action.objects.create(
        automation=auto_approval, order=2, action_type='SEND_EMBED',
        config={'channel': 'bounce', 'template': 'application', 'track': True},
    )
    Action.objects.create(
        automation=auto_approval, order=3, action_type='SEND_DM',
        config={'template': 'WELCOME_DM_APPROVAL'},
    )

    return {'auto_log': auto_log, 'auto_approval': auto_approval}


@pytest.fixture
def test_application(test_guild):
    """Create a pending application."""
    return Application.objects.create(
        guild=test_guild,
        user_id=999888777,
        user_name='TestUser#1234',
        invite_code='abc123',
        inviter_name='Inviter',
        status='PENDING',
        responses={},
    )


@pytest.fixture
def test_form_fields(test_guild):
    """Create form fields with a ROLES dropdown for form-based approval tests."""
    from core.models import Dropdown, FormField, DiscordChannel

    # Roles dropdown (Members role already created in test_guild)
    members_role = DiscordRole.objects.get(discord_id=333333333, guild=test_guild)
    dd_roles = Dropdown.objects.create(
        guild=test_guild, name='Role picker', source_type='ROLES', multiselect=False,
    )
    dd_roles.roles.add(members_role)

    # Channels dropdown
    ch = DiscordChannel.objects.create(discord_id=444444444, guild=test_guild, name='general')
    dd_channels = Dropdown.objects.create(
        guild=test_guild, name='Channel picker', source_type='CHANNELS', multiselect=True,
    )
    dd_channels.channels.add(ch)

    f_name = FormField.objects.create(
        guild=test_guild, label='Name', field_type='text', order=1,
    )
    f_role = FormField.objects.create(
        guild=test_guild, label='Pick Role', field_type='dropdown',
        dropdown=dd_roles, order=2,
    )
    f_channel = FormField.objects.create(
        guild=test_guild, label='Pick Channel', field_type='dropdown',
        dropdown=dd_channels, order=3,
    )

    return {
        'name_field': f_name,
        'role_field': f_role,
        'channel_field': f_channel,
        'roles_dropdown': dd_roles,
        'channels_dropdown': dd_channels,
        'channel': ch,
    }
