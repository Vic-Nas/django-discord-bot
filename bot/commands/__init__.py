from core.models import GuildSettings, BotCommand
from django.core.exceptions import ObjectDoesNotExist
from asgiref.sync import sync_to_async


class CommandRegistry:
    """Manages bot commands"""
    
    def __init__(self):
        self.commands = {}
    
    def register(self, name, handler, description, admin_only=False):
        """Register a command"""
        self.commands[name] = {
            'handler': handler,
            'description': description,
            'admin_only': admin_only
        }
    
    async def execute(self, bot, message, command_name, args, invite_cache):
        """Execute a command"""
        
        # Get guild settings (if in a guild, else None)
        guild_settings = None
        if message.guild:
            try:
                guild_settings = await sync_to_async(GuildSettings.objects.get)(guild_id=message.guild.id)
            except GuildSettings.DoesNotExist:
                await message.channel.send("❌ Guild not configured. Please contact bot admin.")
                return
        
        # Check if command exists in registry
        if command_name not in self.commands:
            await message.channel.send(f"❌ Unknown command: `{command_name}`. Use `@{bot.user.name} help` for available commands.")
            return
        
        cmd_info = self.commands[command_name]
        
        # Check if command is enabled for this guild
        try:
            bot_cmd = await sync_to_async(BotCommand.objects.get)(guild=guild_settings, name=command_name)
            
            enabled = await sync_to_async(lambda: bot_cmd.enabled)()
            if not enabled:
                await message.channel.send(f"❌ Command `{command_name}` is disabled on this server.")
                return
            
            # Check if user has permission
            has_roles = await sync_to_async(bot_cmd.allowed_roles.exists)()
            if has_roles:
                user_role_ids = [role.id for role in message.author.roles]
                allowed_role_ids = await sync_to_async(lambda: list(guild_cmd.allowed_roles.values_list('discord_id', flat=True)))()
                
                if not any(rid in allowed_role_ids for rid in user_role_ids):
                    await message.channel.send("❌ You don't have permission to use this command.")
                    return
            
        except BotCommand.DoesNotExist:
            # Command not in DB, use default behavior
            pass
        
        # Check admin permission for admin-only commands
        if cmd_info['admin_only']:
            admin_role = message.guild.get_role(guild_settings.bot_admin_role_id)
            if not admin_role or admin_role not in message.author.roles:
                await message.channel.send("❌ This command requires the BotAdmin role.")
                return
        
        # Execute the command
        try:
            await cmd_info['handler'](bot, message, args, guild_settings, invite_cache)
        except Exception as e:
            print(f"❌ Error executing command {command_name}: {e}")
            await message.channel.send(f"❌ An error occurred while executing the command: {e}")
    
    def get_commands_for_user(self, guild_settings, user_roles):
        """Get list of commands available to a user"""
        available = []
        
        # In DM context (guild_settings is None), only show getaccess
        if guild_settings is None:
            return [{
                'name': 'getaccess',
                'description': self.commands['getaccess']['description'],
                'admin_only': False
            }]
        
        for name, info in self.commands.items():
            # Check if enabled
            try:
                bot_cmd = BotCommand.objects.get(guild=guild_settings, name=name)
                
                enabled = bot_cmd.enabled
                if not enabled:
                    continue
                
                # Check permissions
                if bot_cmd.allowed_roles.exists():
                    user_role_ids = [role.id for role in user_roles]
                    allowed_role_ids = list(bot_cmd.allowed_roles.values_list('discord_id', flat=True))
                    
                    if not any(rid in allowed_role_ids for rid in user_role_ids):
                        continue
                
            except BotCommand.DoesNotExist:
                pass
            
            available.append({
                'name': name,
                'description': info['description'],
                'admin_only': info['admin_only']
            })
        
        return available


# Global registry instance
command_registry = CommandRegistry()


# Import and register all commands
from .cmd_help import cmd_help
from .cmd_addrule import cmd_addrule
from .cmd_delrule import cmd_delrule
from .cmd_listrules import cmd_listrules
from .cmd_setmode import cmd_setmode
from .cmd_reload import cmd_reload
from .cmd_getaccess import cmd_getaccess
from .cmd_addfield import cmd_addfield
from .cmd_listfields import cmd_listfields

command_registry.register('help', cmd_help, 'Show available commands', admin_only=False)
command_registry.register('addrule', cmd_addrule, 'Add invite rule: addrule <code> <role1,role2> [description]', admin_only=True)
command_registry.register('delrule', cmd_delrule, 'Delete invite rule: delrule <code>', admin_only=True)
command_registry.register('listrules', cmd_listrules, 'List all invite rules', admin_only=True)
command_registry.register('setmode', cmd_setmode, 'Set server mode: setmode <AUTO|APPROVAL>', admin_only=True)
command_registry.register('reload', cmd_reload, 'Sync roles/channels with Discord', admin_only=True)
command_registry.register('getaccess', cmd_getaccess, 'Get web panel access (DM only)', admin_only=False)
command_registry.register('addfield', cmd_addfield, 'Add form field: addfield <label> <type> [required]', admin_only=True)
command_registry.register('listfields', cmd_listfields, 'List application form fields', admin_only=True)
