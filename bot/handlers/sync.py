import discord
from core.models import GuildSettings, DiscordRole, DiscordChannel


async def sync_guild_data(bot, guild_id):
    """
    Sync Discord roles/channels with database.
    - Update names
    - Mark deleted items
    - Don't delete anything from DB
    """
    
    try:
        guild_settings = GuildSettings.objects.get(guild_id=guild_id)
    except GuildSettings.DoesNotExist:
        return "❌ Guild not found in database"
    
    guild = bot.get_guild(guild_id)
    if not guild:
        return "❌ Guild not found on Discord"
    
    # Update guild name
    guild_settings.guild_name = guild.name
    guild_settings.save()
    
    # Sync roles
    roles_synced = 0
    roles_marked_deleted = 0
    
    discord_role_ids = {role.id for role in guild.roles}
    db_roles = DiscordRole.objects.filter(guild=guild_settings)
    
    for db_role in db_roles:
        if db_role.discord_id in discord_role_ids:
            # Update name
            discord_role = guild.get_role(db_role.discord_id)
            if discord_role:
                db_role.name = discord_role.name
                db_role.is_deleted = False
                db_role.save()
                roles_synced += 1
        else:
            # Mark as deleted
            if not db_role.is_deleted:
                db_role.is_deleted = True
                db_role.save()
                roles_marked_deleted += 1
    
    # Sync channels
    channels_synced = 0
    channels_marked_deleted = 0
    
    discord_channel_ids = {channel.id for channel in guild.channels}
    db_channels = DiscordChannel.objects.filter(guild=guild_settings)
    
    for db_channel in db_channels:
        if db_channel.discord_id in discord_channel_ids:
            # Update name
            discord_channel = guild.get_channel(db_channel.discord_id)
            if discord_channel:
                db_channel.name = discord_channel.name
                db_channel.is_deleted = False
                db_channel.save()
                channels_synced += 1
        else:
            # Mark as deleted
            if not db_channel.is_deleted:
                db_channel.is_deleted = True
                db_channel.save()
                channels_marked_deleted += 1
    
    # Build report
    report = f"""✅ **Sync Complete**

**Roles:**
- Updated: {roles_synced}
- Marked as deleted: {roles_marked_deleted}

**Channels:**
- Updated: {channels_synced}
- Marked as deleted: {channels_marked_deleted}
"""
    
    if roles_marked_deleted > 0 or channels_marked_deleted > 0:
        report += "\n⚠️ Some resources were marked as deleted. Check the admin panel to resolve conflicts."
    
    return report
