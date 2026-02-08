"""
Django service layer — ALL business logic lives here.

Two systems work together:
  1. **Automations** (data-driven):  Trigger → Actions, configured via admin.
     Handles: member join flows, custom commands, form events.
  2. **Built-in commands** (code): approve, reject, addrule, etc.
     Complex stateful logic that doesn't fit in JSON config.

The bot sends events as simple dicts.  This module returns action dicts
for the bot to execute on Discord.

Action dict types:
  send_message, send_embed, send_embed_tracked, send_dm,
  add_role, remove_role, edit_message, clear_reactions,
  set_permissions, set_topic, ensure_resources, cleanup_channel, reply
"""

import os
import secrets
from datetime import timedelta

from django.utils import timezone

from .models import (
    GuildSettings, DiscordRole, DiscordChannel, InviteRule,
    Application, FormField, AccessToken, Automation,
)
from bot.handlers.templates import get_template


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_guild(guild_id):
    try:
        return GuildSettings.objects.get(guild_id=guild_id)
    except GuildSettings.DoesNotExist:
        return None


def _resolve_channel(gs, ref):
    """Map a channel reference ('bounce', 'pending', or int) to a channel ID."""
    if not ref:
        return None
    if ref == 'bounce':
        return gs.bounce_channel_id
    if ref == 'pending':
        return gs.pending_channel_id
    if isinstance(ref, int):
        return ref
    return None


def _resolve_role_id(gs, config):
    """Map a role config to a Discord role ID."""
    if 'role_id' in config:
        return config['role_id']
    role_ref = config.get('role', '')
    if role_ref == 'pending':
        return gs.pending_role_id
    if isinstance(role_ref, int):
        return role_ref
    if role_ref:
        r = DiscordRole.objects.filter(guild=gs, name__iexact=role_ref).first()
        return r.discord_id if r else None
    return None


def _resolve_display_value(field, raw_value):
    """Resolve dropdown IDs to human-readable names."""
    if not raw_value or raw_value == 'No answer':
        return raw_value
    if field.field_type != 'dropdown' or not field.dropdown:
        return raw_value

    ids = [v.strip() for v in raw_value.split(',') if v.strip()]
    source = field.dropdown.source_type

    if source == 'ROLES':
        names = []
        for rid in ids:
            try:
                r = DiscordRole.objects.get(guild=field.guild, discord_id=int(rid))
                names.append(r.name)
            except (DiscordRole.DoesNotExist, ValueError):
                names.append(rid)
        return ', '.join(names)
    if source == 'CHANNELS':
        names = []
        for cid in ids:
            try:
                c = DiscordChannel.objects.get(guild=field.guild, discord_id=int(cid))
                names.append(f'#{c.name}' if c.name else cid)
            except (DiscordChannel.DoesNotExist, ValueError):
                names.append(cid)
        return ', '.join(names)
    if source == 'CUSTOM':
        option_map = {o.value: o.label for o in field.dropdown.custom_options.all()}
        return ', '.join(option_map.get(v, v) for v in ids)
    return raw_value


def _extract_form_selections(gs, application):
    """Extract role IDs and channel IDs from dropdown responses."""
    fields = FormField.objects.select_related('dropdown').filter(
        guild=gs, field_type='dropdown',
    )
    role_ids, channel_ids = [], []
    for field in fields:
        if not field.dropdown:
            continue
        raw = application.responses.get(str(field.id), '')
        if not raw:
            continue
        for val in raw.split(','):
            val = val.strip()
            try:
                int_val = int(val)
            except ValueError:
                continue
            if field.dropdown.source_type == 'ROLES':
                role_ids.append(int_val)
            elif field.dropdown.source_type == 'CHANNELS':
                channel_ids.append(int_val)
    return role_ids, channel_ids


# ── Generic Automation Engine ────────────────────────────────────────────────

def process_event(trigger_type, event):
    """Find matching automations and execute their actions."""
    guild_id = event.get('guild_id')
    gs = _get_guild(guild_id)
    if not gs:
        return []

    event['mode'] = gs.mode  # inject for trigger matching

    automations = Automation.objects.filter(
        guild=gs, trigger=trigger_type, enabled=True,
    ).prefetch_related('actions')

    results = []
    for auto in automations:
        if not _trigger_matches(auto.trigger_config, event):
            continue
        for action in auto.actions.filter(enabled=True).order_by('order'):
            results.extend(_process_action(action, gs, event))
    return results


def _trigger_matches(config, event):
    """Return True if every key in trigger_config matches the event."""
    if not config:
        return True
    for key, value in config.items():
        if key == 'mode' and event.get('mode') != value:
            return False
        if key == 'invite_code' and event.get('invite', {}).get('code') != value:
            return False
        if key == 'name' and event.get('command') != value:
            return False
        if key == 'emoji' and event.get('emoji') != value:
            return False
    return True


