"""
Migration 0003:
  1. Update MessageTemplate.template_type choices to match current model
  2. Reset PostgreSQL sequences for all tables to avoid duplicate PK errors
"""

from django.db import migrations, models


def reset_sequences(apps, schema_editor):
    """Reset all auto-increment sequences to max(id)+1."""
    if schema_editor.connection.vendor != 'postgresql':
        return  # Only needed for PostgreSQL

    tables = [
        'access_tokens',
        'actions',
        'applications',
        'automations',
        'discord_channels',
        'discord_roles',
        'dropdowns',
        'dropdown_options',
        'form_fields',
        'guild_message_templates',
        'invite_rules',
        'message_templates',
    ]
    with schema_editor.connection.cursor() as cursor:
        for table in tables:
            cursor.execute(f"""
                SELECT setval(
                    pg_get_serial_sequence('"{table}"', 'id'),
                    COALESCE((SELECT MAX(id) FROM "{table}"), 0) + 1,
                    false
                )
            """)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_guildsettings_language'),
    ]

    operations = [
        migrations.AlterField(
            model_name='messagetemplate',
            name='template_type',
            field=models.CharField(
                choices=[
                    ('INSTALL_WELCOME', 'Setup – Welcome Message'),
                    ('SETUP_DIAGNOSTIC', 'Setup – Role Hierarchy Warning'),
                    ('JOIN_LOG_AUTO', 'Join Log (AUTO mode)'),
                    ('JOIN_LOG_APPROVAL', 'Join Log (APPROVAL mode)'),
                    ('PENDING_CHANNEL_TOPIC', 'Pending Channel – Topic (with form)'),
                    ('PENDING_CHANNEL_TOPIC_NO_FORM', 'Pending Channel – Topic (no form)'),
                    ('APPLICATION_SENT', 'Application Submitted'),
                    ('APPLICATION_APPROVED', 'Application Approved'),
                    ('APPLICATION_REJECTED', 'Application Rejected'),
                    ('APPROVE_CONFIRM', 'Approve – Admin Confirmation'),
                    ('APPROVE_DM', 'Approve – User DM'),
                    ('APPROVE_STATUS', 'Approve – Embed Status Field'),
                    ('REJECT_CONFIRM', 'Reject – Admin Confirmation'),
                    ('REJECT_DM', 'Reject – User DM'),
                    ('REJECT_STATUS', 'Reject – Embed Status Field'),
                    ('REJECT_PENDING', 'Reject – Pending Channel Notice'),
                    ('APPROVAL_NOTIFICATION', 'Approval Channel Notification'),
                    ('NO_PENDING_APP', 'No Pending Application'),
                    ('BULK_APPROVE_RESULT', 'Bulk Approve – Result'),
                    ('GETACCESS_RESPONSE', 'GetAccess Token Response'),
                    ('GETACCESS_EXISTS', 'Token Already Exists'),
                    ('GETACCESS_NO_ADMIN', 'GetAccess – Not Admin'),
                    ('GETACCESS_PICK_SERVER', 'GetAccess – Pick Server'),
                    ('HELP_MESSAGE', 'Help Command'),
                    ('COMMAND_SUCCESS', 'Command Success'),
                    ('COMMAND_ERROR', 'Command Error'),
                    ('COMMAND_NOT_FOUND', 'Command Not Found'),
                    ('COMMAND_DISABLED', 'Command Disabled'),
                    ('LISTRULES_EMPTY', 'List Rules – Empty'),
                    ('LISTFIELDS_EMPTY', 'List Fields – Empty'),
                    ('CLEANUP_REPLY', 'Cleanup – Confirmation'),
                    ('CLEANALL_REPLY', 'Clean All – Confirmation'),
                    ('ADMIN_REQUIRED', 'Admin Required Warning'),
                    ('SERVER_NOT_CONFIGURED', 'Server Not Configured'),
                    ('DM_ONLY_WARNING', 'DM-Only Warning'),
                    ('SERVER_ONLY_WARNING', 'Server-Only Warning'),
                    ('USER_LEFT_SERVER', 'User Left Server'),
                    ('AUTO_TRANSLATE_ON', 'Auto-Translate Enabled'),
                    ('AUTO_TRANSLATE_OFF', 'Auto-Translate Disabled'),
                ],
                max_length=50,
                unique=True,
            ),
        ),
        migrations.RunPython(reset_sequences, migrations.RunPython.noop),
    ]
