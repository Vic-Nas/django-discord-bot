import discord
from core.models import GuildSettings, DiscordRole, DiscordChannel, BotCommand, CommandAction
from .templates import get_template_async
from asgiref.sync import sync_to_async


async def setup_guild(bot, guild):
    """
    Setup guild when bot joins:
    1. Create BotAdmin role
    2. Create Pending role
    3. Create #logs channel
    4. Create all 9 default commands with actions
    5. Save to database
    
    NOTE: This is called automatically when bot joins (on_guild_join event).
    If bot already exists in guild, manually run:
      python manage.py init_defaults --guild_id YOUR_GUILD_ID
    """
    
    # Get or create guild settings
    guild_settings, created = await sync_to_async(GuildSettings.objects.get_or_create)(
        guild_id=guild.id,
        defaults={'guild_name': guild.name}
    )
    
    if not created:
        # Update guild name in case it changed
        guild_settings.guild_name = guild.name
        await sync_to_async(guild_settings.save)()
    
    # Create BotAdmin role
    bot_admin_role = await get_or_create_role(guild, "BotAdmin", color=discord.Color.blue())
    guild_settings.bot_admin_role_id = bot_admin_role.id
    
    # Cache role in DB
    await sync_to_async(DiscordRole.objects.update_or_create)(
        discord_id=bot_admin_role.id,
        guild=guild_settings,
        defaults={'name': bot_admin_role.name}
    )
    
    # Create Pending role
    pending_role = await get_or_create_role(guild, "Pending", color=discord.Color.orange())
    guild_settings.pending_role_id = pending_role.id
    
    # Cache role in DB
    await sync_to_async(DiscordRole.objects.update_or_create)(
        discord_id=pending_role.id,
        guild=guild_settings,
        defaults={'name': pending_role.name}
    )
    
    # Assign BotAdmin role to bot itself
    assignment_failed = False
    try:
        await guild.me.add_roles(bot_admin_role)
        print(f"✅ Assigned BotAdmin role to bot in {guild.name}")
    except Exception as e:
        assignment_failed = True
        print(f"❌ Failed to assign BotAdmin role to bot in {guild.name}: {e}")
        print(f"   Bot permissions: {guild.me.guild_permissions}")
    
    # Create #bounce channel (private, BotAdmin only)
    bounce_channel = await get_or_create_channel(guild, "bounce", bot_admin_role)
    guild_settings.logs_channel_id = bounce_channel.id
    
    # Cache channel in DB
    await sync_to_async(DiscordChannel.objects.update_or_create)(
        discord_id=bounce_channel.id,
        guild=guild_settings,
        defaults={}
    )
    
    # Create #approvals channel (private, BotAdmin only)
    approvals_channel = await get_or_create_channel(guild, "approvals", bot_admin_role)
    guild_settings.approvals_channel_id = approvals_channel.id
    
    await sync_to_async(DiscordChannel.objects.update_or_create)(
        discord_id=approvals_channel.id,
        guild=guild_settings,
        defaults={}
    )
    
    # Create #pending channel (visible ONLY to Pending role + bot)
    pending_channel = await get_or_create_pending_channel(guild, pending_role)
    guild_settings.pending_channel_id = pending_channel.id
    
    await sync_to_async(DiscordChannel.objects.update_or_create)(
        discord_id=pending_channel.id,
        guild=guild_settings,
        defaults={}
    )
    
    # Restrict Pending role from seeing all other channels
    await restrict_pending_role(guild, pending_role)
    
    await sync_to_async(guild_settings.save)()
    
    # Create default commands for this server with real actions (not placeholders)
    default_commands = [
        {
            'name': 'help',
            'description': 'Show available commands and how to use them',
            'actions': [
                {'type': 'LIST_COMMANDS', 'name': 'show_commands', 'parameters': {}},
            ]
        },
        {
            'name': 'getaccess',
            'description': 'Get a temporary access link to the web panel',
            'actions': [
                {'type': 'GENERATE_ACCESS_TOKEN', 'name': 'create_token', 'parameters': {}},
            ]
        },
        {
            'name': 'addrule',
            'description': 'Add an invite rule (Admin only)',
            'actions': [
                {'type': 'ADD_INVITE_RULE', 'name': 'add_rule', 'parameters': {}},
            ]
        },
        {
            'name': 'delrule',
            'description': 'Delete an invite rule (Admin only)',
            'actions': [
                {'type': 'DELETE_INVITE_RULE', 'name': 'delete_rule', 'parameters': {}},
            ]
        },
        {
            'name': 'listrules',
            'description': 'List all invite rules for this server',
            'actions': [
                {'type': 'LIST_INVITE_RULES', 'name': 'show_rules', 'parameters': {}},
            ]
        },
        {
            'name': 'setmode',
            'description': 'Set server mode: AUTO or APPROVAL (Admin only)',
            'actions': [
                {'type': 'SET_SERVER_MODE', 'name': 'change_mode', 'parameters': {}},
            ]
        },
        {
            'name': 'listfields',
            'description': 'List form fields for applications',
            'actions': [
                {'type': 'LIST_FORM_FIELDS', 'name': 'show_fields', 'parameters': {}},
            ]
        },
        {
            'name': 'reload',
            'description': 'Reload bot configuration (Admin only)',
            'actions': [
                {'type': 'RELOAD_CONFIG', 'name': 'reload_config', 'parameters': {}},
            ]
        },
        {
            'name': 'approve',
            'description': 'Approve a pending member (Admin only)',
            'actions': [
                {'type': 'APPROVE_APPLICATION', 'name': 'approve_member', 'parameters': {}},
            ]
        },
        {
            'name': 'reject',
            'description': 'Reject a pending member (Admin only)',
            'actions': [
                {'type': 'REJECT_APPLICATION', 'name': 'reject_member', 'parameters': {}},
            ]
        },
    ]
    
    for cmd in default_commands:
        bot_cmd, _ = await sync_to_async(BotCommand.objects.get_or_create)(
            guild=guild_settings,
            name=cmd['name'],
            defaults={'description': cmd['description'], 'enabled': True}
        )
        
        # Create default actions for this command
        for action_order, action in enumerate(cmd.get('actions', []), start=1):
            await sync_to_async(CommandAction.objects.get_or_create)(
                command=bot_cmd,
                name=action['name'],
                defaults={
                    'order': action_order,
                    'type': action['type'],
                    'parameters': action['parameters'],
                    'enabled': True
                }
            )
    
    print(f"✅ Created {len(default_commands)} default commands with actions for {guild.name}")
    if assignment_failed:
        try:
            bot_role = guild.me.top_role
            bot_role_name = bot_role.name if bot_role.name != "@everyone" else "(no assigned role)"
            
            diagnostic_msg = (
                f"⚠️ **Setup Issue Detected**\n\n"
                f"I couldn't assign the BotAdmin role to myself. My role is: **{bot_role_name}**\n\n"
                f"**Possible fixes:**\n"
                f"1. **Role Hierarchy**: In Server Settings → Roles, make sure my role (**{bot_role_name}**) is positioned **above** BotAdmin in the hierarchy\n"
                f"2. **Permissions**: Make sure I have the \"Manage Roles\" permission\n"
                f"3. **Re-add the bot**: Kick me from the server and add me back (this might trigger a fresh setup)\n\n"
                f"I need this to manage BotAdmin role assignments and channel permissions."
            )
            await bounce_channel.send(diagnostic_msg)
        except Exception:
            # Fallback to general channel
            try:
                general = discord.utils.get(guild.text_channels, name='general')
                if general:
                    bot_role = guild.me.top_role
                    bot_role_name = bot_role.name if bot_role.name != "@everyone" else "(no assigned role)"
                    diagnostic_msg = (
                        f"⚠️ **Setup Issue Detected**\n\n"
                        f"I couldn't assign the BotAdmin role to myself. My role is: **{bot_role_name}**\n\n"
                        f"**Possible fixes:**\n"
                        f"1. **Role Hierarchy**: In Server Settings → Roles, make sure my role (**{bot_role_name}**) is positioned **above** BotAdmin in the hierarchy\n"
                        f"2. **Permissions**: Make sure I have the \"Manage Roles\" permission\n"
                        f"3. **Re-add the bot**: Kick me from the server and add me back (this might trigger a fresh setup)\n\n"
                        f"I need this to manage BotAdmin role assignments and channel permissions."
                    )
                    await general.send(diagnostic_msg)
            except Exception:
                print(f"Could not send diagnostic message to any channel")
    
    # Send welcome message to bounce channel
    try:
        # Ensure channel is accessible
        if bounce_channel:
            template = await get_template_async(guild_settings, 'INSTALL_WELCOME')
            message = template.format(
                bot_admin=bot_admin_role.mention,
                pending=pending_role.mention,
                logs=bounce_channel.mention,
                bot_mention=bot.user.mention
            )
            await bounce_channel.send(message)
    except Exception as e:
        print(f"Failed to send welcome message: {e}")