def _process_action(action, gs, event):
    """Convert an Action model instance into bot action dicts."""
    c = action.config or {}
    t = action.action_type
    member = event.get('member', {})
    user_id = member.get('id') or event.get('user_id')

    if t == 'SEND_MESSAGE':
        ch = _resolve_channel(gs, c.get('channel', 'bounce'))
        tpl_name = c.get('template')
        content = c.get('content', '')
        if tpl_name:
            content = _format_template(gs, tpl_name, event)
        return [{'type': 'send_message', 'channel_id': ch, 'content': content}] if ch and content else []

    if t == 'SEND_DM':
        tpl_name = c.get('template')
        content = c.get('content', '')
        if tpl_name:
            content = _format_template(gs, tpl_name, event)
        return [{'type': 'send_dm', 'user_id': user_id, 'content': content}] if user_id and content else []

    if t == 'SEND_EMBED':
        ch = _resolve_channel(gs, c.get('channel', 'bounce'))
        if not ch:
            return []
        tpl_name = c.get('template', '')
        track = c.get('track', False)

        # Special case: 'application' template builds the application embed
        if tpl_name == 'application':
            return _build_application_embed(gs, event, ch, track)

        # Generic log embeds
        if tpl_name:
            text = _format_template(gs, tpl_name, event)
            embed = {'description': text, 'color': c.get('color', 0x2ecc71)}
            return [{'type': 'send_embed', 'channel_id': ch, 'embed': embed}]
        return []

    if t == 'ADD_ROLE':
        if c.get('from_rule'):
            return _roles_from_invite_rule(gs, event)
        if c.get('from_form'):
            return _roles_from_form(gs, event)
        role_id = _resolve_role_id(gs, c)
        if role_id and user_id:
            return [{'type': 'add_role', 'guild_id': gs.guild_id, 'user_id': user_id,
                     'role_id': role_id, 'reason': c.get('reason', '')}]
        return []

    if t == 'REMOVE_ROLE':
        role_id = _resolve_role_id(gs, c)
        if role_id and user_id:
            return [{'type': 'remove_role', 'guild_id': gs.guild_id, 'user_id': user_id, 'role_id': role_id}]
        return []

    if t == 'SET_TOPIC':
        ch = _resolve_channel(gs, c.get('channel', 'pending'))
        tpl_name = c.get('template')
        content = c.get('content', '')
        if tpl_name:
            content = _format_template(gs, tpl_name, event)
        return [{'type': 'set_topic', 'channel_id': ch, 'topic': content}] if ch else []

    if t == 'SET_PERMS':
        if c.get('from_form'):
            return _channel_perms_from_form(gs, event)
        ch = _resolve_channel(gs, c.get('channel'))
        if ch and user_id:
            return [{'type': 'set_permissions', 'channel_id': ch, 'user_id': user_id,
                     'allow': c.get('allow', ['read_messages', 'send_messages'])}]
        return []

    if t == 'CLEANUP':
        ch = _resolve_channel(gs, c.get('channel', 'bounce'))
        if ch:
            return [{'type': 'cleanup_channel', 'channel_id': ch,
                     'count': c.get('count', 10), 'guild_id': gs.guild_id}]
        return []

    return []


# ── Automation action helpers ────────────────────────────────────────────────

def _format_template(gs, template_name, event):
    """Render a named template with event data."""
    tpl = get_template(gs, template_name)
    member = event.get('member', {})
    invite = event.get('invite', {})
    return tpl.format(
        user=f"<@{member.get('id', '')}>",
        invite_code=invite.get('code', 'unknown'),
        inviter=invite.get('inviter_name', 'Unknown'),
        roles='Pending' if event.get('mode') == 'APPROVAL' else 'See rules',
        pending=f"<@&{gs.pending_role_id}>" if gs.pending_role_id else '@Pending',
        server=gs.guild_name,
        form_url=event.get('form_url', ''),
        message='',
        admin='',
        reason='',
        bot_role='',
    )


