from core.models import GuildSettings, BotCommand
from asgiref.sync import sync_to_async
from bot.execution.action_executor import execute_command_actions


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
        
        # Get guild settings (must exist for guild commands)
        guild_settings = None
        if message.guild:
            try:
                guild_settings = await sync_to_async(GuildSettings.objects.get)(guild_id=message.guild.id)
            except GuildSettings.DoesNotExist:
                await message.channel.send("❌ This server is not configured. Please contact a server administrator.")
                return
        else:
            # DM context
            await message.channel.send("❌ Commands only work in servers.")
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
            
            if available:
                cmd_list = ', '.join(sorted(available))
                await message.channel.send(f"❌ Command `{command_name}` not found.\n\n📋 **Available commands:** {cmd_list}")
            else:
                await message.channel.send(f"❌ Command `{command_name}` not found. No commands configured for this server.")
            return
        
        # Check if command is enabled
        if not bot_cmd.enabled:
            await message.channel.send(f"❌ Command `{command_name}` is disabled on this server.")
            return
        
        # Execute all CommandActions for this command in order
        print(f"📤 Executing command '{command_name}' on server {message.guild.name}")
        
        try:
            results = await execute_command_actions(bot, message, bot_cmd)
            
            # Log results
            for success, status_msg in results:
                if not success:
                    print(f"   {status_msg}")
                else:
                    print(f"   {status_msg}")
        
        except Exception as e:
            print(f"❌ Unexpected error executing {command_name}: {e}")
            await message.channel.send(f"❌ An error occurred: {str(e)}")
    
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
