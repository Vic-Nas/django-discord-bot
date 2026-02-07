import os
import discord
from core.models import GuildSettings, InviteRule, Application
from .templates import get_template_async
from .guild_setup import ensure_required_resources
from asgiref.sync import sync_to_async


async def handle_member_join(bot, member, invite_cache):
    """
    Handle member join event.
    Detects invite used, then routes to AUTO or APPROVAL mode.
    """
    
    guild = member.guild
    
    # Get guild settings
    try:
        guild_settings = await sync_to_async(GuildSettings.objects.get)(guild_id=guild.id)
    except GuildSettings.DoesNotExist:
        print(f'⚠️ No settings for guild {guild.name}, skipping')
        return
    
    # Detect which invite was used
    invite_data = await detect_invite_used(guild, invite_cache)
    
    if not invite_data:
        print(f'⚠️ Could not detect invite for {member.name}')
        invite_data = {'code': 'unknown', 'inviter': None}
    
    # Route based on mode
    if guild_settings.mode == 'AUTO':
        await handle_auto_mode(bot, member, guild_settings, invite_data)
    else:  # APPROVAL
        await handle_approval_mode(bot, member, guild_settings, invite_data)


async def detect_invite_used(guild, invite_cache):
    """
    Compare cached invites with current invites to detect which was used.
    Returns: {'code': str, 'inviter': Member}
    """
    
    try:
        current_invites = await guild.invites()
        current_uses = {inv.code: inv.uses for inv in current_invites}
        
        if guild.id not in invite_cache:
            invite_cache[guild.id] = current_uses
            return None
        
        # Find invite with increased uses
        for code, uses in current_uses.items():
            cached_uses = invite_cache[guild.id].get(code, 0)
            if uses > cached_uses:
                # Found it!
                invite = discord.utils.get(current_invites, code=code)
                invite_cache[guild.id] = current_uses
                return {
                    'code': code,
                    'inviter': invite.inviter if invite else None
                }
        
        # Update cache and return unknown
        invite_cache[guild.id] = current_uses
        return None
        
    except Exception as e:
        print(f'❌ Error detecting invite: {e}')
        return None


async def handle_auto_mode(bot, member, guild_settings, invite_data):
    """
    AUTO mode: Immediately assign roles based on invite rule.
    """
    
    # Ensure required resources exist
    await ensure_required_resources(bot, guild_settings)
    
    # Get rule for this invite
    invite_code = invite_data['code']
    
    try:
        rule = await sync_to_async(lambda: InviteRule.objects.prefetch_related('roles').get(
            guild=guild_settings,
            invite_code=invite_code
        ))()
    except InviteRule.DoesNotExist:
        # Try default rule
        try:
            rule = await sync_to_async(lambda: InviteRule.objects.prefetch_related('roles').get(
                guild=guild_settings,
                invite_code='default'
            ))()
        except InviteRule.DoesNotExist:
            print(f'⚠️ No rule for invite {invite_code} and no default rule')
            await log_join(bot, member, guild_settings, invite_data, [], 'AUTO')
            return
    
    # Assign roles
    roles_to_assign = []
    role_names = []
    
    for db_role in rule.roles.all():
        discord_role = member.guild.get_role(db_role.discord_id)
        if discord_role:
            roles_to_assign.append(discord_role)
            role_names.append(discord_role.name)
    
    if roles_to_assign:
        try:
            await member.add_roles(*roles_to_assign, reason=f'Auto-assigned via invite {invite_code}')
            print(f'✅ Assigned roles {role_names} to {member.name}')
        except Exception as e:
            print(f'❌ Failed to assign roles: {e}')
    
    # Log the join
    await log_join(bot, member, guild_settings, invite_data, role_names, 'AUTO')


async def handle_approval_mode(bot, member, guild_settings, invite_data):
    """
    APPROVAL mode: Assign Pending role, send form link in #pending channel.
    The user fills the form on the web. When submitted, the bot posts to #approvals.
    """
    
    # Ensure required resources exist
    await ensure_required_resources(bot, guild_settings)
    
    # Assign Pending role
    pending_role = member.guild.get_role(guild_settings.pending_role_id)
    if pending_role:
        try:
            await member.add_roles(pending_role, reason='Pending approval')
        except Exception as e:
            print(f'❌ Failed to assign Pending role: {e}')
    
    # Log the join
    await log_join(bot, member, guild_settings, invite_data, ['Pending'], 'APPROVAL')
    
    # Send form link in #pending channel
    await send_form_link(bot, member, guild_settings, invite_data)