def _build_application_embed(gs, event, channel_id, track):
    """Create Application record and return embed action."""
    member = event.get('member', {})

    app = Application.objects.create(
        guild=gs,
        user_id=member['id'],
        user_name=member.get('name', str(member['id'])),
        invite_code=event.get('invite', {}).get('code', 'unknown'),
        inviter_id=event.get('invite', {}).get('inviter_id'),
        inviter_name=event.get('invite', {}).get('inviter_name', 'Unknown'),
        status='PENDING',
        responses={},
    )

    has_form = FormField.objects.filter(guild=gs).exists()
    app_url = os.environ.get('APP_URL', 'https://your-domain.com').rstrip('/')
    if not app_url.startswith(('http://', 'https://')):
        app_url = f'https://{app_url}'
    form_url = f"{app_url}/form/{gs.guild_id}/"

    embed = {
        'title': f'\U0001f4cb Application #{app.id} \u2014 {app.user_name}',
        'color': 0xFFA500,
        'fields': [
            {'name': 'User', 'value': f'<@{app.user_id}>', 'inline': True},
            {'name': 'Invite', 'value': app.invite_code, 'inline': True},
            {'name': 'Invited by', 'value': app.inviter_name or 'Unknown', 'inline': True},
        ],
    }
    if has_form:
        embed['fields'].append({'name': 'Form', 'value': f'\u23f3 [Not submitted yet]({form_url})', 'inline': False})
    embed['fields'].append({
        'name': 'Actions',
        'value': (
            f'\u2705 `@Bot approve <@{app.user_id}>`\n'
            f'\u274c `@Bot reject <@{app.user_id}> [reason]`\n'
            'Or react \u2705 / \u274c'
        ),
        'inline': False,
    })

    action_dict = {
        'type': 'send_embed_tracked',
        'channel_id': channel_id,
        'embed': embed,
        'application_id': app.id,
    }
    results = [action_dict]

    if has_form and gs.pending_channel_id:
        tpl = get_template(gs, 'PENDING_CHANNEL_TOPIC')
        results.append({'type': 'set_topic', 'channel_id': gs.pending_channel_id,
                        'topic': tpl.format(form_url=form_url)})

    return results


def _roles_from_invite_rule(gs, event):
    """Resolve invite rule -> add_role actions."""
    invite = event.get('invite', {})
    code = invite.get('code', 'unknown')
    member = event.get('member', {})
    user_id = member.get('id') or event.get('user_id')
    if not user_id:
        return []

    rule = InviteRule.objects.prefetch_related('roles').filter(guild=gs, invite_code=code).first()
    if not rule:
        rule = InviteRule.objects.prefetch_related('roles').filter(guild=gs, invite_code='default').first()
    if not rule:
        return []

    return [
        {'type': 'add_role', 'guild_id': gs.guild_id, 'user_id': user_id,
         'role_id': r.discord_id, 'reason': f'Auto-assigned via invite {code}'}
        for r in rule.roles.all()
    ]


def _roles_from_form(gs, event):
    """Resolve form selections -> add_role actions."""
    user_id = event.get('member', {}).get('id') or event.get('user_id')
    app = (Application.objects.filter(guild=gs, user_id=user_id, status='PENDING')
           .order_by('-created_at').first() if user_id else None)
    if not app or not app.responses:
        return []
    role_ids, _ = _extract_form_selections(gs, app)
    return [
        {'type': 'add_role', 'guild_id': gs.guild_id, 'user_id': user_id, 'role_id': rid}
        for rid in role_ids
    ]


def _channel_perms_from_form(gs, event):
    """Resolve form selections -> set_permissions actions."""
    user_id = event.get('member', {}).get('id') or event.get('user_id')
    app = (Application.objects.filter(guild=gs, user_id=user_id, status='PENDING')
           .order_by('-created_at').first() if user_id else None)
    if not app or not app.responses:
        return []
    _, channel_ids = _extract_form_selections(gs, app)
    return [
        {'type': 'set_permissions', 'channel_id': cid, 'user_id': user_id,
         'allow': ['read_messages', 'send_messages']}
        for cid in channel_ids
    ]


# ── Event entry points (called by bot) ──────────────────────────────────────

def handle_member_join(event):
    """Process member_join via automations."""
    return process_event('MEMBER_JOIN', event)


def handle_member_remove(event):
    """Cancel PENDING applications for members who left."""
    Application.objects.filter(
        guild__guild_id=event['guild_id'],
        user_id=event['user_id'],
        status='PENDING',
    ).update(status='REJECTED')
    return []


def handle_reaction(event):
    """Handle checkmark/cross reaction on application embeds."""
    emoji = event.get('emoji')
    if emoji not in ('\u2705', '\u274c'):
        return []
    app_id = event.get('application_id')
    if not app_id:
        return []
    try:
        application = Application.objects.get(id=app_id, status='PENDING')
    except Application.DoesNotExist:
        return []

    gs = _get_guild(event['guild_id'])
    if not gs:
        return []

    admin = event['admin']
    if emoji == '\u2705':
        return _approve_user(gs, application, admin, event)
    return _reject_user(gs, application, admin, event, reason='Rejected via reaction')


# ── Shared approve / reject ─────────────────────────────────────────────────

