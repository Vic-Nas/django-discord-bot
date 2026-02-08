"""
Standalone migration to add reviewed_by_name to Application.

This is needed because Railway's DB has migrations 0001-0010 applied individually,
but 0011 (which added this field) was never applied before we squashed into 0001_squashed.
The squash includes this field in its CreateModel, so fresh DBs are fine — but existing
DBs need this explicit AddField.
"""
from django.db import connection, migrations, models


def add_column_if_missing(apps, schema_editor):
    """Add reviewed_by_name column only if it doesn't already exist (idempotent)."""
    columns = [
        col.name for col in connection.introspection.get_table_description(
            connection.cursor(), 'applications'
        )
    ]
    if 'reviewed_by_name' not in columns:
        schema_editor.execute(
            "ALTER TABLE applications ADD COLUMN reviewed_by_name varchar(100) NOT NULL DEFAULT ''"
        )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_squashed'),
    ]

    operations = [
        migrations.RunPython(add_column_if_missing, migrations.RunPython.noop),
    ]
