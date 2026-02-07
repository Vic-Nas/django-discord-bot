"""
ExecutionEngine for CommandActions

Reads CommandActions from database and executes them sequentially.
Each action type (SEND_MESSAGE, ADD_INVITE_RULE, LIST_RULES, etc) is executed with parameters from JSON.
"""

import json
import discord
import secrets
from asgiref.sync import sync_to_async
from django.utils import timezone
from django.db.models import Max
from datetime import timedelta


class ExecutionError(Exception):
    """Raised when an action fails to execute"""
    pass


async def execute_command_actions(bot, message, command_obj, guild_settings, args=None):
    """
    Execute all CommandActions for a BotCommand in order.
    
    Args:
        bot: discord.py Bot instance
        message: discord.Message that triggered the command
        command_obj: BotCommand instance from database
        guild_settings: GuildSettings instance for this server
        args: List of command arguments (optional)
    
    Returns:
        List of (success: bool, message: str) tuples for each action
    """
    
    if args is None:
        args = []
    
    results = []
    
    # Get all actions ordered by order field
    actions = await sync_to_async(
        lambda: list(command_obj.actions.filter(enabled=True).order_by('order'))
    )()
    
    if not actions:
        await message.channel.send(f"⚠️ Command `{command_obj.name}` has no actions configured.")
        return results
    
    # Execute each action
    for action in actions:
        try:
            await execute_single_action(bot, message, action, guild_settings, args)
            results.append((True, f"✅ {action.name}"))
        except ExecutionError as e:
            results.append((False, f"❌ {action.name}: {str(e)}"))
            # Continue to next action even if one fails
        except Exception as e:
            results.append((False, f"❌ {action.name}: Unexpected error: {str(e)}"))
    
    return results


async def execute_single_action(bot, message, action_obj, guild_settings, args=None):
    """
    Execute a single CommandAction.
    
    Args:
        bot: discord.py Bot instance
        message: discord.Message that triggered the command
        action_obj: CommandAction instance
        guild_settings: GuildSettings instance
        args: List of command arguments
        
    Raises:
        ExecutionError: If action fails
    """
    
    if args is None:
        args = []
    
    action_type = action_obj.type
    params = action_obj.parameters or {}
    
    # Route to appropriate handler based on action type string
    if action_type == 'SEND_MESSAGE':
        await handle_send_message(bot, message, params)
    
    elif action_type == 'ASSIGN_ROLE':
        await handle_assign_role(bot, message, params)
    
    elif action_type == 'REMOVE_ROLE':
        await handle_remove_role(bot, message, params)
    
    elif action_type == 'CREATE_CHANNEL':
        await handle_create_channel(bot, message, params)
    
    elif action_type == 'DELETE_CHANNEL':
        await handle_delete_channel(bot, message, params)
    
    elif action_type == 'POLL':
        await handle_poll(bot, message, params)
    
    elif action_type == 'WEBHOOK':
        await handle_webhook(bot, message, params)
    
    elif action_type == 'ADD_INVITE_RULE':
        await handle_add_invite_rule(bot, message, params, args, guild_settings)
    
    elif action_type == 'DELETE_INVITE_RULE':
        await handle_delete_invite_rule(bot, message, params, args, guild_settings)
    
    elif action_type == 'LIST_INVITE_RULES':
        await handle_list_invite_rules(bot, message, params, guild_settings)
    
    elif action_type == 'SET_SERVER_MODE':
        await handle_set_server_mode(bot, message, params, args, guild_settings)
    
    elif action_type == 'LIST_COMMANDS':
        await handle_list_commands(bot, message, params, guild_settings)
    
    elif action_type == 'GENERATE_ACCESS_TOKEN':
        await handle_generate_access_token(bot, message, params, guild_settings)
    
    elif action_type == 'APPROVE_APPLICATION':
        await handle_approve_application(bot, message, params, args, guild_settings)
    
    elif action_type == 'REJECT_APPLICATION':
        await handle_reject_application(bot, message, params, args, guild_settings)
    
    elif action_type == 'LIST_FORM_FIELDS':
        await handle_list_form_fields(bot, message, params, guild_settings)
    
    elif action_type == 'RELOAD_CONFIG':
        await handle_reload_config(bot, message, params, guild_settings)
    
    else:
        raise ExecutionError(f"Unknown action type: {action_type}")


