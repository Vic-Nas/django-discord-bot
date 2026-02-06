from django.core.management.base import BaseCommand
from core.models import MessageTemplate, BotCommand
from bot.handlers.templates import DEFAULT_TEMPLATES


class Command(BaseCommand):
    help = 'Initialize default message templates and bot commands'

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
        
        # Initialize bot commands
        self.stdout.write('\nInitializing bot commands...')
        
        commands_data = [
            ('help', 'Show available commands', 'cmd_help', False),
            ('addrule', 'Add invite rule', 'cmd_addrule', True),
            ('delrule', 'Delete invite rule', 'cmd_delrule', True),
            ('listrules', 'List all invite rules', 'cmd_listrules', True),
            ('setmode', 'Set server mode (AUTO/APPROVAL)', 'cmd_setmode', True),
            ('reload', 'Sync roles/channels with Discord', 'cmd_reload', True),
            ('getaccess', 'Get web panel access token', 'cmd_getaccess', False),
            ('addfield', 'Add application form field', 'cmd_addfield', True),
            ('listfields', 'List application form fields', 'cmd_listfields', True),
        ]
        
        for name, description, handler, admin_only in commands_data:
            cmd, created = BotCommand.objects.get_or_create(
                name=name,
                defaults={
                    'description': description,
                    'handler_function': handler,
                    'admin_only': admin_only
                }
            )
            
            if created:
                self.stdout.write(self.style.SUCCESS(f'  ✓ Created command: {name}'))
            else:
                self.stdout.write(f'  - Command exists: {name}')
        
        self.stdout.write(self.style.SUCCESS('\n✅ Initialization complete!'))
