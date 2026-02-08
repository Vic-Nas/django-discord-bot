"""
Django service layer — ALL business logic lives here.

The bot sends events as simple dicts. This module processes them
using Django ORM and returns a list of actions for the bot to execute.

Action format: {"type": "...", ...params}
Supported types:
  - send_message:    {channel_id, content}
  - send_embed:      {channel_id, embed}
  - send_dm:         {user_id, content}
  - add_role:        {guild_id, user_id, role_id, reason?}
  - remove_role:     {guild_id, user_id, role_id}
  - edit_message:    {channel_id, message_id, embed}
  - clear_reactions: {channel_id, message_id}
  - set_permissions: {channel_id, user_id, allow}
  - set_topic:       {channel_id, topic}
  - create_role:     {guild_id, name, color}
  - create_channel:  {guild_id, name, overwrites}
"""

import os
import secrets
from datetime import timedelta
from django.utils import timezone
from .models import (
    GuildSettings, DiscordRole, DiscordChannel, InviteRule,
    Application, BotCommand, CommandAction, AccessToken, FormField,
)
from bot.handlers.templates import get_template


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_guild(guild_id):
    try:
        return GuildSettings.objects.get(guild_id=guild_id)
    except GuildSettings.DoesNotExist:
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
                role = DiscordRole.objects.get(guild=field.guild, discord_id=int(rid))
                names.append(role.name)
            except (DiscordRole.DoesNotExist, ValueError):
                names.append(rid)
        return ', '.join(names)
    elif source == 'CHANNELS':
        names = []
        for cid in ids:
            try:
                ch = DiscordChannel.objects.get(guild=field.guild, discord_id=int(cid))
                names.append(f'#{ch.name}' if ch.name else cid)
            except (DiscordChannel.DoesNotExist, ValueError):
                names.append(cid)
        return ', '.join(names)
    elif source == 'CUSTOM':
        option_map = {o.value: o.label for o in field.dropdown.custom_options.all()}
        return ', '.join(option_map.get(v, v) for v in ids)
    return raw_value