def _approve_user(gs, application, admin, event, extra_role_ids=None, extra_channel_ids=None):
    """Core approval logic - used by both commands and reactions."""
    actions = []
    user_id = application.user_id

    # Remove Pending role
    if gs.pending_role_id:
        actions.append({'type': 'remove_role', 'guild_id': gs.guild_id,
                        'user_id': user_id, 'role_id': gs.pending_role_id})

    # Roles from invite rule
    rule = InviteRule.objects.prefetch_related('roles').filter(
        guild=gs, invite_code=application.invite_code).first()
    if not rule:
        rule = InviteRule.objects.prefetch_related('roles').filter(
            guild=gs, invite_code='default').first()

    assigned_names = []
    rule_role_ids = set()
    if rule:
        for r in rule.roles.all():
            actions.append({'type': 'add_role', 'guild_id': gs.guild_id, 'user_id': user_id,
                           'role_id': r.discord_id, 'reason': f'Approved by {admin["name"]}'})
            assigned_names.append(r.name)
            rule_role_ids.add(r.discord_id)

    # Roles + channels from form (if user filled it)
    all_channel_ids = set()
    if application.responses:
        role_ids, channel_ids = _extract_form_selections(gs, application)
        for rid in role_ids:
            if rid not in rule_role_ids:
                actions.append({'type': 'add_role', 'guild_id': gs.guild_id, 'user_id': user_id, 'role_id': rid})
                db_r = DiscordRole.objects.filter(guild=gs, discord_id=rid).first()
                assigned_names.append(db_r.name if db_r else str(rid))
        for cid in channel_ids:
            all_channel_ids.add(cid)

    # Extra channels from #mentions in approve command (appended)
    for cid in (extra_channel_ids or []):
        all_channel_ids.add(cid)

    # Grant channel access for all collected channels
    for cid in all_channel_ids:
        actions.append({'type': 'set_permissions', 'channel_id': cid, 'user_id': user_id,
                       'allow': ['read_messages', 'send_messages']})

    # Extra roles from @mentions in approve command (appended)
    for rid in (extra_role_ids or []):
        if not any(a.get('role_id') == rid for a in actions if a['type'] == 'add_role'):
            actions.append({'type': 'add_role', 'guild_id': gs.guild_id, 'user_id': user_id, 'role_id': rid})
            db_r = DiscordRole.objects.filter(guild=gs, discord_id=rid).first()
            assigned_names.append(db_r.name if db_r else str(rid))

    roles_str = ', '.join(assigned_names) or 'no specific roles'

    # Edit tracked embed in-place
    msg_id = event.get('message_id') or application.message_id
    if msg_id and gs.bounce_channel_id:
        original = event.get('original_embed', {})
        original['color'] = 0x2ecc71  # green
        if 'fields' not in original:
            original['fields'] = []
        original['fields'] = [f for f in original['fields'] if f.get('name') != 'Actions']
        status_tpl = get_template(gs, 'APPROVE_STATUS')
        original['fields'].append({'name': 'Status', 'value': status_tpl.format(admin=admin['name']), 'inline': False})
        original['fields'].append({'name': 'Roles', 'value': roles_str, 'inline': False})
        actions.append({'type': 'edit_message', 'channel_id': gs.bounce_channel_id,
                       'message_id': msg_id, 'embed': original})
        actions.append({'type': 'clear_reactions', 'channel_id': gs.bounce_channel_id, 'message_id': msg_id})

    # DM user
    tpl = get_template(gs, 'APPROVE_DM')
    actions.append({'type': 'send_dm', 'user_id': user_id,
                   'content': tpl.format(server=gs.guild_name, roles=roles_str)})

    # Cleanup old bot messages in bounce
    if gs.bounce_channel_id:
        actions.append({'type': 'cleanup_channel', 'channel_id': gs.bounce_channel_id,
                       'count': 50, 'guild_id': gs.guild_id})

    # Delete approved application
    application.delete()
    return actions


def _reject_user(gs, application, admin, event, reason='No reason provided'):
    """Core rejection logic - used by both commands and reactions."""
    actions = []
    user_id = application.user_id

    application.status = 'REJECTED'
    application.reviewed_by = admin['id']
    application.reviewed_by_name = admin['name']
    application.reviewed_at = timezone.now()
    application.save()

    # Remove Pending role
    if gs.pending_role_id:
        actions.append({'type': 'remove_role', 'guild_id': gs.guild_id,
                        'user_id': user_id, 'role_id': gs.pending_role_id})

    # Edit tracked embed in-place
    msg_id = event.get('message_id') or application.message_id
    if msg_id and gs.bounce_channel_id:
        original = event.get('original_embed', {})
        original['color'] = 0xe74c3c  # red
        if 'fields' not in original:
            original['fields'] = []
        original['fields'] = [f for f in original['fields'] if f.get('name') != 'Actions']
        status_tpl = get_template(gs, 'REJECT_STATUS')
        original['fields'].append({'name': 'Status', 'value': status_tpl.format(admin=admin['name']), 'inline': False})
        if reason and reason != 'No reason provided':
            original['fields'].append({'name': 'Reason', 'value': reason, 'inline': False})
        actions.append({'type': 'edit_message', 'channel_id': gs.bounce_channel_id,
                       'message_id': msg_id, 'embed': original})
        actions.append({'type': 'clear_reactions', 'channel_id': gs.bounce_channel_id, 'message_id': msg_id})

    # DM user
    tpl = get_template(gs, 'REJECT_DM')
    actions.append({'type': 'send_dm', 'user_id': user_id,
                   'content': tpl.format(server=gs.guild_name, reason=reason)})

    # Notify pending channel
    if gs.pending_channel_id:
        tpl = get_template(gs, 'REJECT_PENDING')
        actions.append({'type': 'send_message', 'channel_id': gs.pending_channel_id,
                       'content': tpl.format(user=f'<@{user_id}>', reason=reason)})

    return actions