async def handle_send_message(bot, message, params):
    """SEND_MESSAGE: Send a message to a channel"""
    
    if not params or 'text' not in params:
        raise ExecutionError("Missing 'text' parameter")
    
    text = params.get('text', '')
    channel_id = params.get('channel_id')  # If None, use current channel
    
    target_channel = None
    if channel_id:
        target_channel = bot.get_channel(int(channel_id))
        if not target_channel:
            raise ExecutionError(f"Channel {channel_id} not found")
    else:
        target_channel = message.channel
    
    if not text.strip():
        raise ExecutionError("Message text is empty")
    
    try:
        await target_channel.send(text)
    except discord.Forbidden:
        raise ExecutionError(f"No permission to send message to {target_channel.mention}")
    except discord.HTTPException as e:
        raise ExecutionError(f"Failed to send message: {str(e)}")


async def handle_assign_role(bot, message, params):
    """ASSIGN_ROLE: Assign a role to the user"""
    
    if not params or 'role_id' not in params:
        raise ExecutionError("Missing 'role_id' parameter")
    
    role_id = int(params.get('role_id'))
    target_member = params.get('target_user_id')
    
    # If no target user specified, assign to command invoker
    if target_member:
        try:
            member = await message.guild.fetch_member(int(target_member))
        except discord.NotFound:
            raise ExecutionError(f"User {target_member} not found in this server")
    else:
        member = message.author
    
    role = message.guild.get_role(role_id)
    if not role:
        raise ExecutionError(f"Role {role_id} not found in this server")
    
    if role in member.roles:
        raise ExecutionError(f"{member.mention} already has role {role.mention}")
    
    try:
        await member.add_roles(role)
    except discord.Forbidden:
        raise ExecutionError(f"Bot doesn't have permission to assign {role.mention}")
    except discord.HTTPException as e:
        raise ExecutionError(f"Failed to assign role: {str(e)}")


async def handle_remove_role(bot, message, params):
    """REMOVE_ROLE: Remove a role from the user"""
    
    if not params or 'role_id' not in params:
        raise ExecutionError("Missing 'role_id' parameter")
    
    role_id = int(params.get('role_id'))
    target_member = params.get('target_user_id')
    
    # If no target user specified, remove from command invoker
    if target_member:
        try:
            member = await message.guild.fetch_member(int(target_member))
        except discord.NotFound:
            raise ExecutionError(f"User {target_member} not found in this server")
    else:
        member = message.author
    
    role = message.guild.get_role(role_id)
    if not role:
        raise ExecutionError(f"Role {role_id} not found in this server")
    
    if role not in member.roles:
        raise ExecutionError(f"{member.mention} doesn't have role {role.mention}")
    
    try:
        await member.remove_roles(role)
    except discord.Forbidden:
        raise ExecutionError(f"Bot doesn't have permission to remove {role.mention}")
    except discord.HTTPException as e:
        raise ExecutionError(f"Failed to remove role: {str(e)}")


async def handle_create_channel(bot, message, params):
    """CREATE_CHANNEL: Create a new text channel"""
    
    if not params or 'name' not in params:
        raise ExecutionError("Missing 'name' parameter")
    
    channel_name = params.get('name', '').strip()
    
    if not channel_name:
        raise ExecutionError("Channel name is empty")
    
    # Validate channel name (Discord requirements)
    if len(channel_name) > 100:
        raise ExecutionError("Channel name too long (max 100 chars)")
    
    try:
        new_channel = await message.guild.create_text_channel(channel_name)
    except discord.Forbidden:
        raise ExecutionError("Bot doesn't have permission to create channels")
    except discord.HTTPException as e:
        raise ExecutionError(f"Failed to create channel: {str(e)}")


async def handle_delete_channel(bot, message, params):
    """DELETE_CHANNEL: Delete a channel"""
    
    if not params or 'channel_id' not in params:
        raise ExecutionError("Missing 'channel_id' parameter")
    
    channel_id = int(params.get('channel_id'))
    channel = bot.get_channel(channel_id)
    
    if not channel:
        raise ExecutionError(f"Channel {channel_id} not found")
    
    if channel.guild.id != message.guild.id:
        raise ExecutionError("Channel is not in this server")
    
    try:
        await channel.delete()
    except discord.Forbidden:
        raise ExecutionError("Bot doesn't have permission to delete this channel")
    except discord.HTTPException as e:
        raise ExecutionError(f"Failed to delete channel: {str(e)}")


