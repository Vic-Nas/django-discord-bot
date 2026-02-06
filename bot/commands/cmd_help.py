import discord
from handlers.templates import get_template_async


async def cmd_help(bot, message, args, guild_settings, invite_cache):
    """Show available commands"""
    
    from . import command_registry
    
    # Get commands available to this user
    commands = command_registry.get_commands_for_user(guild_settings, message.author.roles)
    
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
