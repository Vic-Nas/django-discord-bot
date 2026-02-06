from handlers.sync import sync_guild_data


async def cmd_reload(bot, message, args, guild_settings, invite_cache):
    """
    Reload/sync roles and channels from Discord
    Usage: @Bot reload
    """
    
    await message.channel.send("🔄 Syncing data with Discord...")
    
    report = await sync_guild_data(bot, guild_settings.guild_id)
    
    await message.channel.send(report)