# ── Command routing ──────────────────────────────────────────────────────────

class _CmdError(Exception):
    pass


def _require_admin(gs, author_role_ids):
    if gs.bot_admin_role_id not in author_role_ids:
        raise _CmdError(get_template(gs, 'ADMIN_REQUIRED'))


BUILTIN_COMMANDS = {}  # populated after function definitions


def handle_command(event):
    """Route a command to built-in handler or custom automation."""
    command_name = event['command']
    guild_id = event.get('guild_id')

    # getaccess is DM-only
    if command_name == 'getaccess':
        if guild_id:
            tpl = get_template(None, 'DM_ONLY_WARNING')
            return [{'type': 'reply', 'content': tpl}]
        return _cmd_getaccess(event)

    # Everything else needs a guild
    if not guild_id:
        tpl = get_template(None, 'SERVER_ONLY_WARNING')
        return [{'type': 'reply', 'content': tpl}]

    gs = _get_guild(guild_id)
    if not gs:
        return [{'type': 'reply', 'content': get_template(None, 'SERVER_NOT_CONFIGURED')}]

    # Built-in commands
    handler = BUILTIN_COMMANDS.get(command_name)
    if handler:
        try:
            return handler(gs, event)
        except _CmdError as e:
            tpl = get_template(gs, 'COMMAND_ERROR')
            return [{'type': 'reply', 'content': tpl.format(message=str(e))}]

    # Custom automations with trigger=COMMAND
    autos = Automation.objects.filter(
        guild=gs, trigger='COMMAND', enabled=True,
    ).prefetch_related('actions')

    for auto in autos:
        cfg_name = (auto.trigger_config or {}).get('name', '')
        if cfg_name == command_name:
            if auto.admin_only:
                try:
                    _require_admin(gs, event['author']['role_ids'])
                except _CmdError as e:
                    tpl = get_template(gs, 'COMMAND_ERROR')
                    return [{'type': 'reply', 'content': tpl.format(message=str(e))}]
            results = []
            for action in auto.actions.filter(enabled=True).order_by('order'):
                results.extend(_process_action(action, gs, event))
            return results

    # Nothing matched
    builtin_names = sorted(BUILTIN_COMMANDS.keys())
    custom_names = sorted(
        (a.trigger_config or {}).get('name', '?')
        for a in Automation.objects.filter(guild=gs, trigger='COMMAND', enabled=True)
    )
    all_cmds = ', '.join(builtin_names + custom_names) or 'none'
    tpl = get_template(gs, 'COMMAND_NOT_FOUND')
    return [{'type': 'reply', 'content': tpl.format(command=command_name, commands=all_cmds)}]


# ── Built-in command implementations ────────────────────────────────────────

def _cmd_help(gs, event):
    builtin_info = [
        ('help', 'Show this command list'),
        ('addrule', 'Add an invite rule (Admin)'),
        ('delrule', 'Delete an invite rule (Admin)'),
        ('listrules', 'List all invite rules'),
        ('setmode', 'Set AUTO / APPROVAL mode (Admin)'),
        ('approve', 'Approve a pending user, optionally with extra @roles/#channels (Admin)'),
        ('reject', 'Reject a pending user (Admin)'),
        ('cleanup', 'Delete resolved bot messages in this channel (Admin)'),
        ('cleanall', 'Delete ALL bot messages except pending apps in this channel (Admin)'),
        ('listfields', 'List form fields'),
        ('auto-translate', 'Set auto-translate language (Admin)'),
        ('reload', 'Reload configuration (Admin)'),
        ('getaccess', 'Get web panel link (DM only)'),
    ]
    lines = [f'\u2022 **{name}** \u2014 {desc}' for name, desc in builtin_info]

    customs = Automation.objects.filter(guild=gs, trigger='COMMAND', enabled=True)
    for a in customs:
        cmd_name = (a.trigger_config or {}).get('name', '?')
        lines.append(f'\u2022 **{cmd_name}** \u2014 {a.description or "Custom command"}')

    tpl = get_template(gs, 'HELP_MESSAGE')
    return [{'type': 'reply', 'content': tpl.format(
        commands='\n'.join(lines), bot_mention='@Bot')}]


