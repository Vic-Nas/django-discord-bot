import discord
from django.utils import timezone
from core.models import GuildSettings, Application, InviteRule
from .templates import get_template


async def handle_reaction(bot, payload):
    """
    Handle reactions on application messages.
    ✅ = approve, ❌ = reject
    """
    
    # Get the message
    channel = bot.get_channel(payload.channel_id)
    if not channel:
        return
    
    try:
        message = await channel.fetch_message(payload.message_id)
    except:
        return
    
    # Check if this is an application message
    if not message.embeds or not message.embeds[0].title or 'Application #' not in message.embeds[0].title:
        return
    
    # Extract application ID
    try:
        app_id = int(message.embeds[0].title.split('#')[1])
    except:
        return
    
    # Get application
    try:
        application = Application.objects.get(id=app_id, status='PENDING')
    except Application.DoesNotExist:
        return
    
    # Get guild settings
    guild_settings = application.guild
    
    # Check if user has BotAdmin role
    guild = bot.get_guild(guild_settings.guild_id)
    if not guild:
        return
    
    member = guild.get_member(payload.user_id)
    if not member:
        return
    
    admin_role = guild.get_role(guild_settings.bot_admin_role_id)
    if not admin_role or admin_role not in member.roles:
        # Remove reaction if not admin
        await message.remove_reaction(payload.emoji, member)
        return
    
    # Get the applicant
    applicant = guild.get_member(application.user_id)
    if not applicant:
        await channel.send(f"❌ User has left the server.")
        return
    
    # Handle approval or rejection
    if str(payload.emoji) == '✅':
        await approve_application(bot, application, applicant, member, message)
    elif str(payload.emoji) == '❌':
        await reject_application(bot, application, applicant, member, message)


async def approve_application(bot, application, applicant, admin, message):
    """Approve application and assign roles"""
    
    guild_settings = application.guild
    guild = applicant.guild
    
    # Update application status
    application.status = 'APPROVED'
    application.reviewed_by = admin.id
    application.reviewed_at = timezone.now()
    application.save()
    
    # Get rule for the invite code
    try:
        rule = InviteRule.objects.prefetch_related('roles').get(
            guild=guild_settings,
            invite_code=application.invite_code
        )
    except InviteRule.DoesNotExist:
        # Try default rule
        try:
            rule = InviteRule.objects.prefetch_related('roles').get(
                guild=guild_settings,
                invite_code='default'
            )
        except InviteRule.DoesNotExist:
            await message.channel.send(f"⚠️ No rule found for invite `{application.invite_code}` and no default rule.")
            return
    
    # Remove Pending role
    pending_role = guild.get_role(guild_settings.pending_role_id)
    if pending_role and pending_role in applicant.roles:
        try:
            await applicant.remove_roles(pending_role)
        except:
            pass
    
    # Assign roles from rule
    roles_to_assign = []
    role_names = []
    
    for db_role in rule.roles.filter(is_deleted=False):
        discord_role = guild.get_role(db_role.discord_id)
        if discord_role:
            roles_to_assign.append(discord_role)
            role_names.append(discord_role.name)
    
    if roles_to_assign:
        try:
            await applicant.add_roles(*roles_to_assign, reason=f'Application approved by {admin.name}')
        except Exception as e:
            await message.channel.send(f"❌ Error assigning roles: {e}")
            return
    
    # Update embed
    embed = message.embeds[0]
    embed.color = discord.Color.green()
    embed.add_field(name="Status", value=f"✅ Approved by {admin.mention}", inline=False)
    embed.add_field(name="Roles Assigned", value=', '.join(role_names) if role_names else 'None', inline=False)
    await message.edit(embed=embed)
    await message.clear_reactions()
    
    # DM the user
    template = get_template(guild_settings, 'APPLICATION_APPROVED')
    dm_message = template.format(
        server=guild.name,
        roles=', '.join(role_names) if role_names else 'None'
    )
    
    try:
        await applicant.send(dm_message)
    except:
        pass
    
    print(f'✅ Application #{application.id} approved by {admin.name}')


async def reject_application(bot, application, applicant, admin, message):
    """Reject application"""
    
    guild_settings = application.guild
    guild = applicant.guild
    
    # Update application status
    application.status = 'REJECTED'
    application.reviewed_by = admin.id
    application.reviewed_at = timezone.now()
    application.save()
    
    # Update embed
    embed = message.embeds[0]
    embed.color = discord.Color.red()
    embed.add_field(name="Status", value=f"❌ Rejected by {admin.mention}", inline=False)
    await message.edit(embed=embed)
    await message.clear_reactions()
    
    # DM the user
    template = get_template(guild_settings, 'APPLICATION_REJECTED')
    dm_message = template.format(
        server=guild.name,
        reason="Your application did not meet our requirements at this time."
    )
    
    try:
        await applicant.send(dm_message)
    except:
        pass
    
    # Optionally kick the user
    # await applicant.kick(reason=f'Application rejected by {admin.name}')
    
    print(f'❌ Application #{application.id} rejected by {admin.name}')
