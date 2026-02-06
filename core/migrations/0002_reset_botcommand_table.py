from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            DROP TABLE IF EXISTS core_guildcommand CASCADE;
            DROP TABLE IF EXISTS core_botcommand CASCADE;
            """,
            reverse_sql="SELECT 1;",  # No-op for reverse
        ),
    ]
