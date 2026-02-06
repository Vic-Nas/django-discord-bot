import os
from django.utils import timezone
from datetime import timedelta
from core.models import AccessToken, GuildSettings
from handlers.templates import get_template_async
from asgiref.sync import sync_to_async


async def cmd_getaccess(bot, message, args, guild_settings, invite_cache):
    """
    Get web panel access token (DM only)
    Usage: @Bot getaccess (in DM)
    """
    
    # Must be in DM
    if message.guild:
        await message.channel.send("❌ This command only works in DMs. Please send me a direct message!")
        return
    
    # Get all guilds where user has BotAdmin role
    user_guilds = []
    
    for guild in bot.guilds:
        member = guild.get_member(message.author.id)
        if not member:
            continue
        
        try:
            settings = await sync_to_async(GuildSettings.objects.get)(guild_id=guild.id)
            if settings.bot_admin_role_id:
                admin_role = guild.get_role(settings.bot_admin_role_id)
                if admin_role and admin_role in member.roles:
                    user_guilds.append({'guild': guild, 'settings': settings})
        except GuildSettings.DoesNotExist:
            continue
    
    if not user_guilds:
        await message.channel.send("❌ You don't have BotAdmin role in any server with this bot.")
        return
    
    # If only one guild, use it
    if len(user_guilds) == 1:
        selected_guild = user_guilds[0]
    else:
        # Ask user to choose
        guild_list = "\n".join([f"{i+1}. {g['guild'].name}" for i, g in enumerate(user_guilds)])
        await message.channel.send(f"**Select a server:**\n{guild_list}\n\nReply with the number.")
        
        def check(m):
            return m.author == message.author and m.channel == message.channel
        
        try:
            response = await bot.wait_for('message', check=check, timeout=30)
            choice = int(response.content) - 1
            
            if choice < 0 or choice >= len(user_guilds):
                await message.channel.send("❌ Invalid selection.")
                return
            
            selected_guild = user_guilds[choice]
        except:
            await message.channel.send("❌ Selection timed out.")
            return
    
    guild_settings = selected_guild['settings']
    
    # Check for existing valid token
    existing_token = await sync_to_async(lambda: AccessToken.objects.filter(
        user_id=message.author.id,
        guild=guild_settings,
        expires_at__gt=timezone.now()
    ).first())()
    
    if existing_token:
        # Return existing token
        app_url = os.getenv('APP_URL', 'http://localhost:8000')
        if not app_url.startswith(('http://', 'https://')):
            app_url = f"https://{app_url}"
        url = f"{app_url}/auth/login/?token={existing_token.token}"
        url_link = f"[Admin Panel]({url})"
        
        template = await get_template_async(guild_settings, 'GETACCESS_EXISTS')
        msg = template.format(
            url=url_link,
            expires=existing_token.expires_at.strftime('%Y-%m-%d %H:%M UTC')
        )
        
        await message.channel.send(msg)
        return
    
    # Create new token
    expires = timezone.now() + timedelta(hours=24)
    
    token = await sync_to_async(AccessToken.objects.create)(
        user_id=message.author.id,
        user_name=str(message.author),
        guild=guild_settings,
        expires_at=expires
    )
    
    app_url = os.getenv('APP_URL', 'http://localhost:8000')
    if not app_url.startswith(('http://', 'https://')):
        app_url = f"https://{app_url}"
    url = f"{app_url}/auth/login/?token={token.token}"
    url_link = f"[Admin Panel]({url})"
    
    template = await get_template_async(guild_settings, 'GETACCESS_RESPONSE')
    msg = template.format(
        url=url_link,
        expires=expires.strftime('%Y-%m-%d %H:%M UTC')
    )
    
    await message.channel.send(msg)