async def get_or_create_pending_channel(guild, pending_role):
    """Create #pending channel visible ONLY to Pending role and bot"""
    channel = discord.utils.get(guild.text_channels, name='pending')
    
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        pending_role: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    
    if channel:
        try:
            await channel.edit(overwrites=overwrites)
        except Exception:
            pass
        return channel
    
    try:
        channel = await guild.create_text_channel('pending', overwrites=overwrites)
    except Exception:
        channel = await guild.create_text_channel('pending')
    
    return channel


async def restrict_pending_role(guild, pending_role):
    """Prevent Pending role from seeing all channels except #pending"""
    for channel in guild.text_channels:
        if channel.name == 'pending':
            continue  # Skip #pending channel
        try:
            await channel.set_permissions(
                pending_role,
                read_messages=False
            )
        except Exception:
            pass  # Skip channels we can't modify


async def get_or_create_role(guild, name, **kwargs):
    """Get existing role or create new one"""
    # Check if role exists
    role = discord.utils.get(guild.roles, name=name)
    
    if role:
        return role
    
    # Create new role
    role = await guild.create_role(name=name, **kwargs)
    return role


async def get_or_create_channel(guild, name, admin_role):
    """Get existing channel or create new one with proper permissions"""
    # Check if channel exists
    channel = discord.utils.get(guild.text_channels, name=name)
    
    if channel:
        # Try to update permissions if bot has Manage Channels permission
        try:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                admin_role: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            await channel.edit(overwrites=overwrites)
        except Exception:
            pass
        return channel
    
    # Create channel with permissions
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        admin_role: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    
    try:
        channel = await guild.create_text_channel(name, overwrites=overwrites)
    except Exception:
        # If creation fails, try without overwrites
        channel = await guild.create_text_channel(name)
    
    return channel


