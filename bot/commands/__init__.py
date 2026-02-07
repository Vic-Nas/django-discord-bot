from core.models import GuildSettings, BotCommand
from asgiref.sync import sync_to_async
from bot.execution.action_executor import execute_command_actions, handle_generate_access_token
from bot.handlers.templates import get_template_async


class CommandRegistry:
    """
    Database-driven command registry.
    All commands are read from BotCommand model with CommandActions.
    No hardcoded handlers - execution is purely data-driven.
    """
    
    async def execute(self, bot, message, command_name, args, invite_cache):
        """
        Execute a command by looking it up in the database and running its CommandActions.
        
        Args:
            bot: discord.py Bot instance
            message: discord.Message that triggered the command
            command_name: Name of the command (e.g., 'help')
            args: List of argument strings
            invite_cache: Invite cache dict for member tracking
        """
        
        # getaccess is DM-only — bypass normal guild-based command lookup
        if command_name == 'getaccess':
            if message.guild:
                tpl = await get_template_async(None, 'DM_ONLY_WARNING')
                await message.channel.send(tpl)
                return
            # DM context — call handler directly (no guild_settings needed)
            await handle_generate_access_token(bot, message, {}, None)
            return
        
        # All other commands require server context
        if not message.guild:
            tpl = await get_template_async(None, 'SERVER_ONLY_WARNING')
            await message.channel.send(tpl)
            return
        
        # Get guild settings (must exist for guild commands)
        try:
            guild_settings = await sync_to_async(GuildSettings.objects.get)(guild_id=message.guild.id)
        except GuildSettings.DoesNotExist:
            await message.channel.send("❌ This server is not configured. Please contact a server administrator.")
            return
        
        # Look up command in database
        try:
            bot_cmd = await sync_to_async(BotCommand.objects.get)(
                guild=guild_settings, 
                name=command_name
            )
        except BotCommand.DoesNotExist:
            # Get list of available commands for help text
            available = await sync_to_async(
                lambda: list(BotCommand.objects.filter(guild=guild_settings, enabled=True).values_list('name', flat=True))
            )()
            
            cmd_list = ', '.join(sorted(available)) if available else 'none'
            tpl = await get_template_async(guild_settings, 'COMMAND_NOT_FOUND')
            await message.channel.send(tpl.format(command=command_name, commands=cmd_list))
            return
        
        # Check if command is enabled
        if not bot_cmd.enabled:
            tpl = await get_template_async(guild_settings, 'COMMAND_DISABLED')
            await message.channel.send(tpl.format(command=command_name))
            return
        
        # Execute all CommandActions for this command in order
        guild_name = message.guild.name if message.guild else 'DM'
        print(f"📤 Executing command '{command_name}' on server {guild_name}")
        
        try:
            results = await execute_command_actions(bot, message, bot_cmd, guild_settings, args)
            
            # Log results
            for success, status_msg in results:
                if not success:
                    print(f"   {status_msg}")
                else:
                    print(f"   {status_msg}")
        
        except Exception as e:
            print(f"❌ Unexpected error executing {command_name}: {e}")
            tpl = await get_template_async(guild_settings, 'COMMAND_ERROR')
            await message.channel.send(tpl.format(message=str(e)))
    
    async def get_commands_for_user(self, guild_settings):
        """
        Get list of enabled commands for a guild (sorted by name).
        
        Returns:
            List of dicts with 'name' and 'description'
        """
        if not guild_settings:
            return []
        
        commands = await sync_to_async(
            lambda: list(
                BotCommand.objects.filter(
                    guild=guild_settings, 
                    enabled=True
                ).order_by('name').values('name', 'description')
            )
        )()
        
        return commands


# Global registry instance - now purely database-driven
command_registry = CommandRegistry()