async def handle_poll(bot, message, params):
    """POLL: Create a poll with reactions"""
    
    if not params or 'question' not in params:
        raise ExecutionError("Missing 'question' parameter")
    
    question = params.get('question', '').strip()
    options = params.get('options', [])  # List of option strings
    
    if not question:
        raise ExecutionError("Poll question is empty")
    
    if not options or len(options) < 2:
        raise ExecutionError("Poll needs at least 2 options")
    
    # Build poll message
    poll_text = f"📊 **{question}**\n\n"
    emojis = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']
    
    for i, option in enumerate(options[:len(emojis)]):
        poll_text += f"{emojis[i]} {option}\n"
    
    try:
        poll_msg = await message.channel.send(poll_text)
        
        # Add reactions
        for i in range(len(options)):
            await poll_msg.add_reaction(emojis[i])
    
    except discord.Forbidden:
        raise ExecutionError("Bot doesn't have permission to send or react to messages")
    except discord.HTTPException as e:
        raise ExecutionError(f"Failed to create poll: {str(e)}")


async def handle_webhook(bot, message, params):
    """WEBHOOK: Send message to external webhook"""
    
    if not params or 'webhook_url' not in params:
        raise ExecutionError("Missing 'webhook_url' parameter")
    
    webhook_url = params.get('webhook_url', '').strip()
    text = params.get('text', '').strip()
    
    if not webhook_url:
        raise ExecutionError("Webhook URL is empty")
    
    if not text:
        raise ExecutionError("Webhook message text is empty")
    
    # Note: Actual webhook execution would require aiohttp or requests
    # For now, just validate and log
    if not webhook_url.startswith('http'):
        raise ExecutionError("Invalid webhook URL")
    
    # In production, implement actual HTTP POST here
    # import aiohttp
    # async with aiohttp.ClientSession() as session:
    #     await session.post(webhook_url, json={'content': text})
    
    raise ExecutionError("Webhook execution not yet implemented")


# ===== Real Command Logic Actions =====

async def handle_add_invite_rule(bot, message, params, args, guild_settings):
    """ADD_INVITE_RULE: Add an invite code -> roles mapping"""
    from core.models import InviteRule, DiscordRole
    from bot.handlers.templates import get_template_async
    
    if len(args) < 2:
        raise ExecutionError("Usage: `@Bot addrule <invite_code> <role1,role2,...> [description]`")
    
    invite_code = args[0]
    role_names = args[1].split(',')
    description = ' '.join(args[2:]) if len(args) > 2 else ""
    
    # Validate roles exist
    roles_to_add = []
    for role_name in role_names:
        role_name = role_name.strip()
        discord_role = None
        
        for r in message.guild.roles:
            if r.name.lower() == role_name.lower():
                discord_role = r
                break
        
        if not discord_role:
            raise ExecutionError(f"Role not found: `{role_name}`")
        
        # Get or create in DB
        db_role, _ = await sync_to_async(DiscordRole.objects.get_or_create)(
            discord_id=discord_role.id,
            guild=guild_settings,
            defaults={'name': discord_role.name}
        )
        roles_to_add.append(db_role)
    
    # Create or update rule
    rule, created = await sync_to_async(InviteRule.objects.get_or_create)(
        guild=guild_settings,
        invite_code=invite_code,
        defaults={'description': description}
    )
    
    # Set roles
    await sync_to_async(rule.roles.set)(roles_to_add)
    
    role_str = ', '.join([r.name for r in roles_to_add])
    template = await get_template_async(guild_settings, 'COMMAND_SUCCESS')
    msg = template.format(message=f"Invite rule created: `{invite_code}` → {role_str}")
    await message.channel.send(msg)


