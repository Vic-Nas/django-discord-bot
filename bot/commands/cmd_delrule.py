from core.models import InviteRule
from handlers.templates import get_template


async def cmd_delrule(bot, message, args, guild_settings, invite_cache):
    """
    Delete invite rule
    Usage: @Bot delrule <invite_code>
    """
    
    if len(args) < 1:
        await message.channel.send("❌ Usage: `@Bot delrule <invite_code>`")
        return
    
    invite_code = args[0]
    
    try:
        rule = InviteRule.objects.get(guild=guild_settings, invite_code=invite_code)
        rule.delete()
        
        template = get_template(guild_settings, 'COMMAND_SUCCESS')
        msg = template.format(message=f"Rule `{invite_code}` deleted!")
        await message.channel.send(msg)
        
    except InviteRule.DoesNotExist:
        await message.channel.send(f"❌ No rule found for invite code `{invite_code}`")
