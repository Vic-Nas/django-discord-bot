import discord
from core.models import InviteRule


async def cmd_listrules(bot, message, args, guild_settings, invite_cache):
    """List all invite rules"""
    
    rules = InviteRule.objects.filter(guild=guild_settings).prefetch_related('roles')
    
    if not rules.exists():
        await message.channel.send("📋 No rules configured yet.")
        return
    
    embed = discord.Embed(
        title="📋 Invite Rules",
        color=discord.Color.blue()
    )
    
    for rule in rules:
        role_names = ', '.join([r.name for r in rule.roles.filter(is_deleted=False)])
        deleted_roles = rule.roles.filter(is_deleted=True).count()
        
        value = f"**Roles:** {role_names if role_names else 'None'}"
        
        if deleted_roles > 0:
            value += f"\n⚠️ {deleted_roles} deleted role(s)"
        
        if rule.description:
            value += f"\n*{rule.description}*"
        
        embed.add_field(
            name=f"`{rule.invite_code}`",
            value=value,
            inline=False
        )
    
    await message.channel.send(embed=embed)
