from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='guildsettings',
            name='language',
            field=models.CharField(
                blank=True,
                help_text='Auto-translate language code (e.g. fr, es, de). Leave blank for English.',
                max_length=10,
                null=True,
            ),
        ),
    ]
