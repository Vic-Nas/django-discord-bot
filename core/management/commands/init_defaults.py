from django.core.management.base import BaseCommand
from core.models import MessageTemplate, GuildSettings, BotCommand, CommandAction
from bot.handlers.templates import DEFAULT_TEMPLATES


class Command(BaseCommand):
    help = 'Initialize default message templates and bot commands for a guild'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--guild_id',
            type=int,
            help='Guild ID to initialize. If not provided, initializes all guilds.'
        )

    def handle(self, *args, **options):
        # Initialize message templates
        self.stdout.write('Initializing message templates...')
        
        for template_type, content in DEFAULT_TEMPLATES.items():
            template, created = MessageTemplate.objects.get_or_create(
                template_type=template_type,
                defaults={'default_content': content}
            )
            
            if created:
                self.stdout.write(self.style.SUCCESS(f'  ✓ Created template: {template_type}'))
            else:
                # Update content if changed
                if template.default_content != content:
                    template.default_content = content
                    template.save()
                    self.stdout.write(self.style.WARNING(f'  ↻ Updated template: {template_type}'))
                else:
                    self.stdout.write(f'  - Template exists: {template_type}')
        
        # Initialize bot commands per guild
        self.stdout.write('\nInitializing bot commands...')
        
        guild_id = options.get('guild_id')
        if guild_id:
            guilds = GuildSettings.objects.filter(guild_id=guild_id)
            if not guilds.exists():
                self.stdout.write(self.style.ERROR(f'Guild {guild_id} not found in database'))
                return
        else:
            guilds = GuildSettings.objects.all()
        
        if not guilds.exists():
            self.stdout.write(self.style.WARNING('No guilds found. Add bot to Discord server first.'))
            return
        
        commands_data = [
            {
                'name': 'help',
                'description': 'Show available commands and how to use them',
                'actions': [
                    {'type': 'LIST_COMMANDS', 'name': 'show_commands', 'parameters': {}},
                ]
            },
            {
                'name': 'getaccess',
                'description': 'Get a temporary access link to the web panel',
                'actions': [
                    {'type': 'GENERATE_ACCESS_TOKEN', 'name': 'create_token', 'parameters': {}},
                ]
            },
            {
                'name': 'addrule',
                'description': 'Add an invite rule (Admin only)',
                'actions': [
                    {'type': 'ADD_INVITE_RULE', 'name': 'add_rule', 'parameters': {}},
                ]
            },
            {
                'name': 'delrule',
                'description': 'Delete an invite rule (Admin only)',
                'actions': [
                    {'type': 'DELETE_INVITE_RULE', 'name': 'delete_rule', 'parameters': {}},
                ]
            },
            {
                'name': 'listrules',
                'description': 'List all invite rules for this server',
                'actions': [
                    {'type': 'LIST_INVITE_RULES', 'name': 'show_rules', 'parameters': {}},
                ]
            },
            {
                'name': 'setmode',
                'description': 'Set server mode: AUTO or APPROVAL (Admin only)',
                'actions': [
                    {'type': 'SET_SERVER_MODE', 'name': 'change_mode', 'parameters': {}},
                ]
            },
            {
                'name': 'approve',
                'description': 'Approve a pending user application (Admin only)',
                'actions': [
                    {'type': 'APPROVE_APPLICATION', 'name': 'approve_user', 'parameters': {}},
                ]
            },
            {
                'name': 'reject',
                'description': 'Reject a pending user application (Admin only)',
                'actions': [
                    {'type': 'REJECT_APPLICATION', 'name': 'reject_user', 'parameters': {}},
                ]
            },
            {
                'name': 'listfields',
                'description': 'List form fields for applications',
                'actions': [
                    {'type': 'LIST_FORM_FIELDS', 'name': 'show_fields', 'parameters': {}},
                ]
            },
            {
                'name': 'reload',
                'description': 'Reload bot configuration (Admin only)',
                'actions': [
                    {'type': 'RELOAD_CONFIG', 'name': 'reload_config', 'parameters': {}},
                ]
            },
        ]
        
        for guild in guilds:
            self.stdout.write(f'\n  Guild: {guild.guild_name} ({guild.guild_id})')
            
            for cmd_data in commands_data:
                # Get or create command
                bot_cmd, created = BotCommand.objects.get_or_create(
                    guild=guild,
                    name=cmd_data['name'],
                    defaults={
                        'description': cmd_data['description'],
                        'enabled': True
                    }
                )
                
                if created:
                    self.stdout.write(self.style.SUCCESS(f'    ✓ Created command: {cmd_data["name"]}'))
                else:
                    self.stdout.write(f'    - Command exists: {cmd_data["name"]}')
                
                # Create actions for this command
                for action_order, action in enumerate(cmd_data.get('actions', []), start=1):
                    action_obj, action_created = CommandAction.objects.get_or_create(
                        command=bot_cmd,
                        name=action['name'],
                        defaults={
                            'order': action_order,
                            'type': action['type'],
                            'parameters': action['parameters'],
                            'enabled': True
                        }
                    )
                    
                    if action_created:
                        self.stdout.write(f'      ✓ Created action: {action["type"]}')
        
        self.stdout.write(self.style.SUCCESS('\n✅ Initialization complete!'))
