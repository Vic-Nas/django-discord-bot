"""
Management command to initialize default templates and automations.

Templates are seeded for every guild. Automations are created via
guild_setup.py when the bot first joins, but this command can recreate
them if needed (e.g., after a DB reset).

Default automation definitions live in core/fixtures/default_automations.json
— the same data an admin could create manually via the admin panel.

Usage:
  python manage.py init_defaults
  python manage.py init_defaults --guild_id 123456789
"""

import json
import os

from django.core.management.base import BaseCommand
from core.models import GuildSettings, Automation, Action
from bot.handlers.templates import init_default_templates, DEFAULT_TEMPLATES


FIXTURE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'fixtures', 'default_automations.json',
)


def _load_automation_fixture():
    with open(FIXTURE_PATH, 'r') as f:
        return json.load(f)


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
            init_default_templates()
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
        """Create default automations from fixture file (sync version)."""
        defaults = _load_automation_fixture()

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