def _extract_form_selections(guild_settings, application):
    """Extract role IDs and channel IDs from dropdown responses."""
    fields = FormField.objects.select_related('dropdown').filter(
        guild=guild_settings, field_type='dropdown'
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
            if not val:
                continue
            try:
                int_val = int(val)
            except ValueError:
                continue
            if field.dropdown.source_type == 'ROLES':
                role_ids.append(int_val)
            elif field.dropdown.source_type == 'CHANNELS':
                channel_ids.append(int_val)
    return role_ids, channel_ids


# ── Event handlers ───────────────────────────────────────────────────────────

def handle_member_join(event):
    """Process member_join event. Returns list of actions."""
    guild_id = event['guild_id']
    gs = _get_guild(guild_id)
    if not gs:
        return []

    member = event['member']
    invite = event.get('invite', {})
    invite_code = invite.get('code', 'unknown')
    inviter_id = invite.get('inviter_id')
    inviter_name = invite.get('inviter_name', 'Unknown')

    actions = []

    if gs.mode == 'AUTO':
        actions += _handle_auto_join(gs, member, invite_code, inviter_name)
    else:
        actions += _handle_approval_join(gs, member, invite_code, inviter_id, inviter_name)

    # Log the join
    actions += _log_join(gs, member, invite_code, inviter_name)

    return actions


def _handle_auto_join(gs, member, invite_code, inviter_name):
    """AUTO mode: assign roles immediately."""
    actions = []

    # Find rule
    rule = InviteRule.objects.prefetch_related('roles').filter(
        guild=gs, invite_code=invite_code
    ).first()
    if not rule:
        rule = InviteRule.objects.prefetch_related('roles').filter(
            guild=gs, invite_code='default'
        ).first()
    if not rule:
        return actions

    # Assign roles from rule
    for db_role in rule.roles.all():
        actions.append({
            'type': 'add_role',
            'guild_id': gs.guild_id,
            'user_id': member['id'],
            'role_id': db_role.discord_id,
            'reason': f'Auto-assigned via invite {invite_code}',
        })

    return actions


def _handle_approval_join(gs, member, invite_code, inviter_id, inviter_name):
    """APPROVAL mode: assign Pending role, create Application, send form link."""
    actions = []

    # Assign Pending role
    if gs.pending_role_id:
        actions.append({
            'type': 'add_role',
            'guild_id': gs.guild_id,
            'user_id': member['id'],
            'role_id': gs.pending_role_id,
            'reason': 'Pending approval',
        })

    # Create Application record
    application = Application.objects.create(
        guild=gs,
        user_id=member['id'],
        user_name=member['name'],
        invite_code=invite_code,
        inviter_id=inviter_id,
        inviter_name=inviter_name,
        status='PENDING',
        responses={},
    )

    # Check if form fields exist
    fields = list(FormField.objects.filter(guild=gs))
    if not fields:
        # No form — post directly to approvals
        actions += _build_application_embed(gs, application)
    else:
        # Set pending channel topic with form link
        app_url = os.environ.get('APP_URL', 'https://your-domain.com').rstrip('/')
        if not app_url.startswith(('http://', 'https://')):
            app_url = f'https://{app_url}'
        form_url = f"{app_url}/form/{gs.guild_id}/"
        if gs.pending_channel_id:
            template = get_template(gs, 'PENDING_CHANNEL_TOPIC')
            actions.append({
                'type': 'set_topic',
                'channel_id': gs.pending_channel_id,
                'topic': template.format(form_url=form_url),
            })

    return actions


def _log_join(gs, member, invite_code, inviter_name):
    """Build log message for #bounce channel."""
    if not gs.logs_channel_id:
        return []

    template_type = 'JOIN_LOG_AUTO' if gs.mode == 'AUTO' else 'JOIN_LOG_APPROVAL'
    template = get_template(gs, template_type)

    text = template.format(
        user=f"<@{member['id']}>",
        invite_code=invite_code,
        inviter=inviter_name,
        roles='Pending' if gs.mode == 'APPROVAL' else 'See above',
        pending=f"<@&{gs.pending_role_id}>" if gs.pending_role_id else '@Pending',
    )

    return [{
        'type': 'send_embed',
        'channel_id': gs.logs_channel_id,
        'embed': {'description': text, 'color': 0x2ecc71},
    }]


def _build_application_embed(gs, application):
    """Build the application embed for #approvals (no form fields case)."""
    if not gs.approvals_channel_id:
        return []

    embed = {
        'title': f'📋 Application #{application.id} — {application.user_name}',
        'color': 0xFFA500,
        'fields': [
            {'name': 'User', 'value': f'<@{application.user_id}>', 'inline': True},
            {'name': 'Invite', 'value': application.invite_code, 'inline': True},
            {'name': 'Invited by', 'value': application.inviter_name or 'Unknown', 'inline': True},
            {'name': 'Actions', 'value': (
                f'✅ `@Bot approve <@{application.user_id}>`\n'
                f'❌ `@Bot reject <@{application.user_id}> [reason]`'
            ), 'inline': False},
        ],
    }

    return [{'type': 'send_embed', 'channel_id': gs.approvals_channel_id, 'embed': embed}]


def handle_member_remove(event):
    """Cancel PENDING applications for members who left."""
    Application.objects.filter(
        guild__guild_id=event['guild_id'],
        user_id=event['user_id'],
        status='PENDING',
    ).update(status='REJECTED')
    return []


def handle_reaction(event):
    """Handle ✅/❌ reaction on application embed."""
    guild_id = event['guild_id']
    gs = _get_guild(guild_id)
    if not gs:
        return []

    emoji = event['emoji']
    if emoji not in ('✅', '❌'):
        return []

    app_id = event.get('application_id')
    if not app_id:
        return []

    try:
        application = Application.objects.get(id=app_id, status='PENDING')
    except Application.DoesNotExist:
        return []

    admin = event['admin']

    # Check BotAdmin permission (bot verified this before calling)
    if emoji == '✅':
        return _approve_via_reaction(gs, application, admin, event)
    else:
        return _reject_via_reaction(gs, application, admin, event)


def _approve_via_reaction(gs, application, admin, event):
    """Approve application from reaction."""
    actions = []
    app_id = application.id
    guild_id = gs.guild_id

    # Find matching invite rule
    rule = InviteRule.objects.prefetch_related('roles').filter(
        guild=gs, invite_code=application.invite_code
    ).first()
    if not rule:
        rule = InviteRule.objects.prefetch_related('roles').filter(
            guild=gs, invite_code='default'
        ).first()

    # Remove Pending role
    if gs.pending_role_id:
        actions.append({
            'type': 'remove_role',
            'guild_id': guild_id,
            'user_id': application.user_id,
            'role_id': gs.pending_role_id,
        })

    # Assign roles from rule
    role_names = []
    if rule:
        for db_role in rule.roles.all():
            actions.append({
                'type': 'add_role',
                'guild_id': guild_id,
                'user_id': application.user_id,
                'role_id': db_role.discord_id,
                'reason': f'Application approved by {admin["name"]}',
            })
            role_names.append(db_role.name)

    # Update embed
    msg_id = event.get('message_id')
    ch_id = event.get('channel_id')
    if msg_id and ch_id:
        embed = event.get('original_embed', {})
        embed['color'] = 0x2ecc71  # green
        if 'fields' not in embed:
            embed['fields'] = []
        embed['fields'].append({'name': 'Status', 'value': f'✅ Approved by <@{admin["id"]}>', 'inline': False})
        embed['fields'].append({'name': 'Roles Assigned', 'value': ', '.join(role_names) or 'None', 'inline': False})
        actions.append({'type': 'edit_message', 'channel_id': ch_id, 'message_id': msg_id, 'embed': embed})
        actions.append({'type': 'clear_reactions', 'channel_id': ch_id, 'message_id': msg_id})

    # DM the user
    template = get_template(gs, 'APPLICATION_APPROVED')
    actions.append({
        'type': 'send_dm',
        'user_id': application.user_id,
        'content': template.format(server=gs.guild_name, roles=', '.join(role_names) or 'None'),
    })

    # Delete the approved application
    application.delete()

    return actions


def _reject_via_reaction(gs, application, admin, event):
    """Reject application from reaction."""
    actions = []
    guild_id = gs.guild_id

    # Update application
    application.status = 'REJECTED'
    application.reviewed_by = admin['id']
    application.reviewed_by_name = admin['name']
    application.reviewed_at = timezone.now()
    application.save()

    # Remove Pending role
    if gs.pending_role_id:
        actions.append({
            'type': 'remove_role',
            'guild_id': guild_id,
            'user_id': application.user_id,
            'role_id': gs.pending_role_id,
        })

    # Update embed
    msg_id = event.get('message_id')
    ch_id = event.get('channel_id')
    if msg_id and ch_id:
        embed = event.get('original_embed', {})
        embed['color'] = 0xe74c3c  # red
        if 'fields' not in embed:
            embed['fields'] = []
        embed['fields'].append({'name': 'Status', 'value': f'❌ Rejected by <@{admin["id"]}>', 'inline': False})
        actions.append({'type': 'edit_message', 'channel_id': ch_id, 'message_id': msg_id, 'embed': embed})
        actions.append({'type': 'clear_reactions', 'channel_id': ch_id, 'message_id': msg_id})

    # DM the user
    template = get_template(gs, 'APPLICATION_REJECTED')
    actions.append({
        'type': 'send_dm',
        'user_id': application.user_id,
        'content': template.format(
            server=gs.guild_name,
            reason='Your application did not meet our requirements at this time.',
        ),
    })

    return actions


# ── Command handlers ─────────────────────────────────────────────────────────

def handle_command(event):
    """Route a command event to the appropriate handler."""
    guild_id = event.get('guild_id')
    command_name = event['command']
    args = event.get('args', [])
    author = event['author']

    # getaccess: DM-only, no guild needed
    if command_name == 'getaccess':
        if guild_id:
            tpl = get_template(None, 'DM_ONLY_WARNING')
            return [{'type': 'reply', 'content': tpl}]
        return _cmd_getaccess(event)

    # All other commands need a guild
    if not guild_id:
        tpl = get_template(None, 'SERVER_ONLY_WARNING')
        return [{'type': 'reply', 'content': tpl}]

    gs = _get_guild(guild_id)
    if not gs:
        return [{'type': 'reply', 'content': '❌ This server is not configured.'}]

    # Look up command in DB
    try:
        bot_cmd = BotCommand.objects.get(guild=gs, name=command_name)
    except BotCommand.DoesNotExist:
        available = list(BotCommand.objects.filter(guild=gs, enabled=True).values_list('name', flat=True))
        tpl = get_template(gs, 'COMMAND_NOT_FOUND')
        return [{'type': 'reply', 'content': tpl.format(command=command_name, commands=', '.join(sorted(available)) or 'none')}]

    if not bot_cmd.enabled:
        tpl = get_template(gs, 'COMMAND_DISABLED')
        return [{'type': 'reply', 'content': tpl.format(command=command_name)}]

    # Get first action type to determine handler
    action = CommandAction.objects.filter(command=bot_cmd, enabled=True).order_by('order').first()
    if not action:
        return [{'type': 'reply', 'content': f'⚠️ Command `{command_name}` has no actions configured.'}]

    handler_map = {
        'ADD_INVITE_RULE': _cmd_addrule,
        'DELETE_INVITE_RULE': _cmd_delrule,
        'LIST_INVITE_RULES': _cmd_listrules,
        'SET_SERVER_MODE': _cmd_setmode,
        'LIST_COMMANDS': _cmd_listcommands,
        'LIST_FORM_FIELDS': _cmd_listfields,
        'RELOAD_CONFIG': _cmd_reload,
        'APPROVE_APPLICATION': _cmd_approve,
        'REJECT_APPLICATION': _cmd_reject,
    }

    handler = handler_map.get(action.type)
    if not handler:
        return [{'type': 'reply', 'content': f'⚠️ Unknown action type: {action.type}'}]

    try:
        return handler(gs, event)
    except _CmdError as e:
        tpl = get_template(gs, 'COMMAND_ERROR')
        return [{'type': 'reply', 'content': tpl.format(message=str(e))}]


class _CmdError(Exception):
    pass


def _require_admin(gs, author_role_ids):
    if gs.bot_admin_role_id not in author_role_ids:
        raise _CmdError("You need the **BotAdmin** role to use this command.")


# ── Individual commands ──────────────────────────────────────────────────────

def _cmd_addrule(gs, event):
    args = event['args']
    _require_admin(gs, event['author']['role_ids'])
    if len(args) < 2:
        raise _CmdError("Usage: `@Bot addrule <invite_code> <role1,role2,...> [description]`")

    invite_code = args[0]
    role_names_input = args[1].split(',')
    description = ' '.join(args[2:]) if len(args) > 2 else ''

    # Match roles from guild_roles in event
    guild_roles = {r['name'].lower(): r for r in event.get('guild_roles', [])}
    roles_to_add = []
    for name in role_names_input:
        name = name.strip()
        r = guild_roles.get(name.lower())
        if not r:
            raise _CmdError(f"Role not found: `{name}`")
        db_role, _ = DiscordRole.objects.get_or_create(
            discord_id=r['id'], guild=gs, defaults={'name': r['name']}
        )
        roles_to_add.append(db_role)

    rule, _ = InviteRule.objects.get_or_create(
        guild=gs, invite_code=invite_code, defaults={'description': description}
    )
    rule.roles.set(roles_to_add)

    role_str = ', '.join(r.name for r in roles_to_add)
    tpl = get_template(gs, 'COMMAND_SUCCESS')
    return [{'type': 'reply', 'content': tpl.format(message=f'Invite rule created: `{invite_code}` → {role_str}')}]


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
        return [{'type': 'reply', 'content': '📋 No rules configured yet.'}]

    embed = {'title': '📋 Invite Rules', 'color': 0x3498db, 'fields': []}
    for rule in rules:
        role_names = ', '.join(r.name for r in rule.roles.all())
        value = f"**Roles:** {role_names or 'None'}"
        if rule.description:
            value += f"\n*{rule.description}*"
        embed['fields'].append({'name': f'`{rule.invite_code}`', 'value': value, 'inline': False})

    return [{'type': 'send_embed', 'channel_id': event['channel_id'], 'embed': embed}]


def _cmd_setmode(gs, event):
    args = event['args']
    _require_admin(gs, event['author']['role_ids'])
    if len(args) < 1:
        raise _CmdError("Usage: `@Bot setmode <AUTO|APPROVAL>`")

    mode = args[0].upper()
    if mode not in ('AUTO', 'APPROVAL'):
        raise _CmdError("Mode must be AUTO or APPROVAL")

    old_mode = gs.mode
    gs.mode = mode
    gs.save()

    actions = []
    # If switching to APPROVAL, bot needs to ensure channels exist
    if mode == 'APPROVAL':
        actions.append({'type': 'ensure_resources', 'guild_id': gs.guild_id})

    tpl = get_template(gs, 'COMMAND_SUCCESS')
    actions.append({'type': 'reply', 'content': tpl.format(message=f'Server mode changed from **{old_mode}** to **{mode}**')})
    return actions


def _cmd_listcommands(gs, event):
    commands = BotCommand.objects.filter(guild=gs, enabled=True).order_by('name')
    if not commands.exists():
        return [{'type': 'reply', 'content': '📋 No commands configured.'}]

    cmd_list = '\n'.join(f'• **{c.name}** - {c.description}' for c in commands)
    return [{'type': 'reply', 'content': f'📋 **Available Commands:**\n{cmd_list}'}]


def _cmd_listfields(gs, event):
    fields = FormField.objects.select_related('dropdown').filter(guild=gs).order_by('order')
    if not fields.exists():
        return [{'type': 'reply', 'content': '📋 No form fields configured yet. Add them in the admin panel.'}]

    embed = {'title': '📋 Application Form Fields', 'color': 0x3498db, 'fields': []}
    for field in fields:
        required_str = "✅ Required" if field.required else "⭕ Optional"
        type_display = field.get_field_type_display()
        details = f"Type: `{type_display}` • {required_str}"
        if field.field_type == 'dropdown' and field.dropdown:
            source = field.dropdown.get_source_type_display()
            multi = " (multiple)" if field.dropdown.multiselect else ""
            options = field.dropdown.get_options()
            option_names = [o['label'] for o in options[:5]]
            preview = ', '.join(option_names)
            if len(options) > 5:
                preview += f" (+{len(options) - 5} more)"
            details += f"\nDropdown: **{field.dropdown.name}** [{source}]{multi}"
            if preview:
                details += f"\nOptions: {preview}"
        if field.placeholder:
            details += f"\nPlaceholder: *{field.placeholder}*"
        embed['fields'].append({'name': field.label, 'value': details, 'inline': False})

    return [{'type': 'send_embed', 'channel_id': event['channel_id'], 'embed': embed}]


def _cmd_reload(gs, event):
    _require_admin(gs, event['author']['role_ids'])

    actions = []

    # Sync roles from event data
    guild_roles = event.get('guild_roles', [])
    for r in guild_roles:
        DiscordRole.objects.update_or_create(
            discord_id=r['id'], guild=gs, defaults={'name': r['name']}
        )

    # Sync channels from event data
    guild_channels = event.get('guild_channels', [])
    for c in guild_channels:
        DiscordChannel.objects.update_or_create(
            discord_id=c['id'], guild=gs, defaults={'name': c['name']}
        )

    # Create missing applications for APPROVAL mode
    missing_apps = 0
    if gs.mode == 'APPROVAL':
        existing_user_ids = set(Application.objects.filter(guild=gs).values_list('user_id', flat=True))
        guild_members = event.get('guild_members', [])
        for m in guild_members:
            if m.get('bot', False):
                continue
            if m['id'] not in existing_user_ids:
                Application.objects.create(
                    guild=gs,
                    user_id=m['id'],
                    user_name=m['name'],
                    invite_code='reload',
                    inviter_name='System (reload)',
                    status='PENDING',
                    responses={},
                )
                missing_apps += 1

    # Ensure resources exist (bot-side)
    actions.append({'type': 'ensure_resources', 'guild_id': gs.guild_id})

    details = f"{len(guild_roles)} roles, {len(guild_channels)} channels"
    if gs.mode == 'APPROVAL':
        details += f", {missing_apps} missing applications created"

    tpl = get_template(gs, 'COMMAND_SUCCESS')
    actions.append({'type': 'reply', 'content': tpl.format(message=f'Reloaded configuration ({details}). All resources verified.')})
    return actions


def _cmd_approve(gs, event):
    _require_admin(gs, event['author']['role_ids'])
    args = event['args']
    if len(args) < 1:
        raise _CmdError("Usage: `@Bot approve @user [@role ...]` or `@Bot approve @Role`")

    user_mentions = event.get('user_mentions', [])
    role_mentions = event.get('role_mentions', [])
    admin_role_id = gs.bot_admin_role_id

    # Bulk approve: role mentioned with no users
    if not user_mentions and role_mentions:
        return _cmd_bulk_approve(gs, event, role_mentions[0])

    if not user_mentions:
        raise _CmdError("Please mention the user to approve: `@Bot approve @user`")

    target = user_mentions[0]
    actions = []

    # Find pending application
    application = Application.objects.filter(
        guild=gs, user_id=target['id'], status='PENDING'
    ).order_by('-created_at').first()

    # Collect roles: from @mentions + form selections
    role_ids_to_assign = [r['id'] for r in role_mentions if r['id'] != admin_role_id]
    channels_to_allow = []

    if application and application.responses:
        form_role_ids, form_channel_ids = _extract_form_selections(gs, application)
        for rid in form_role_ids:
            if rid not in role_ids_to_assign:
                role_ids_to_assign.append(rid)
        channels_to_allow = form_channel_ids

    # Remove Pending role
    if gs.pending_role_id:
        actions.append({
            'type': 'remove_role',
            'guild_id': gs.guild_id,
            'user_id': target['id'],
            'role_id': gs.pending_role_id,
        })

    # Assign roles
    assigned_role_names = []
    for rid in role_ids_to_assign:
        actions.append({
            'type': 'add_role',
            'guild_id': gs.guild_id,
            'user_id': target['id'],
            'role_id': rid,
        })
        db_role = DiscordRole.objects.filter(guild=gs, discord_id=rid).first()
        assigned_role_names.append(db_role.name if db_role else str(rid))

    # Grant channel access
    for cid in channels_to_allow:
        actions.append({
            'type': 'set_permissions',
            'channel_id': cid,
            'user_id': target['id'],
            'allow': ['read_messages', 'send_messages'],
        })

    # Delete the approved application
    if application:
        application.delete()

    # DM the user
    roles_str = ', '.join(assigned_role_names) or 'no specific roles'
    tpl = get_template(gs, 'APPROVE_DM')
    actions.append({'type': 'send_dm', 'user_id': target['id'], 'content': tpl.format(server=gs.guild_name, roles=roles_str)})

    # Confirmation in channel
    tpl = get_template(gs, 'APPROVE_CONFIRM')
    actions.append({'type': 'reply', 'content': tpl.format(user=target['name'], roles=roles_str)})

    return actions


def _cmd_bulk_approve(gs, event, target_role):
    """Approve all members with the given role who have submitted their form."""
    actions = []
    members = event.get('members_with_role', [])
    summary = {'approved': 0, 'skipped': 0}

    for m in members:
        app = Application.objects.filter(
            guild=gs, user_id=m['id']
        ).order_by('-created_at').first()

        if not app or not app.responses:
            summary['skipped'] += 1
            continue

        # Extract form selections
        role_ids, channel_ids = _extract_form_selections(gs, app)

        # Remove Pending role
        if gs.pending_role_id:
            actions.append({'type': 'remove_role', 'guild_id': gs.guild_id, 'user_id': m['id'], 'role_id': gs.pending_role_id})

        # Assign roles
        role_names = []
        for rid in role_ids:
            actions.append({'type': 'add_role', 'guild_id': gs.guild_id, 'user_id': m['id'], 'role_id': rid})
            db_role = DiscordRole.objects.filter(guild=gs, discord_id=rid).first()
            role_names.append(db_role.name if db_role else str(rid))

        # Channel permissions
        for cid in channel_ids:
            actions.append({'type': 'set_permissions', 'channel_id': cid, 'user_id': m['id'], 'allow': ['read_messages', 'send_messages']})

        # DM
        roles_str = ', '.join(role_names) or 'no specific roles'
        tpl = get_template(gs, 'APPROVE_DM')
        actions.append({'type': 'send_dm', 'user_id': m['id'], 'content': tpl.format(server=gs.guild_name, roles=roles_str)})

        # Delete approved application
        app.delete()
        summary['approved'] += 1

    report = f"✅ **Bulk approve complete — {summary['approved']} approved**"
    if summary['skipped']:
        report += f"\n⏭️ Skipped (form not filled): {summary['skipped']}"
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
    actions = []

    # Update application
    application = Application.objects.filter(
        guild=gs, user_id=target['id'], status='PENDING'
    ).order_by('-created_at').first()

    if application:
        application.status = 'REJECTED'
        application.reviewed_by = event['author']['id']
        application.reviewed_by_name = event['author']['name']
        application.reviewed_at = timezone.now()
        application.save()

    # Post to #pending
    if gs.pending_channel_id:
        tpl = get_template(gs, 'REJECT_PENDING')
        actions.append({
            'type': 'send_message',
            'channel_id': gs.pending_channel_id,
            'content': tpl.format(user=f"<@{target['id']}>", reason=reason),
        })

    # Remove Pending role
    if gs.pending_role_id:
        actions.append({
            'type': 'remove_role',
            'guild_id': gs.guild_id,
            'user_id': target['id'],
            'role_id': gs.pending_role_id,
        })

    # DM user
    tpl = get_template(gs, 'REJECT_DM')
    actions.append({'type': 'send_dm', 'user_id': target['id'], 'content': tpl.format(server=gs.guild_name, reason=reason)})

    # Confirmation
    tpl = get_template(gs, 'REJECT_CONFIRM')
    actions.append({'type': 'reply', 'content': tpl.format(user=target['name'], reason=reason)})
    return actions


def _cmd_getaccess(event):
    """Generate access token. DM-only."""
    author = event['author']
    admin_guilds = event.get('admin_guilds', [])

    if not admin_guilds:
        tpl = get_template(None, 'GETACCESS_NO_ADMIN')
        return [{'type': 'send_dm', 'user_id': author['id'], 'content': tpl}]

    # If multiple guilds, the bot handles the selection flow and sends the chosen guild_id
    selected = admin_guilds[0]
    gs = _get_guild(selected['guild_id'])
    if not gs:
        return [{'type': 'send_dm', 'user_id': author['id'], 'content': '❌ Server not found.'}]

    app_url = os.environ.get('APP_URL', 'https://your-domain.com').rstrip('/')
    if not app_url.startswith(('http://', 'https://')):
        app_url = f'https://{app_url}'

    # Check existing token
    existing = AccessToken.objects.filter(
        user_id=author['id'], guild=gs, expires_at__gt=timezone.now()
    ).first()

    if existing:
        expires_str = existing.expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')
        url = f"{app_url}/auth/login/?token={existing.token}"
        tpl = get_template(gs, 'GETACCESS_EXISTS')
        return [{'type': 'send_dm', 'user_id': author['id'], 'content': tpl.format(server=gs.guild_name, url=url, expires=expires_str)}]

    # Create new token
    token = secrets.token_urlsafe(32)
    expires_at = timezone.now() + timedelta(hours=24)
    AccessToken.objects.create(
        token=token, user_id=author['id'], user_name=author['name'],
        guild=gs, expires_at=expires_at,
    )

    expires_str = expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')
    url = f"{app_url}/auth/login/?token={token}"
    tpl = get_template(gs, 'GETACCESS_RESPONSE')
    return [{'type': 'send_dm', 'user_id': author['id'], 'content': tpl.format(server=gs.guild_name, url=url, expires=expires_str)}]