def _cmd_addrule(gs, event):
    args = event['args']
    _require_admin(gs, event['author']['role_ids'])
    if len(args) < 2:
        raise _CmdError("Usage: `@Bot addrule <invite_code> <role1,role2,...> [description]`")

    invite_code = args[0]
    role_names = args[1].split(',')
    description = ' '.join(args[2:]) if len(args) > 2 else ''

    guild_roles = {r['name'].lower(): r for r in event.get('guild_roles', [])}
    roles_to_add = []
    for name in role_names:
        name = name.strip()
        r = guild_roles.get(name.lower())
        if not r:
            raise _CmdError(f"Role not found: `{name}`")
        db_role, _ = DiscordRole.objects.get_or_create(
            discord_id=r['id'], guild=gs, defaults={'name': r['name']})
        roles_to_add.append(db_role)

    rule, _ = InviteRule.objects.get_or_create(
        guild=gs, invite_code=invite_code, defaults={'description': description})
    rule.roles.set(roles_to_add)

    role_str = ', '.join(r.name for r in roles_to_add)
    tpl = get_template(gs, 'COMMAND_SUCCESS')
    return [{'type': 'reply', 'content': tpl.format(message=f'Invite rule created: `{invite_code}` \u2192 {role_str}')}]


def _cmd_delrule(gs, event):
    args = event['args']
    _require_admin(gs, event['author']['role_ids'])
    if len(args) < 1:
        raise _CmdError("Usage: `@Bot delrule <invite_code>`")
    try:
        rule = InviteRule.objects.get(guild=gs, invite_code=args[0])
        rule.delete()
        tpl = get_template(gs, 'COMMAND_SUCCESS')
        return [{'type': 'reply', 'content': tpl.format(message=f'Invite rule deleted: `{args[0]}`')}]
    except InviteRule.DoesNotExist:
        raise _CmdError(f"Rule not found: `{args[0]}`")


def _cmd_listrules(gs, event):
    rules = InviteRule.objects.filter(guild=gs).prefetch_related('roles')
    if not rules.exists():
        return [{'type': 'reply', 'content': get_template(gs, 'LISTRULES_EMPTY')}]
    embed = {'title': '\U0001f4cb Invite Rules', 'color': 0x3498db, 'fields': []}
    for rule in rules:
        role_names = ', '.join(r.name for r in rule.roles.all())
        val = f"**Roles:** {role_names or 'None'}"
        if rule.description:
            val += f"\n*{rule.description}*"
        embed['fields'].append({'name': f'`{rule.invite_code}`', 'value': val, 'inline': False})
    return [{'type': 'send_embed', 'channel_id': event['channel_id'], 'embed': embed}]


def _cmd_setmode(gs, event):
    args = event['args']
    _require_admin(gs, event['author']['role_ids'])
    if len(args) < 1:
        raise _CmdError("Usage: `@Bot setmode <AUTO|APPROVAL>`")
    mode = args[0].upper()
    if mode not in ('AUTO', 'APPROVAL'):
        raise _CmdError("Mode must be AUTO or APPROVAL")
    old = gs.mode
    gs.mode = mode
    gs.save()
    actions = []
    if mode == 'APPROVAL':
        actions.append({'type': 'ensure_resources', 'guild_id': gs.guild_id})
    tpl = get_template(gs, 'COMMAND_SUCCESS')
    actions.append({'type': 'reply', 'content': tpl.format(
        message=f'Server mode changed from **{old}** to **{mode}**')})
    return actions


def _cmd_listfields(gs, event):
    fields = FormField.objects.select_related('dropdown').filter(guild=gs).order_by('order')
    if not fields.exists():
        return [{'type': 'reply', 'content': get_template(gs, 'LISTFIELDS_EMPTY')}]
    embed = {'title': '\U0001f4cb Application Form Fields', 'color': 0x3498db, 'fields': []}
    for f in fields:
        req = "\u2705 Required" if f.required else "\u2b55 Optional"
        details = f"Type: `{f.get_field_type_display()}` \u2022 {req}"
        if f.field_type == 'dropdown' and f.dropdown:
            src = f.dropdown.get_source_type_display()
            multi = " (multiple)" if f.dropdown.multiselect else ""
            opts = f.dropdown.get_options()[:5]
            preview = ', '.join(o['label'] for o in opts)
            if len(f.dropdown.get_options()) > 5:
                preview += f" (+{len(f.dropdown.get_options()) - 5} more)"
            details += f"\nDropdown: **{f.dropdown.name}** [{src}]{multi}"
            if preview:
                details += f"\nOptions: {preview}"
        if f.placeholder:
            details += f"\nPlaceholder: *{f.placeholder}*"
        embed['fields'].append({'name': f.label, 'value': details, 'inline': False})
    return [{'type': 'send_embed', 'channel_id': event['channel_id'], 'embed': embed}]


