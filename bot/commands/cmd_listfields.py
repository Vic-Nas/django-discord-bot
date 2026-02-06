import discord
from core.models import FormField


async def cmd_listfields(bot, message, args, guild_settings, invite_cache):
    """List all form fields"""
    
    fields = FormField.objects.filter(guild=guild_settings).order_by('order')
    
    if not fields.exists():
        await message.channel.send("📋 No form fields configured yet.")
        return
    
    embed = discord.Embed(
        title="📋 Application Form Fields",
        description="Fields shown to users in APPROVAL mode:",
        color=discord.Color.blue()
    )
    
    for field in fields:
        value = f"**Type:** {field.field_type}\n**Required:** {'Yes' if field.required else 'No'}"
        
        if field.options:
            value += f"\n**Options:** {', '.join(field.options)}"
        
        embed.add_field(
            name=f"{field.order + 1}. {field.label}",
            value=value,
            inline=False
        )
    
    await message.channel.send(embed=embed)
