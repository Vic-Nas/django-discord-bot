from core.models import InviteRule
from handlers.templates import get_template_async
from asgiref.sync import sync_to_async


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
        rule = await sync_to_async(InviteRule.objects.get)(guild=guild_settings, invite_code=invite_code)
        await sync_to_async(rule.delete)()
        
        template = await get_template_async(guild_settings, 'COMMAND_SUCCESS')
        msg = template.format(message=f"Rule `{invite_code}` deleted!")
        await message.channel.send(msg)
        
    except InviteRule.DoesNotExist:
        await message.channel.send(f"❌ No rule found for invite code `{invite_code}`")