def _cmd_reload(gs, event):
    _require_admin(gs, event['author']['role_ids'])
    actions = []
    for r in event.get('guild_roles', []):
        DiscordRole.objects.update_or_create(discord_id=r['id'], guild=gs, defaults={'name': r['name']})
    for c in event.get('guild_channels', []):
        DiscordChannel.objects.update_or_create(discord_id=c['id'], guild=gs, defaults={'name': c['name']})

    missing_apps = 0
    if gs.mode == 'APPROVAL':
        existing = set(Application.objects.filter(guild=gs).values_list('user_id', flat=True))
        for m in event.get('guild_members', []):
            if m.get('bot') or m['id'] in existing:
                continue
            Application.objects.create(
                guild=gs, user_id=m['id'], user_name=m['name'],
                invite_code='reload', inviter_name='System (reload)',
                status='PENDING', responses={})
            missing_apps += 1

    actions.append({'type': 'ensure_resources', 'guild_id': gs.guild_id})
    details = f"{len(event.get('guild_roles', []))} roles, {len(event.get('guild_channels', []))} channels"
    if gs.mode == 'APPROVAL':
        details += f", {missing_apps} missing applications created"
    tpl = get_template(gs, 'COMMAND_SUCCESS')
    actions.append({'type': 'reply', 'content': tpl.format(
        message=f'Reloaded configuration ({details}). All resources verified.')})
    return actions


def _cmd_approve(gs, event):
    _require_admin(gs, event['author']['role_ids'])
    args = event['args']
    if len(args) < 1:
        raise _CmdError("Usage: `@Bot approve @user [@role ...] [#channel ...]` or `@Bot approve @Role`")

    user_mentions = event.get('user_mentions', [])
    role_mentions = event.get('role_mentions', [])
    channel_mentions = event.get('channel_mentions', [])

    # Bulk approve: role mentioned with no users
    if not user_mentions and role_mentions:
        return _cmd_bulk_approve(gs, event, role_mentions[0])

    if not user_mentions:
        raise _CmdError("Please mention the user to approve: `@Bot approve @user`")

    target = user_mentions[0]

    # get_or_create: approve works even if no Application exists
    # (e.g. user has Pending role but wasn't tracked)
    application, _created = Application.objects.get_or_create(
        guild=gs, user_id=target['id'], status='PENDING',
        defaults={
            'user_name': target['name'],
            'invite_code': 'manual',
            'inviter_name': f"Approved by {event['author']['name']}",
            'responses': {},
        },
    )

    extra_role_ids = [r['id'] for r in role_mentions if r['id'] != gs.bot_admin_role_id]
    extra_channel_ids = [c['id'] for c in channel_mentions]

    result = _approve_user(gs, application, event['author'], event,
                           extra_role_ids=extra_role_ids,
                           extra_channel_ids=extra_channel_ids)
    tpl = get_template(gs, 'APPROVE_CONFIRM')
    extras = []
    if extra_role_ids:
        role_names = [r['name'] for r in role_mentions if r['id'] in extra_role_ids]
        extras.append(f"roles: {', '.join(role_names)}")
    if extra_channel_ids:
        ch_names = [f"#{c['name']}" for c in channel_mentions]
        extras.append(f"channels: {', '.join(ch_names)}")
    extras_str = '; '.join(extras) if extras else 'from rules/form'
    result.append({'type': 'reply', 'content': tpl.format(
        user=target['name'], roles=extras_str)})
    return result


def _cmd_bulk_approve(gs, event, target_role):
    """Approve all members with the given role."""
    actions = []
    members = event.get('members_with_role', [])
    approved = 0

    for m in members:
        # get_or_create: works even without a prior Application
        app, _created = Application.objects.get_or_create(
            guild=gs, user_id=m['id'], status='PENDING',
            defaults={
                'user_name': m['name'],
                'invite_code': 'bulk',
                'inviter_name': f"Bulk approved by {event['author']['name']}",
                'responses': {},
            },
        )
        actions.extend(_approve_user(gs, app, event['author'], event))
        approved += 1

    report = get_template(gs, 'BULK_APPROVE_RESULT').format(
        approved=approved, skipped=0)
    actions.append({'type': 'reply', 'content': report})
    return actions


def _cmd_reject(gs, event):
    _require_admin(gs, event['author']['role_ids'])
    args = event['args']
    if len(args) < 1:
        raise _CmdError("Usage: `@Bot reject @user [reason]`")

    user_mentions = event.get('user_mentions', [])
    if not user_mentions:
        raise _CmdError("Please mention the user to reject: `@Bot reject @user [reason]`")

    target = user_mentions[0]
    reason = ' '.join(args[1:]) if len(args) > 1 else 'No reason provided'

    application = Application.objects.filter(
        guild=gs, user_id=target['id'], status='PENDING'
    ).order_by('-created_at').first()
    if not application:
        raise _CmdError(get_template(gs, 'NO_PENDING_APP').format(name=target['name']))

    result = _reject_user(gs, application, event['author'], event, reason=reason)
    tpl = get_template(gs, 'REJECT_CONFIRM')
    result.append({'type': 'reply', 'content': tpl.format(user=target['name'], reason=reason)})
    return result


