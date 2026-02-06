import discord
from handlers.templates import get_template_async
from asgiref.sync import sync_to_async


async def cmd_help(bot, message, args, guild_settings, invite_cache):
    """Show available commands"""
    
    from . import command_registry
    
    # Get user roles (if in guild, else empty list for DM)
    user_roles = message.author.roles if hasattr(message.author, 'roles') else []
    
    # Get commands available to this user (wrap in sync_to_async)
    commands = await sync_to_async(command_registry.get_commands_for_user)(guild_settings, user_roles)
    
    if not commands:
        await message.channel.send("❌ No commands available.")
        return
    
    # Build command list
    cmd_list = []
    for cmd in commands:
        line = f"**{cmd['name']}** - {cmd['description']}"
        if cmd['admin_only']:
            line += " 🔒"
        cmd_list.append(line)
    
    commands_text = "\n".join(cmd_list)
    
    # Use template if in guild, else use simple format for DM
    if guild_settings:
        template = await get_template_async(guild_settings, 'HELP_MESSAGE')
        message_text = template.format(
            commands=commands_text,
            bot_mention=bot.user.mention
        )
        
        embed = discord.Embed(
            title="🤖 Bot Commands",
            description=message_text,
            color=discord.Color.blue()
        )
        
        await message.channel.send(embed=embed)
    else:
        # DM context - simple message
        msg = f"🤖 **Bot Commands**\n\n{commands_text}\n\n💡 Use `@{bot.user.name} <command>` to run commands"
        await message.channel.send(msg)