async def handle_delete_invite_rule(bot, message, params, args, guild_settings):
    """DELETE_INVITE_RULE: Remove an invite rule"""
    from core.models import InviteRule
    from bot.handlers.templates import get_template_async
    
    if len(args) < 1:
        raise ExecutionError("Usage: `@Bot delrule <invite_code>`")
    
    invite_code = args[0]
    
    try:
        rule = await sync_to_async(InviteRule.objects.get)(
            guild=guild_settings,
            invite_code=invite_code
        )
        await sync_to_async(rule.delete)()
        template = await get_template_async(guild_settings, 'COMMAND_SUCCESS')
        msg = template.format(message=f"Invite rule deleted: `{invite_code}`")
        await message.channel.send(msg)
    except:
        raise ExecutionError(f"Rule not found: `{invite_code}`")


async def handle_list_invite_rules(bot, message, params, guild_settings):
    """LIST_INVITE_RULES: Show all invite rules"""
    from core.models import InviteRule
    
    rules = await sync_to_async(
        lambda: list(InviteRule.objects.filter(guild=guild_settings).prefetch_related('roles'))
    )()
    
    if not rules:
        await message.channel.send("📋 No rules configured yet.")
        return
    
    embed = discord.Embed(title="📋 Invite Rules", color=discord.Color.blue())
    
    for rule in rules:
        role_names = ', '.join([r.name for r in rule.roles.all()])
        value = f"**Roles:** {role_names if role_names else 'None'}"
        if rule.description:
            value += f"\n*{rule.description}*"
        
        embed.add_field(name=f"`{rule.invite_code}`", value=value, inline=False)
    
    await message.channel.send(embed=embed)


async def handle_set_server_mode(bot, message, params, args, guild_settings):
    """SET_SERVER_MODE: Change server from AUTO to APPROVAL"""
    from core.models import DiscordChannel
    from bot.handlers.guild_setup import get_or_create_channel
    from bot.handlers.templates import get_template_async
    
    if len(args) < 1:
        raise ExecutionError("Usage: `@Bot setmode <AUTO|APPROVAL>`")
    
    mode = args[0].upper()
    
    if mode not in ['AUTO', 'APPROVAL']:
        raise ExecutionError("Mode must be AUTO or APPROVAL")
    
    old_mode = guild_settings.mode
    guild_settings.mode = mode
    
    # If switching to APPROVAL mode, create approvals + pending channels
    if mode == 'APPROVAL':
        if not guild_settings.approvals_channel_id:
            admin_role = message.guild.get_role(guild_settings.bot_admin_role_id)
            if admin_role:
                approvals_channel = await get_or_create_channel(message.guild, "approvals", admin_role)
                guild_settings.approvals_channel_id = approvals_channel.id
                await sync_to_async(DiscordChannel.objects.update_or_create)(
                    discord_id=approvals_channel.id,
                    guild=guild_settings,
                    defaults={}
                )
        
        if not guild_settings.pending_channel_id:
            from bot.handlers.guild_setup import get_or_create_pending_channel
            pending_role = message.guild.get_role(guild_settings.pending_role_id)
            if pending_role:
                pending_channel = await get_or_create_pending_channel(message.guild, pending_role)
                guild_settings.pending_channel_id = pending_channel.id
                await sync_to_async(DiscordChannel.objects.update_or_create)(
                    discord_id=pending_channel.id,
                    guild=guild_settings,
                    defaults={}
                )
    
    await sync_to_async(guild_settings.save)()
    template = await get_template_async(guild_settings, 'COMMAND_SUCCESS')
    msg = template.format(message=f"Server mode changed from **{old_mode}** to **{mode}**")
    await message.channel.send(msg)


async def handle_list_commands(bot, message, params, guild_settings):
    """LIST_COMMANDS: Show all available commands"""
    from core.models import BotCommand
    
    commands = await sync_to_async(
        lambda: list(BotCommand.objects.filter(guild=guild_settings, enabled=True).order_by('name'))
    )()
    
    if not commands:
        await message.channel.send("📋 No commands configured.")
        return
    
    cmd_list = '\n'.join([f"• **{c.name}** - {c.description}" for c in commands])
    await message.channel.send(f"📋 **Available Commands:**\n{cmd_list}")