def _cmd_getaccess(event):
    """Generate access token. DM-only."""
    author = event['author']
    admin_guilds = event.get('admin_guilds', [])

    if not admin_guilds:
        tpl = get_template(None, 'GETACCESS_NO_ADMIN')
        return [{'type': 'send_dm', 'user_id': author['id'], 'content': tpl}]

    selected = admin_guilds[0]
    gs = _get_guild(selected['guild_id'])
    if not gs:
        return [{'type': 'send_dm', 'user_id': author['id'], 'content': '\u274c Server not found.'}]

    app_url = os.environ.get('APP_URL', 'https://your-domain.com').rstrip('/')
    if not app_url.startswith(('http://', 'https://')):
        app_url = f'https://{app_url}'

    existing = AccessToken.objects.filter(
        user_id=author['id'], guild=gs, expires_at__gt=timezone.now()).first()
    if existing:
        url = f"{app_url}/auth/login/?token={existing.token}"
        tpl = get_template(gs, 'GETACCESS_EXISTS')
        return [{'type': 'send_dm', 'user_id': author['id'], 'content': tpl.format(
            server=gs.guild_name, url=url, expires=existing.expires_at.strftime('%Y-%m-%d %H:%M:%S UTC'))}]

    token = secrets.token_urlsafe(32)
    expires_at = timezone.now() + timedelta(hours=24)
    AccessToken.objects.create(
        token=token, user_id=author['id'], user_name=author['name'],
        guild=gs, expires_at=expires_at)
    url = f"{app_url}/auth/login/?token={token}"
    tpl = get_template(gs, 'GETACCESS_RESPONSE')
    return [{'type': 'send_dm', 'user_id': author['id'], 'content': tpl.format(
        server=gs.guild_name, url=url, expires=expires_at.strftime('%Y-%m-%d %H:%M:%S UTC'))}]


def _cmd_cleanup(gs, event):
    """Delete resolved (non-pending) bot messages in the calling channel."""
    _require_admin(gs, event['author']['role_ids'])
    channel_id = event.get('channel_id')
    if not channel_id:
        raise _CmdError("Could not determine the current channel.")
    return [
        {'type': 'cleanup_channel', 'channel_id': channel_id,
         'count': 50, 'guild_id': gs.guild_id},
        {'type': 'reply', 'content': get_template(gs, 'CLEANUP_REPLY').format(count=50)},
    ]


def _cmd_cleanall(gs, event):
    """Delete ALL bot messages except pending application embeds in the calling channel."""
    _require_admin(gs, event['author']['role_ids'])
    channel_id = event.get('channel_id')
    if not channel_id:
        raise _CmdError("Could not determine the current channel.")
    return [
        {'type': 'cleanup_channel', 'channel_id': channel_id,
         'count': 999, 'guild_id': gs.guild_id},
        {'type': 'reply', 'content': get_template(gs, 'CLEANALL_REPLY')},
    ]


def _cmd_auto_translate(gs, event):
    """Enable or disable auto-translate for this guild."""
    _require_admin(gs, event['author']['role_ids'])
    args = event['args']
    if len(args) < 1:
        raise _CmdError("Usage: `@Bot auto-translate on <language_code>` or `@Bot auto-translate off`")

    action = args[0].lower()
    if action == 'off':
        gs.language = None
        gs.save()
        tpl = get_template(gs, 'AUTO_TRANSLATE_OFF')
        return [{'type': 'reply', 'content': tpl}]
    elif action == 'on':
        if len(args) < 2:
            raise _CmdError("Usage: `@Bot auto-translate on <language_code>` (e.g. `fr`, `es`, `de`)")
        lang_input = args[1]
        try:
            from bot.handlers.translate import validate_language
            code = validate_language(lang_input)
        except Exception:
            code = lang_input.lower()[:10]  # fallback: accept as-is
        if not code:
            raise _CmdError(f"Unsupported language: `{lang_input}`. Use a language code like `fr`, `es`, `de`, `ja`.")
        gs.language = code
        gs.save()
        tpl = get_template(gs, 'AUTO_TRANSLATE_ON')
        return [{'type': 'reply', 'content': tpl.format(language=code)}]
    else:
        raise _CmdError("Usage: `@Bot auto-translate on <language_code>` or `@Bot auto-translate off`")


# Register built-in commands
BUILTIN_COMMANDS.update({
    'help': _cmd_help,
    'addrule': _cmd_addrule,
    'delrule': _cmd_delrule,
    'listrules': _cmd_listrules,
    'setmode': _cmd_setmode,
    'listfields': _cmd_listfields,
    'reload': _cmd_reload,
    'approve': _cmd_approve,
    'reject': _cmd_reject,
    'cleanup': _cmd_cleanup,
    'cleanall': _cmd_cleanall,
    'auto-translate': _cmd_auto_translate,
})
