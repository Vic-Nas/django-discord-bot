from django.db import connection, migrations


def drop_tables(apps, schema_editor):
    """Drop old tables in a DB-agnostic way."""
    with connection.cursor() as cursor:
        if connection.vendor == 'postgresql':
            cursor.execute("DROP TABLE IF EXISTS core_guildcommand CASCADE;")
            cursor.execute("DROP TABLE IF EXISTS core_botcommand CASCADE;")
        else:
            cursor.execute("DROP TABLE IF EXISTS core_guildcommand;")
            cursor.execute("DROP TABLE IF EXISTS core_botcommand;")


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(drop_tables, reverse_code=migrations.RunPython.noop),
    ]