async def ensure_required_resources(bot, guild_settings):
    """
    Ensure required roles/channels exist.
    Called when needed (e.g., before role assignment).
    Creates if missing or if ID was never set.
    """
    guild = bot.get_guild(guild_settings.guild_id)
    if not guild:
        return
    
    changed = False
    
    # Check BotAdmin role
    bot_admin_role = None
    if guild_settings.bot_admin_role_id:
        bot_admin_role = guild.get_role(guild_settings.bot_admin_role_id)
    if not bot_admin_role:
        bot_admin_role = await get_or_create_role(guild, "BotAdmin", color=discord.Color.blue())
        guild_settings.bot_admin_role_id = bot_admin_role.id
        changed = True
        await sync_to_async(DiscordRole.objects.update_or_create)(
            discord_id=bot_admin_role.id,
            guild=guild_settings,
            defaults={'name': bot_admin_role.name}
        )
    
    # Check Pending role
    pending_role = None
    if guild_settings.pending_role_id:
        pending_role = guild.get_role(guild_settings.pending_role_id)
    if not pending_role:
        pending_role = await get_or_create_role(guild, "Pending", color=discord.Color.orange())
        guild_settings.pending_role_id = pending_role.id
        changed = True
        await sync_to_async(DiscordRole.objects.update_or_create)(
            discord_id=pending_role.id,
            guild=guild_settings,
            defaults={'name': pending_role.name}
        )
    
    # Check bounce channel
    bounce_channel = None
    if guild_settings.logs_channel_id:
        bounce_channel = guild.get_channel(guild_settings.logs_channel_id)
    if not bounce_channel:
        bounce_channel = await get_or_create_channel(guild, "bounce", bot_admin_role)
        guild_settings.logs_channel_id = bounce_channel.id
        changed = True
        await sync_to_async(DiscordChannel.objects.update_or_create)(
            discord_id=bounce_channel.id,
            guild=guild_settings,
            defaults={}
        )
    
    # Check approvals channel — always ensure it exists
    approvals_channel = None
    if guild_settings.approvals_channel_id:
        approvals_channel = guild.get_channel(guild_settings.approvals_channel_id)
    if not approvals_channel:
        approvals_channel = await get_or_create_channel(guild, "approvals", bot_admin_role)
        guild_settings.approvals_channel_id = approvals_channel.id
        changed = True
        await sync_to_async(DiscordChannel.objects.update_or_create)(
            discord_id=approvals_channel.id,
            guild=guild_settings,
            defaults={}
        )
    
    # Check pending channel — always ensure it exists
    pending_channel = None
    if guild_settings.pending_channel_id:
        pending_channel = guild.get_channel(guild_settings.pending_channel_id)
    if not pending_channel:
        pending_channel = await get_or_create_pending_channel(guild, pending_role)
        guild_settings.pending_channel_id = pending_channel.id
        changed = True
        await sync_to_async(DiscordChannel.objects.update_or_create)(
            discord_id=pending_channel.id,
            guild=guild_settings,
            defaults={}
        )
    
    if changed:
        await sync_to_async(guild_settings.save)()
