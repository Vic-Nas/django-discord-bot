from core.models import InviteRule, DiscordRole
from handlers.templates import get_template


async def cmd_addrule(bot, message, args, guild_settings, invite_cache):
    """
    Add invite rule
    Usage: @Bot addrule <invite_code> <role1,role2,...> [description]
    """
    
    if len(args) < 2:
        await message.channel.send("❌ Usage: `@Bot addrule <invite_code> <role1,role2,...> [description]`")
        return
    
    invite_code = args[0]
    role_names = args[1].split(',')
    description = ' '.join(args[2:]) if len(args) > 2 else ""
    
    # Validate roles exist
    roles_to_add = []
    
    for role_name in role_names:
        role_name = role_name.strip()
        discord_role = None
        
        # Try to find role by name
        for r in message.guild.roles:
            if r.name.lower() == role_name.lower():
                discord_role = r
                break
        
        if not discord_role:
            await message.channel.send(f"❌ Role not found: `{role_name}`")
            return
        
        # Get or create in DB
        db_role, created = DiscordRole.objects.get_or_create(
            discord_id=discord_role.id,
            guild=guild_settings,
            defaults={'name': discord_role.name, 'is_deleted': False}
        )
        
        if not created:
            db_role.name = discord_role.name
            db_role.is_deleted = False
            db_role.save()
        
        roles_to_add.append(db_role)
    
    # Create or update rule
    rule, created = InviteRule.objects.get_or_create(
        guild=guild_settings,
        invite_code=invite_code,
        defaults={'description': description}
    )
    
    if not created:
        rule.description = description
        rule.save()
    
    # Set roles
    rule.roles.clear()
    rule.roles.add(*roles_to_add)
    
    action = "created" if created else "updated"
    role_list = ', '.join([r.name for r in roles_to_add])
    
    template = get_template(guild_settings, 'COMMAND_SUCCESS')
    msg = template.format(
        message=f"Rule `{invite_code}` {action}!\nRoles: {role_list}"
    )
    
    await message.channel.send(msg)
