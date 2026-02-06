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
    
    for db_role in rule.roles.filter(is_deleted=False):
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
    APPROVAL mode: Assign Pending role, collect application.
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
    
    # Send application form to user
    await send_application_form(bot, member, guild_settings, invite_data)


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


async def send_application_form(bot, member, guild_settings, invite_data):
    """Send application form to user via DM"""
    
    # Get form fields
    from core.models import FormField
    fields = await sync_to_async(lambda: list(FormField.objects.filter(guild=guild_settings).order_by('order')))()
    
    if not fields:
        # No form configured, just notify user
        template = await get_template_async(guild_settings, 'APPLICATION_SENT')
        message = template.format(server=member.guild.name)
        
        try:
            await member.send(message)
        except:
            print(f'❌ Could not DM {member.name}')
        return
    
    # Send form questions one by one
    try:
        await member.send(f"📋 **Application for {member.guild.name}**\n\nPlease answer the following questions:")
        
        responses = {}
        
        for field in fields:
            # Ask question
            question = f"**{field.label}**"
            if field.required:
                question += " (required)"
            
            if field.field_type in ['select', 'radio', 'checkbox'] and field.options:
                question += "\nOptions: " + ", ".join(field.options)
            
            await member.send(question)
            
            # Wait for response
            def check(m):
                return m.author == member and isinstance(m.channel, discord.DMChannel)
            
            try:
                response = await bot.wait_for('message', check=check, timeout=300)  # 5 min timeout
                responses[field.id] = response.content
            except:
                if field.required:
                    await member.send("❌ Application timed out. Please try again.")
                    return
                responses[field.id] = ""
        
        # Save application
        inviter_id = invite_data['inviter'].id if invite_data['inviter'] else None
        inviter_name = invite_data['inviter'].name if invite_data['inviter'] else 'Unknown'
        
        application = await sync_to_async(Application.objects.create)(
            guild=guild_settings,
            user_id=member.id,
            user_name=str(member),
            invite_code=invite_data['code'],
            inviter_id=inviter_id,
            inviter_name=inviter_name,
            responses=responses
        )
        
        # Confirm to user
        template = await get_template_async(guild_settings, 'APPLICATION_SENT')
        message = template.format(server=member.guild.name)
        await member.send(message)
        
        # Post to approvals channel
        await post_application_for_review(bot, guild_settings, member, application, invite_data)
        
    except Exception as e:
        print(f'❌ Error sending application form: {e}')
        try:
            await member.send("❌ Sorry, there was an error with the application form. Please contact an admin.")
        except:
            pass


async def post_application_for_review(bot, guild_settings, member, application, invite_data):
    """Post application to approvals channel for admin review"""
    
    if not guild_settings.approvals_channel_id:
        return
    
    channel = bot.get_channel(guild_settings.approvals_channel_id)
    if not channel:
        return
    
    # Format responses
    from core.models import FormField
    fields = await sync_to_async(lambda: list(FormField.objects.filter(guild=guild_settings).order_by('order')))()
    
    responses_text = ""
    for field in fields:
        answer = application.responses.get(str(field.id), "No answer")
        responses_text += f"**{field.label}:** {answer}\n"
    
    template = await get_template_async(guild_settings, 'APPROVAL_NOTIFICATION')
    inviter_name = invite_data['inviter'].name if invite_data['inviter'] else 'Unknown'
    
    message = template.format(
        user=member.mention,
        invite_code=invite_data['code'],
        inviter=inviter_name,
        responses=responses_text
    )
    
    embed = discord.Embed(
        title=f"Application #{application.id}",
        description=message,
        color=discord.Color.orange()
    )
    
    msg = await channel.send(embed=embed)
    
    # Add reactions for approve/reject
    await msg.add_reaction('✅')
    await msg.add_reaction('❌')
