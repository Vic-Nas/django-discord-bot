import discord
from core.models import GuildSettings, DiscordRole, DiscordChannel
from .templates import get_template_async
from asgiref.sync import sync_to_async


async def setup_guild(bot, guild):
    """
    Setup guild when bot joins:
    1. Create BotAdmin role
    2. Create Pending role
    3. Create #logs channel
    4. Send welcome message
    5. Save to database
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
        defaults={'name': bot_admin_role.name, 'is_deleted': False}
    )
    
    # Create Pending role
    pending_role = await get_or_create_role(guild, "Pending", color=discord.Color.orange())
    guild_settings.pending_role_id = pending_role.id
    
    # Cache role in DB
    await sync_to_async(DiscordRole.objects.update_or_create)(
        discord_id=pending_role.id,
        guild=guild_settings,
        defaults={'name': pending_role.name, 'is_deleted': False}
    )
    
    # Create #logs channel
    logs_channel = await get_or_create_channel(guild, "logs", bot_admin_role)
    guild_settings.logs_channel_id = logs_channel.id
    
    # Cache channel in DB
    await sync_to_async(DiscordChannel.objects.update_or_create)(
        discord_id=logs_channel.id,
        guild=guild_settings,
        defaults={'name': logs_channel.name, 'is_deleted': False}
    )
    
    await sync_to_async(guild_settings.save)()
    
    # Send welcome message to logs
    template = await get_template_async(guild_settings, 'INSTALL_WELCOME')
    message = template.format(
        bot_admin=bot_admin_role.mention,
        pending=pending_role.mention,
        logs=logs_channel.mention,
        bot_mention=bot.user.mention
    )
    
    await logs_channel.send(message)
    
    print(f'✅ Setup complete for {guild.name}')


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
        # Update permissions to ensure bot can send messages
        try:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                admin_role: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            await channel.edit(overwrites=overwrites)
        except Exception as e:
            print(f'⚠️ Could not update permissions for {name}: {e}')
        return channel
    
    # Create channel with permissions
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        admin_role: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    
    channel = await guild.create_text_channel(name, overwrites=overwrites)
    return channel


async def ensure_required_resources(bot, guild_settings):
    """
    Ensure required roles/channels exist.
    Called when needed (e.g., before role assignment).
    Recreates if deleted.
    """
    guild = bot.get_guild(guild_settings.guild_id)
    if not guild:
        return
    
    # Check BotAdmin role
    if guild_settings.bot_admin_role_id:
        role = guild.get_role(guild_settings.bot_admin_role_id)
        if not role:
            # Recreate
            role = await get_or_create_role(guild, "BotAdmin", color=discord.Color.blue())
            guild_settings.bot_admin_role_id = role.id
            await sync_to_async(guild_settings.save)()
            
            await sync_to_async(DiscordRole.objects.update_or_create)(
                discord_id=role.id,
                guild=guild_settings,
                defaults={'name': role.name, 'is_deleted': False}
            )
    
    # Check Pending role
    if guild_settings.pending_role_id:
        role = guild.get_role(guild_settings.pending_role_id)
        if not role:
            role = await get_or_create_role(guild, "Pending", color=discord.Color.orange())
            guild_settings.pending_role_id = role.id
            await sync_to_async(guild_settings.save)()
            
            await sync_to_async(DiscordRole.objects.update_or_create)(
                discord_id=role.id,
                guild=guild_settings,
                defaults={'name': role.name, 'is_deleted': False}
            )
    
    # Check logs channel
    if guild_settings.logs_channel_id:
        channel = guild.get_channel(guild_settings.logs_channel_id)
        if not channel:
            admin_role = guild.get_role(guild_settings.bot_admin_role_id)
            channel = await get_or_create_channel(guild, "logs", admin_role)
            guild_settings.logs_channel_id = channel.id
            await sync_to_async(guild_settings.save)()
            
            await sync_to_async(DiscordChannel.objects.update_or_create)(
                discord_id=channel.id,
                guild=guild_settings,
                defaults={'name': channel.name, 'is_deleted': False}
            )
    
    # Check approvals channel if in APPROVAL mode
    if guild_settings.mode == 'APPROVAL' and guild_settings.approvals_channel_id:
        channel = guild.get_channel(guild_settings.approvals_channel_id)
        if not channel:
            admin_role = guild.get_role(guild_settings.bot_admin_role_id)
            channel = await get_or_create_channel(guild, "approvals", admin_role)
            guild_settings.approvals_channel_id = channel.id
            await sync_to_async(guild_settings.save)()
            
            await sync_to_async(DiscordChannel.objects.update_or_create)(
                discord_id=channel.id,
                guild=guild_settings,
                defaults={'name': channel.name, 'is_deleted': False}
            )