async def handle_generate_access_token(bot, message, params, guild_settings):
    """GENERATE_ACCESS_TOKEN: DM-only. Find guilds where user is BotAdmin, let them pick, generate token."""
    from core.models import AccessToken, GuildSettings
    from bot.handlers.templates import get_template_async
    import os

    # Must be used in DM only
    if message.guild is not None:
        await message.channel.send("⚠️ This command only works in DMs. Please send me a direct message!")
        return

    # Find all guilds where this user has the BotAdmin role
    all_guild_settings = await sync_to_async(
        lambda: list(GuildSettings.objects.filter(bot_admin_role_id__isnull=False))
    )()

    admin_guilds = []
    for gs in all_guild_settings:
        guild = bot.get_guild(gs.guild_id)
        if guild is None:
            continue
        member = guild.get_member(message.author.id)
        if member is None:
            continue
        # Check if member has the BotAdmin role
        if any(r.id == gs.bot_admin_role_id for r in member.roles):
            admin_guilds.append((guild, gs))

    if not admin_guilds:
        await message.author.send("⚠️ You are not a BotAdmin in any server I'm in.")
        return

    if len(admin_guilds) == 1:
        # Only one guild, use it directly
        selected_guild, selected_gs = admin_guilds[0]
    else:
        # Multiple guilds — ask user to pick
        guild_list = '\n'.join([f"**{i+1}.** {g.name}" for i, (g, _) in enumerate(admin_guilds)])
        await message.author.send(f"You are a BotAdmin in multiple servers. Reply with the number:\n{guild_list}")

        def check(m):
            return m.author.id == message.author.id and m.guild is None and m.content.isdigit()

        try:
            reply = await bot.wait_for('message', check=check, timeout=30.0)
            choice = int(reply.content)
            if choice < 1 or choice > len(admin_guilds):
                await message.author.send("❌ Invalid choice.")
                return
            selected_guild, selected_gs = admin_guilds[choice - 1]
        except Exception:
            await message.author.send("⏰ Timed out. Please try again.")
            return

    # Check for existing token
    existing = await sync_to_async(
        lambda: AccessToken.objects.filter(
            user_id=message.author.id,
            guild=selected_gs,
            expires_at__gt=timezone.now()
        ).first()
    )()

    app_url = os.environ.get('APP_URL', 'https://your-domain.com').rstrip('/')
    if not app_url.startswith(('http://', 'https://')):
        app_url = f'https://{app_url}'

    if existing:
        expires_str = existing.expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')
        access_url = f"{app_url}/auth/login/?token={existing.token}"
        await message.author.send(
            f"🔑 You already have an active token for **{selected_guild.name}**:\n"
            f"[Admin Panel]({access_url})\n"
            f"Expires: {expires_str}"
        )
        return

    # Create new token
    token = secrets.token_urlsafe(32)
    expires_at = timezone.now() + timedelta(hours=24)

    await sync_to_async(AccessToken.objects.create)(
        token=token,
        user_id=message.author.id,
        user_name=message.author.name,
        guild=selected_gs,
        expires_at=expires_at
    )

    expires_str = expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')
    access_url = f"{app_url}/auth/login/?token={token}"
    await message.author.send(
        f"🔑 Access token for **{selected_guild.name}**:\n"
        f"[Admin Panel]({access_url})\n"
        f"Expires: {expires_str}"
    )


async def handle_approve_application(bot, message, params, args, guild_settings):
    """APPROVE_APPLICATION: Approve a user and assign roles. Usage: @Bot approve @user role1,role2"""
    from core.models import Application, DiscordRole
    from bot.handlers.templates import get_template_async

    if not message.guild:
        raise ExecutionError("This command can only be used in a server.")

    if len(args) < 1:
        raise ExecutionError("Usage: `@Bot approve @user [role1,role2,...]`")

    # Parse mentioned user
    if not message.mentions:
        raise ExecutionError("Please mention the user to approve: `@Bot approve @user [role1,role2]`")

    target_user = message.mentions[0]
    member = message.guild.get_member(target_user.id)
    if not member:
        raise ExecutionError(f"User {target_user.name} is not in this server.")

    # Parse roles from args (second arg onwards, comma-separated)
    role_names = []
    if len(args) >= 2:
        role_names = [r.strip() for r in ' '.join(args[1:]).split(',') if r.strip()]

    # Find the pending application
    application = await sync_to_async(
        lambda: Application.objects.filter(
            guild=guild_settings,
            user_id=target_user.id,
            status='PENDING'
        ).order_by('-created_at').first()
    )()

    # Remove Pending role
    if guild_settings.pending_role_id:
        pending_role = message.guild.get_role(guild_settings.pending_role_id)
        if pending_role and pending_role in member.roles:
            await member.remove_roles(pending_role)

    # Assign requested roles
    assigned_roles = []
    for rname in role_names:
        role = discord.utils.get(message.guild.roles, name=rname)
        if role:
            await member.add_roles(role)
            assigned_roles.append(role.name)

    # Update application status
    if application:
        application.status = 'APPROVED'
        application.reviewed_by = message.author.id
        application.reviewed_at = timezone.now()
        await sync_to_async(application.save)()

    # Notify the user
    try:
        roles_str = ', '.join(assigned_roles) if assigned_roles else 'no specific roles'
        await target_user.send(
            f"✅ Your application in **{message.guild.name}** has been approved! "
            f"Roles assigned: {roles_str}"
        )
    except discord.Forbidden:
        pass  # Can't DM user

    roles_str = ', '.join(assigned_roles) if assigned_roles else 'none'
    await message.channel.send(
        f"✅ Approved **{target_user.display_name}**. Roles assigned: {roles_str}"
    )


