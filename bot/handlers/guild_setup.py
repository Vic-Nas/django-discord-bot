import discord
from core.models import GuildSettings, DiscordRole, DiscordChannel, Automation, Action
from .templates import get_template_async
from asgiref.sync import sync_to_async


async def setup_guild(bot, guild):
    """
    Setup guild when bot joins:
    1. Create BotAdmin role
    2. Create Pending role
    3. Create #bounce channel (single channel for all bot output)
    4. Create #pending channel
    5. Create default automations
    6. Save to database
    """

    # Get or create guild settings
    guild_settings, created = await sync_to_async(GuildSettings.objects.get_or_create)(
        guild_id=guild.id,
        defaults={'guild_name': guild.name}
    )

    if not created:
        guild_settings.guild_name = guild.name
        await sync_to_async(guild_settings.save)()

    # Create BotAdmin role
    bot_admin_role = await get_or_create_role(guild, "BotAdmin", color=discord.Color.blue())
    guild_settings.bot_admin_role_id = bot_admin_role.id

    await sync_to_async(DiscordRole.objects.update_or_create)(
        discord_id=bot_admin_role.id,
        guild=guild_settings,
        defaults={'name': bot_admin_role.name}
    )

    # Create Pending role
    pending_role = await get_or_create_role(guild, "Pending", color=discord.Color.orange())
    guild_settings.pending_role_id = pending_role.id

    await sync_to_async(DiscordRole.objects.update_or_create)(
        discord_id=pending_role.id,
        guild=guild_settings,
        defaults={'name': pending_role.name}
    )

    # Assign BotAdmin role to bot itself
    assignment_failed = False
    try:
        await guild.me.add_roles(bot_admin_role)
        print(f"✅ Assigned BotAdmin role to bot in {guild.name}")
    except Exception as e:
        assignment_failed = True
        print(f"❌ Failed to assign BotAdmin role to bot in {guild.name}: {e}")
        print(f"   Bot permissions: {guild.me.guild_permissions}")

    # Create #bounce channel (single channel for all bot output)
    bounce_channel = await get_or_create_channel(guild, "bounce", bot_admin_role)
    guild_settings.bounce_channel_id = bounce_channel.id

    await sync_to_async(DiscordChannel.objects.update_or_create)(
        discord_id=bounce_channel.id,
        guild=guild_settings,
        defaults={'name': bounce_channel.name}
    )

    # Create #pending channel (visible ONLY to Pending role + bot)
    pending_channel = await get_or_create_pending_channel(guild, pending_role)
    guild_settings.pending_channel_id = pending_channel.id

    await sync_to_async(DiscordChannel.objects.update_or_create)(
        discord_id=pending_channel.id,
        guild=guild_settings,
        defaults={'name': pending_channel.name}
    )

    # Restrict Pending role from seeing all other channels
    await restrict_pending_role(guild, pending_role)

    await sync_to_async(guild_settings.save)()

    # Create default automations
    await _create_default_automations(guild_settings)

    if assignment_failed:
        try:
            bot_role = guild.me.top_role
            bot_role_name = bot_role.name if bot_role.name != "@everyone" else "(no assigned role)"
            diagnostic_msg = await get_template_async(guild_settings, 'SETUP_DIAGNOSTIC')
            diagnostic_msg = diagnostic_msg.format(bot_role=bot_role_name)
            await bounce_channel.send(diagnostic_msg)
        except Exception:
            try:
                general = discord.utils.get(guild.text_channels, name='general')
                if general:
                    bot_role = guild.me.top_role
                    bot_role_name = bot_role.name if bot_role.name != "@everyone" else "(no assigned role)"
                    diagnostic_msg = await get_template_async(guild_settings, 'SETUP_DIAGNOSTIC')
                    diagnostic_msg = diagnostic_msg.format(bot_role=bot_role_name)
                    await general.send(diagnostic_msg)
            except Exception:
                print("Could not send diagnostic message to any channel")

    # Send welcome message to bounce channel
    try:
        if bounce_channel:
            template = await get_template_async(guild_settings, 'INSTALL_WELCOME')
            message = template.format(
                bot_admin=bot_admin_role.mention,
                pending=pending_role.mention,
                logs=bounce_channel.mention,
                bot_mention=bot.user.mention
            )
            await bounce_channel.send(message)
    except Exception as e:
        print(f"Failed to send welcome message: {e}")


