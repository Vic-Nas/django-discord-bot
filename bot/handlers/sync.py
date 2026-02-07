import discord
from core.models import GuildSettings, DiscordRole, DiscordChannel
from asgiref.sync import sync_to_async


async def sync_guild_data(bot, guild_id):
    """
    Sync Discord roles/channels with database.
    - Update names for roles
    - Remove stale DB entries for deleted Discord resources
    """
    
    try:
        guild_settings = await sync_to_async(GuildSettings.objects.get)(guild_id=guild_id)
    except GuildSettings.DoesNotExist:
        return "❌ Guild not found in database"
    
    guild = bot.get_guild(guild_id)
    if not guild:
        return "❌ Guild not found on Discord"
    
    # Update guild name
    guild_settings.guild_name = guild.name
    await sync_to_async(guild_settings.save)()
    
    # Sync roles
    roles_synced = 0
    roles_removed = 0
    
    discord_role_ids = {role.id for role in guild.roles}
    db_roles = await sync_to_async(lambda: list(DiscordRole.objects.filter(guild=guild_settings)))()
    
    for db_role in db_roles:
        if db_role.discord_id in discord_role_ids:
            # Update name
            discord_role = guild.get_role(db_role.discord_id)
            if discord_role and db_role.name != discord_role.name:
                db_role.name = discord_role.name
                await sync_to_async(db_role.save)()
            roles_synced += 1
        else:
            # Role was deleted on Discord — remove from DB
            await sync_to_async(db_role.delete)()
            roles_removed += 1
    
    # Add new roles not yet in DB
    roles_added = 0
    for role in guild.roles:
        if role.is_default():
            continue
        exists = await sync_to_async(
            lambda r=role: DiscordRole.objects.filter(discord_id=r.id, guild=guild_settings).exists()
        )()
        if not exists:
            await sync_to_async(DiscordRole.objects.create)(
                discord_id=role.id,
                guild=guild_settings,
                name=role.name
            )
            roles_added += 1
    
    # Sync channels
    channels_synced = 0
    channels_removed = 0
    
    discord_channel_ids = {channel.id for channel in guild.channels}
    db_channels = await sync_to_async(lambda: list(DiscordChannel.objects.filter(guild=guild_settings)))()
    
    for db_channel in db_channels:
        if db_channel.discord_id in discord_channel_ids:
            channels_synced += 1
        else:
            # Channel was deleted on Discord — remove from DB
            await sync_to_async(db_channel.delete)()
            channels_removed += 1
    
    # Add new channels not yet in DB
    channels_added = 0
    for channel in guild.text_channels:
        exists = await sync_to_async(
            lambda c=channel: DiscordChannel.objects.filter(discord_id=c.id, guild=guild_settings).exists()
        )()
        if not exists:
            await sync_to_async(DiscordChannel.objects.create)(
                discord_id=channel.id,
                guild=guild_settings
            )
            channels_added += 1
    
    # Build report
    report = f"""✅ **Sync Complete**

**Roles:**
- Synced: {roles_synced}
- Added: {roles_added}
- Removed (deleted on Discord): {roles_removed}

**Channels:**
- Synced: {channels_synced}
- Added: {channels_added}
- Removed (deleted on Discord): {channels_removed}
"""
    
    return report
