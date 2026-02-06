import discord
from handlers.templates import get_template_async
from handlers.guild_setup import get_or_create_channel
from core.models import DiscordChannel
from asgiref.sync import sync_to_async


async def cmd_setmode(bot, message, args, guild_settings, invite_cache):
    """
    Set server mode
    Usage: @Bot setmode <AUTO|APPROVAL>
    """
    
    if len(args) < 1:
        await message.channel.send("❌ Usage: `@Bot setmode <AUTO|APPROVAL>`")
        return
    
    mode = args[0].upper()
    
    if mode not in ['AUTO', 'APPROVAL']:
        await message.channel.send("❌ Mode must be AUTO or APPROVAL")
        return
    
    old_mode = guild_settings.mode
    guild_settings.mode = mode
    
    # If switching to APPROVAL mode, create approvals channel
    if mode == 'APPROVAL' and not guild_settings.approvals_channel_id:
        admin_role = message.guild.get_role(guild_settings.bot_admin_role_id)
        
        if admin_role:
            approvals_channel = await get_or_create_channel(message.guild, "approvals", admin_role)
            guild_settings.approvals_channel_id = approvals_channel.id
            
            # Cache in DB
            await sync_to_async(DiscordChannel.objects.update_or_create)(
                discord_id=approvals_channel.id,
                guild=guild_settings,
                defaults={}
            )
    
    await sync_to_async(guild_settings.save)()
    
    template = await get_template_async(guild_settings, 'COMMAND_SUCCESS')
    msg = template.format(
        message=f"Server mode changed from **{old_mode}** to **{mode}**"
    )
    
    if mode == 'APPROVAL' and guild_settings.approvals_channel_id:
        channel = message.guild.get_channel(guild_settings.approvals_channel_id)
        if channel:
            msg += f"\n\nApplications will be posted to {channel.mention}"
    
    await message.channel.send(msg)