async def handle_reject_application(bot, message, params, args, guild_settings):
    """REJECT_APPLICATION: Reject a user's application. Usage: @Bot reject @user [reason]"""
    from core.models import Application

    if not message.guild:
        raise ExecutionError("This command can only be used in a server.")

    if len(args) < 1:
        raise ExecutionError("Usage: `@Bot reject @user [reason]`")

    if not message.mentions:
        raise ExecutionError("Please mention the user to reject: `@Bot reject @user [reason]`")

    target_user = message.mentions[0]
    member = message.guild.get_member(target_user.id)

    reason = ' '.join(args[1:]) if len(args) > 1 else 'No reason provided'

    # Update application status
    application = await sync_to_async(
        lambda: Application.objects.filter(
            guild=guild_settings,
            user_id=target_user.id,
            status='PENDING'
        ).order_by('-created_at').first()
    )()

    if application:
        application.status = 'REJECTED'
        application.reviewed_by = message.author.id
        application.reviewed_at = timezone.now()
        await sync_to_async(application.save)()

    # Notify the user
    try:
        await target_user.send(
            f"❌ Your application in **{message.guild.name}** has been rejected.\n"
            f"Reason: {reason}"
        )
    except discord.Forbidden:
        pass

    # Optionally kick the user
    if member and params.get('kick_on_reject', False):
        try:
            await member.kick(reason=f"Application rejected: {reason}")
        except discord.Forbidden:
            pass

    await message.channel.send(
        f"❌ Rejected **{target_user.display_name}**. Reason: {reason}"
    )


async def handle_list_form_fields(bot, message, params, guild_settings):
    """LIST_FORM_FIELDS: Show all form fields"""
    from core.models import FormField
    
    fields = await sync_to_async(
        lambda: list(FormField.objects.filter(guild=guild_settings).order_by('order'))
    )()
    
    if not fields:
        await message.channel.send("📋 No form fields configured yet.")
        return
    
    embed = discord.Embed(title="📋 Application Form Fields", color=discord.Color.blue())
    
    for field in fields:
        required_str = "✅ Required" if field.required else "⭕ Optional"
        embed.add_field(
            name=f"{field.label}",
            value=f"Type: `{field.field_type}` • {required_str}",
            inline=False
        )
    
    await message.channel.send(embed=embed)


async def handle_reload_config(bot, message, params, guild_settings):
    """RELOAD_CONFIG: Sync roles and channels with Discord"""
    from core.models import DiscordRole, DiscordChannel
    from bot.handlers.templates import get_template_async
    
    # Sync all roles
    roles = message.guild.roles
    for role in roles:
        await sync_to_async(DiscordRole.objects.update_or_create)(
            discord_id=role.id,
            guild=guild_settings,
            defaults={'name': role.name}
        )
    
    # Sync all channels
    channels = message.guild.text_channels
    for channel in channels:
        await sync_to_async(DiscordChannel.objects.update_or_create)(
            discord_id=channel.id,
            guild=guild_settings,
            defaults={}
        )
    
    template = await get_template_async(guild_settings, 'COMMAND_SUCCESS')
    msg = template.format(message=f"Reloaded configuration ({len(roles)} roles, {len(channels)} channels)")
    await message.channel.send(msg)