async def _create_default_automations(gs):
    """Create default event-driven automations for this guild."""

    defaults = [
        # AUTO mode: log join to bounce channel
        {
            'name': 'Log Join (Auto)',
            'trigger': 'MEMBER_JOIN',
            'trigger_config': {'mode': 'AUTO'},
            'description': 'Log new member join to bounce channel in AUTO mode',
            'actions': [
                {'order': 1, 'action_type': 'SEND_EMBED', 'config': {
                    'channel': 'bounce', 'template': 'JOIN_LOG_AUTO', 'color': 0x2ecc71}},
                {'order': 2, 'action_type': 'ADD_ROLE', 'config': {'from_rule': True}},
            ]
        },
        # APPROVAL mode: create application embed, assign Pending, set topic
        {
            'name': 'Approval Join',
            'trigger': 'MEMBER_JOIN',
            'trigger_config': {'mode': 'APPROVAL'},
            'description': 'Create pending application for new member',
            'actions': [
                {'order': 1, 'action_type': 'ADD_ROLE', 'config': {'role': 'pending'}},
                {'order': 2, 'action_type': 'SEND_EMBED', 'config': {
                    'channel': 'bounce', 'template': 'application', 'track': True}},
                {'order': 3, 'action_type': 'SEND_DM', 'config': {
                    'template': 'WELCOME_DM_APPROVAL'}},
            ]
        },
    ]

    for d in defaults:
        auto, created = await sync_to_async(Automation.objects.get_or_create)(
            guild=gs,
            name=d['name'],
            defaults={
                'trigger': d['trigger'],
                'trigger_config': d.get('trigger_config', {}),
                'description': d.get('description', ''),
                'enabled': True,
            }
        )
        if created:
            for a in d.get('actions', []):
                await sync_to_async(Action.objects.create)(
                    automation=auto,
                    order=a['order'],
                    action_type=a['action_type'],
                    config=a.get('config', {}),
                    enabled=True,
                )

    count = await sync_to_async(Automation.objects.filter(guild=gs).count)()
    print(f"✅ {count} automations configured for {gs.guild_name}")


async def get_or_create_pending_channel(guild, pending_role):
    """Create #pending channel visible ONLY to Pending role and bot"""
    channel = discord.utils.get(guild.text_channels, name='pending')

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        pending_role: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }

    if channel:
        try:
            await channel.edit(overwrites=overwrites)
        except Exception:
            pass
        return channel

    try:
        channel = await guild.create_text_channel('pending', overwrites=overwrites)
    except Exception:
        channel = await guild.create_text_channel('pending')

    return channel


async def restrict_pending_role(guild, pending_role):
    """Prevent Pending role from seeing all channels except #pending"""
    for channel in guild.text_channels:
        if channel.name == 'pending':
            continue
        try:
            await channel.set_permissions(pending_role, read_messages=False)
        except Exception:
            pass


async def get_or_create_role(guild, name, **kwargs):
    """Get existing role or create new one"""
    role = discord.utils.get(guild.roles, name=name)
    if role:
        return role
    role = await guild.create_role(name=name, **kwargs)
    return role


async def get_or_create_channel(guild, name, admin_role):
    """Get existing channel or create new one with proper permissions"""
    channel = discord.utils.get(guild.text_channels, name=name)

    if channel:
        try:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                admin_role: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, embed_links=True)
            }
            await channel.edit(overwrites=overwrites)
        except Exception:
            pass
        return channel

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        admin_role: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, embed_links=True)
    }

    try:
        channel = await guild.create_text_channel(name, overwrites=overwrites)
    except Exception:
        channel = await guild.create_text_channel(name)

    return channel


async def ensure_required_resources(bot, guild_settings):
    """
    Ensure required roles/channels exist.
    Called when needed (e.g., before role assignment).
    """
    guild = bot.get_guild(guild_settings.guild_id)
    if not guild:
        return

    changed = False

    # Check BotAdmin role
    bot_admin_role = None
    if guild_settings.bot_admin_role_id:
        bot_admin_role = guild.get_role(guild_settings.bot_admin_role_id)
    if not bot_admin_role:
        bot_admin_role = await get_or_create_role(guild, "BotAdmin", color=discord.Color.blue())
        guild_settings.bot_admin_role_id = bot_admin_role.id
        changed = True
        await sync_to_async(DiscordRole.objects.update_or_create)(
            discord_id=bot_admin_role.id,
            guild=guild_settings,
            defaults={'name': bot_admin_role.name}
        )

    # Check Pending role
    pending_role = None
    if guild_settings.pending_role_id:
        pending_role = guild.get_role(guild_settings.pending_role_id)
    if not pending_role:
        pending_role = await get_or_create_role(guild, "Pending", color=discord.Color.orange())
        guild_settings.pending_role_id = pending_role.id
        changed = True
        await sync_to_async(DiscordRole.objects.update_or_create)(
            discord_id=pending_role.id,
            guild=guild_settings,
            defaults={'name': pending_role.name}
        )

    # Check bounce channel
    bounce_channel = None
    if guild_settings.bounce_channel_id:
        bounce_channel = guild.get_channel(guild_settings.bounce_channel_id)
    if not bounce_channel:
        bounce_channel = await get_or_create_channel(guild, "bounce", bot_admin_role)
        guild_settings.bounce_channel_id = bounce_channel.id
        changed = True
        await sync_to_async(DiscordChannel.objects.update_or_create)(
            discord_id=bounce_channel.id,
            guild=guild_settings,
            defaults={'name': bounce_channel.name}
        )

    # Check pending channel
    pending_channel = None
    if guild_settings.pending_channel_id:
        pending_channel = guild.get_channel(guild_settings.pending_channel_id)
    if not pending_channel:
        pending_channel = await get_or_create_pending_channel(guild, pending_role)
        guild_settings.pending_channel_id = pending_channel.id
        changed = True
        await sync_to_async(DiscordChannel.objects.update_or_create)(
            discord_id=pending_channel.id,
            guild=guild_settings,
            defaults={'name': pending_channel.name}
        )

    if changed:
        await sync_to_async(guild_settings.save)()
