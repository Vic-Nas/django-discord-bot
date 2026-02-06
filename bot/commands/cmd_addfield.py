from core.models import FormField
from handlers.templates import get_template


async def cmd_addfield(bot, message, args, guild_settings, invite_cache):
    """
    Add form field for APPROVAL mode
    Usage: @Bot addfield <label> <text|textarea|select|radio|checkbox|file> [required] [options...]
    
    Examples:
    @Bot addfield "What is your name?" text required
    @Bot addfield "Why do you want to join?" textarea required
    @Bot addfield "Select your role" select required option1,option2,option3
    """
    
    if len(args) < 2:
        await message.channel.send(
            "❌ Usage: `@Bot addfield <label> <type> [required] [options]`\n"
            "Types: text, textarea, select, radio, checkbox, file\n"
            "Example: `@Bot addfield \"Your name\" text required`"
        )
        return
    
    # Parse arguments
    label = args[0].strip('"')
    field_type = args[1].lower()
    
    valid_types = ['text', 'textarea', 'select', 'radio', 'checkbox', 'file']
    if field_type not in valid_types:
        await message.channel.send(f"❌ Invalid type. Must be one of: {', '.join(valid_types)}")
        return
    
    required = 'required' in [a.lower() for a in args]
    
    # Get options for select/radio/checkbox
    options = None
    if field_type in ['select', 'radio', 'checkbox']:
        # Look for comma-separated options
        for arg in args[2:]:
            if ',' in arg and arg.lower() != 'required':
                options = [opt.strip() for opt in arg.split(',')]
                break
        
        if not options:
            await message.channel.send(f"❌ {field_type} fields require options. Example: option1,option2,option3")
            return
    
    # Get next order number
    max_order = FormField.objects.filter(guild=guild_settings).count()
    
    # Create field
    field = FormField.objects.create(
        guild=guild_settings,
        label=label,
        field_type=field_type,
        options=options,
        required=required,
        order=max_order
    )
    
    template = get_template(guild_settings, 'COMMAND_SUCCESS')
    msg = template.format(
        message=f"Form field added: **{label}** ({field_type})"
    )
    
    await message.channel.send(msg)