async def log_join(bot, member, guild_settings, invite_data, roles, mode):
    """Log member join to bounce channel"""
    
    if not guild_settings.logs_channel_id:  # bounce_channel_id
        return
    
    channel = bot.get_channel(guild_settings.logs_channel_id)  # bounce channel
    if not channel:
        return
    
    template_type = 'JOIN_LOG_AUTO' if mode == 'AUTO' else 'JOIN_LOG_APPROVAL'
    template = await get_template_async(guild_settings, template_type)
    
    inviter_name = invite_data['inviter'].name if invite_data['inviter'] else 'Unknown'
    roles_str = ', '.join(roles) if roles else 'None'
    
    pending_role = member.guild.get_role(guild_settings.pending_role_id) if guild_settings.pending_role_id else None
    
    message = template.format(
        user=member.mention,
        invite_code=invite_data['code'],
        inviter=inviter_name,
        roles=roles_str,
        pending=pending_role.mention if pending_role else '@Pending'
    )
    
    embed = discord.Embed(description=message, color=discord.Color.green())
    await channel.send(embed=embed)


async def send_form_link(bot, member, guild_settings, invite_data):
    """Send form link in the #pending channel so the new member can fill it out."""
    from core.models import FormField

    # Get form fields to check if any exist
    fields = await sync_to_async(
        lambda: list(FormField.objects.select_related('dropdown').filter(guild=guild_settings).order_by('order'))
    )()

    # Build form URL
    app_url = os.environ.get('APP_URL', 'https://your-domain.com').rstrip('/')
    if not app_url.startswith(('http://', 'https://')):
        app_url = f'https://{app_url}'
    form_url = f"{app_url}/form/{guild_settings.guild_id}?user={member.id}&invite={invite_data['code']}"

    # Send in #pending channel
    pending_channel = bot.get_channel(guild_settings.pending_channel_id) if guild_settings.pending_channel_id else None
    if not pending_channel:
        # Fallback: try to find a channel named 'pending'
        pending_channel = discord.utils.get(member.guild.text_channels, name='pending')

    if not pending_channel:
        print(f'⚠️ No #pending channel found for {member.guild.name}')
        return

    # Always create an Application record to track the member
    inviter_id = invite_data['inviter'].id if invite_data['inviter'] else None
    inviter_name = invite_data['inviter'].name if invite_data['inviter'] else 'Unknown'

    application = await sync_to_async(Application.objects.create)(
        guild=guild_settings,
        user_id=member.id,
        user_name=str(member),
        invite_code=invite_data['code'],
        inviter_id=inviter_id,
        inviter_name=inviter_name,
        status='PENDING',
        responses={}
    )

    if not fields:
        await pending_channel.send(
            f"👋 Welcome {member.mention}! No application form is configured yet. "
            f"Please wait for an admin to review your join request."
        )
        # Still notify admins in #approvals
        await post_application_for_review(bot, guild_settings, member, application, invite_data)
        return

    field_list = '\n'.join([f"• {f.label}" for f in fields])
    await pending_channel.send(
        f"👋 Welcome {member.mention}!\n\n"
        f"To complete your application for **{member.guild.name}**, please fill out the form:\n"
        f"🔗 [Application Form]({form_url})\n\n"
        f"The form will ask you about:\n{field_list}\n\n"
        f"Once submitted, an admin will review your application."
    )

    # Do NOT post to #approvals yet — that happens when the form is submitted on the web


async def post_application_for_review(bot, guild_settings, member, application, invite_data):
    """Post application to approvals channel for admin review (used when no form fields exist)."""
    
    if not guild_settings.approvals_channel_id:
        return
    
    channel = bot.get_channel(guild_settings.approvals_channel_id)
    if not channel:
        return
    
    # Format responses — resolve dropdown IDs to human-readable names
    from core.models import FormField, DiscordRole, DiscordChannel
    fields = await sync_to_async(lambda: list(FormField.objects.select_related('dropdown').filter(guild=guild_settings).order_by('order')))()
    
    responses_text = ""
    for field in fields:
        raw_answer = application.responses.get(str(field.id), "No answer")
        answer = await sync_to_async(lambda f=field, v=raw_answer: _resolve_value(f, v))()
        responses_text += f"**{field.label}:** {answer}\n"
    
    inviter_name = invite_data.get('inviter_name') if isinstance(invite_data, dict) else 'Unknown'
    if not inviter_name:
        inviter_name = invite_data.get('inviter', {})
        if hasattr(inviter_name, 'name'):
            inviter_name = inviter_name.name
        else:
            inviter_name = 'Unknown'
    
    invite_code = invite_data.get('code', 'unknown') if isinstance(invite_data, dict) else 'unknown'
    
    embed = discord.Embed(
        title=f"📋 Application #{application.id} — {application.user_name}",
        color=discord.Color.orange()
    )
    embed.add_field(name="User", value=f"<@{application.user_id}>", inline=True)
    embed.add_field(name="Invite", value=invite_code, inline=True)
    embed.add_field(name="Invited by", value=inviter_name, inline=True)
    
    if responses_text:
        embed.add_field(name="Responses", value=responses_text, inline=False)
    
    embed.add_field(
        name="Actions",
        value=(
            f"✅ `@Bot approve <@{application.user_id}> role1,role2`\n"
            f"❌ `@Bot reject <@{application.user_id}> [reason]`"
        ),
        inline=False
    )
    
    await channel.send(embed=embed)


def _resolve_value(field, raw_value):
    """Resolve raw dropdown value to display name (sync helper)."""
    from core.models import DiscordRole, DiscordChannel

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
