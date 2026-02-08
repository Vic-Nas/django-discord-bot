"""
Management command to initialize default templates and automations.

Templates are seeded for every guild. Automations are created via
guild_setup.py when the bot first joins, but this command can recreate
them if needed (e.g., after a DB reset).

Usage:
  python manage.py init_defaults
  python manage.py init_defaults --guild_id 123456789
"""

from django.core.management.base import BaseCommand
from core.models import GuildSettings, Automation, Action
from bot.handlers.templates import init_default_templates, DEFAULT_TEMPLATES


class Command(BaseCommand):
    help = 'Initialize default templates and automations for all guilds'

    def add_arguments(self, parser):
        parser.add_argument('--guild_id', type=int, help='Only initialize for this guild')

    def handle(self, *args, **options):
        guild_id = options.get('guild_id')

        if guild_id:
            guilds = GuildSettings.objects.filter(guild_id=guild_id)
        else:
            guilds = GuildSettings.objects.all()

        if not guilds.exists():
            self.stdout.write(self.style.WARNING('No guilds found.'))
            return

        for gs in guilds:
            self.stdout.write(f'\n{"="*50}')
            self.stdout.write(f'Guild: {gs.guild_name} ({gs.guild_id})')
            self.stdout.write(f'{"="*50}')

            # Initialize templates
            init_default_templates(gs)
            self.stdout.write(self.style.SUCCESS(
                f'  ✅ {len(DEFAULT_TEMPLATES)} templates initialized'))

            # Create default automations if none exist
            auto_count = Automation.objects.filter(guild=gs).count()
            if auto_count == 0:
                self._create_default_automations(gs)
                auto_count = Automation.objects.filter(guild=gs).count()
                self.stdout.write(self.style.SUCCESS(
                    f'  ✅ {auto_count} automations created'))
            else:
                self.stdout.write(self.style.SUCCESS(
                    f'  ✅ {auto_count} automations already exist (skipped)'))

        self.stdout.write(self.style.SUCCESS(
            f'\n✅ Done — initialized {guilds.count()} guild(s)'))

    def _create_default_automations(self, gs):
        """Create default event-driven automations (sync version of guild_setup logic)."""
        defaults = [
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
            auto, created = Automation.objects.get_or_create(
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
                    Action.objects.create(
                        automation=auto,
                        order=a['order'],
                        action_type=a['action_type'],
                        config=a.get('config', {}),
                        enabled=True,
                    )
