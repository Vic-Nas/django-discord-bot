from django.db import models
from django.utils import timezone
import secrets


# ── Guild Config ─────────────────────────────────────────────────────────────

class GuildSettings(models.Model):
    """Main settings for each Discord server."""
    guild_id = models.BigIntegerField(primary_key=True)
    guild_name = models.CharField(max_length=100)

    MODE_CHOICES = [('AUTO', 'Auto'), ('APPROVAL', 'Approval')]
    mode = models.CharField(max_length=20, choices=MODE_CHOICES, default='AUTO')

    # Roles (auto-created by bot)
    bot_admin_role_id = models.BigIntegerField(null=True, blank=True)
    pending_role_id = models.BigIntegerField(null=True, blank=True)

    # Channels — single #bounce channel replaces old logs+approvals
    bounce_channel_id = models.BigIntegerField(null=True, blank=True)
    pending_channel_id = models.BigIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'guild_settings'
        verbose_name_plural = 'Guild Settings'

    def __str__(self):
        return f"{self.guild_name} ({self.guild_id})"


# ── Discord Cache ────────────────────────────────────────────────────────────

class DiscordRole(models.Model):
    """Cached Discord roles."""
    discord_id = models.BigIntegerField()
    guild = models.ForeignKey(GuildSettings, on_delete=models.CASCADE, related_name='roles')
    name = models.CharField(max_length=100)

    class Meta:
        db_table = 'discord_roles'
        unique_together = ['guild', 'discord_id']

    def __str__(self):
        return self.name


class DiscordChannel(models.Model):
    """Cached Discord channels."""
    discord_id = models.BigIntegerField()
    guild = models.ForeignKey(GuildSettings, on_delete=models.CASCADE, related_name='channels')
    name = models.CharField(max_length=100, blank=True, default='')

    class Meta:
        db_table = 'discord_channels'
        unique_together = ['guild', 'discord_id']

    def __str__(self):
        return self.name or f"Channel {self.discord_id}"


# ── Automations (replaces BotCommand + CommandAction) ────────────────────────

class Automation(models.Model):
    """
    Event trigger → actions.  The core building block for bot behaviour.

    trigger_config examples:
      MEMBER_JOIN  — {"mode": "AUTO"} or {"mode": "APPROVAL"} or {} (always)
      COMMAND      — {"name": "welcome"}
      FORM_SUBMIT  — {}
      REACTION     — {"emoji": "✅"}
    """
    TRIGGERS = [
        ('MEMBER_JOIN', 'Member Joins'),
        ('MEMBER_LEAVE', 'Member Leaves'),
        ('COMMAND', 'Bot Command'),
        ('FORM_SUBMIT', 'Form Submitted'),
        ('REACTION', 'Reaction Added'),
    ]

    guild = models.ForeignKey(GuildSettings, on_delete=models.CASCADE, related_name='automations')
    name = models.CharField(max_length=100)
    trigger = models.CharField(max_length=20, choices=TRIGGERS)
    trigger_config = models.JSONField(
        default=dict, blank=True,
        help_text='Filter conditions as JSON. Leave {} to match all events of this trigger type.',
    )
    admin_only = models.BooleanField(default=False)
    enabled = models.BooleanField(default=True)
    description = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = 'automations'
        ordering = ['name']
        unique_together = ['guild', 'name']

    def __str__(self):
        return f"{self.name} [{self.get_trigger_display()}]"


class Action(models.Model):
    """
    A single step in an automation pipeline.

    config examples per action_type:
      SEND_MESSAGE — {"channel": "bounce", "template": "JOIN_LOG_AUTO"}
      SEND_DM      — {"template": "APPROVE_DM"}  or  {"content": "Hello!"}
      SEND_EMBED   — {"channel": "bounce", "template": "application", "track": true}
      ADD_ROLE     — {"role": "pending"}  or  {"from_rule": true}  or  {"from_form": true}
      REMOVE_ROLE  — {"role": "pending"}
      EDIT_MESSAGE — {"color": "green", "status_field": "✅ Approved by {admin}"}
      SET_TOPIC    — {"channel": "pending", "template": "PENDING_CHANNEL_TOPIC"}
      SET_PERMS    — {"channel": "from_form", "allow": ["read_messages"]}
      CLEANUP      — {"channel": "bounce", "count": 10}
    """
    TYPES = [
        ('SEND_MESSAGE', 'Send Channel Message'),
        ('SEND_DM', 'Send DM'),
        ('SEND_EMBED', 'Send Embed'),
        ('ADD_ROLE', 'Add Role'),
        ('REMOVE_ROLE', 'Remove Role'),
        ('EDIT_MESSAGE', 'Edit Tracked Message'),
        ('SET_TOPIC', 'Set Channel Topic'),
        ('SET_PERMS', 'Grant Channel Access'),
        ('CLEANUP', 'Delete Old Bot Messages'),
    ]

    automation = models.ForeignKey(Automation, on_delete=models.CASCADE, related_name='actions')
    order = models.IntegerField(default=0)
    action_type = models.CharField(max_length=20, choices=TYPES)
    config = models.JSONField(
        default=dict, blank=True,
        help_text='Parameters as JSON.  See Automation docs for format per action type.',
    )
    enabled = models.BooleanField(default=True)

    class Meta:
        db_table = 'actions'
        ordering = ['order']

    def __str__(self):
        return f"{self.automation.name} → {self.get_action_type_display()} (#{self.order})"


# ── Invite Rules ─────────────────────────────────────────────────────────────

class InviteRule(models.Model):
    """Invite code → roles mapping."""
    guild = models.ForeignKey(GuildSettings, on_delete=models.CASCADE, related_name='rules')
    invite_code = models.CharField(max_length=50)
    roles = models.ManyToManyField(DiscordRole, related_name='rules')
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'invite_rules'
        unique_together = ['guild', 'invite_code']

    def __str__(self):
        return f"{self.invite_code} → {', '.join(r.name for r in self.roles.all())}"


# ── Forms ────────────────────────────────────────────────────────────────────

class Dropdown(models.Model):
    """Reusable dropdown definitions for form fields."""
    SOURCE_TYPES = [
        ('ROLES', 'Guild Roles'),
        ('CHANNELS', 'Guild Channels'),
        ('CUSTOM', 'Custom Options'),
    ]

    guild = models.ForeignKey(GuildSettings, on_delete=models.CASCADE, related_name='dropdowns')
    name = models.CharField(max_length=100)
    source_type = models.CharField(max_length=20, choices=SOURCE_TYPES)
    multiselect = models.BooleanField(default=False)
    roles = models.ManyToManyField(DiscordRole, blank=True, related_name='dropdowns')
    channels = models.ManyToManyField(DiscordChannel, blank=True, related_name='dropdowns')

    class Meta:
        db_table = 'dropdowns'
        unique_together = ['guild', 'name']

    def __str__(self):
        multi = " (multi)" if self.multiselect else ""
        return f"{self.name} [{self.get_source_type_display()}]{multi}"

    def get_options(self):
        if self.source_type == 'ROLES':
            qs = self.roles.all() if self.roles.exists() else DiscordRole.objects.filter(guild=self.guild)
            return [{'label': r.name, 'value': str(r.discord_id)} for r in qs]
        elif self.source_type == 'CHANNELS':
            qs = self.channels.all() if self.channels.exists() else DiscordChannel.objects.filter(guild=self.guild)
            return [{'label': c.name or f'#{c.discord_id}', 'value': str(c.discord_id)} for c in qs]
        else:
            return [{'label': o.label, 'value': o.value} for o in self.custom_options.all()]


class DropdownOption(models.Model):
    """Custom options for CUSTOM-type dropdowns."""
    dropdown = models.ForeignKey(Dropdown, on_delete=models.CASCADE, related_name='custom_options')
    label = models.CharField(max_length=200)
    value = models.CharField(max_length=200)
    order = models.IntegerField(default=0)

    class Meta:
        db_table = 'dropdown_options'
        ordering = ['order']

    def __str__(self):
        return self.label


class FormField(models.Model):
    """Dynamic form fields for approval applications."""
    FIELD_TYPES = [
        ('text', 'Short Text'),
        ('textarea', 'Long Text'),
        ('dropdown', 'Dropdown'),
        ('checkbox', 'Yes/No Checkbox'),
        ('file', 'File Upload'),
    ]

    guild = models.ForeignKey(GuildSettings, on_delete=models.CASCADE, related_name='form_fields')
    label = models.CharField(max_length=200)
    field_type = models.CharField(max_length=20, choices=FIELD_TYPES)
    dropdown = models.ForeignKey(Dropdown, null=True, blank=True, on_delete=models.SET_NULL)
    placeholder = models.CharField(max_length=200, blank=True)
    required = models.BooleanField(default=True)
    order = models.IntegerField(default=0)

    class Meta:
        db_table = 'form_fields'
        ordering = ['order']

    def __str__(self):
        return f"{self.label} ({self.get_field_type_display()})"


# ── Applications ─────────────────────────────────────────────────────────────

class Application(models.Model):
    """User applications in APPROVAL mode."""
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
    ]

    guild = models.ForeignKey(GuildSettings, on_delete=models.CASCADE, related_name='applications')
    user_id = models.BigIntegerField()
    user_name = models.CharField(max_length=100)
    invite_code = models.CharField(max_length=50)
    inviter_id = models.BigIntegerField(null=True, blank=True)
    inviter_name = models.CharField(max_length=100, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    responses = models.JSONField(default=dict)

    # Discord message ID of the tracked embed in #bounce
    message_id = models.BigIntegerField(null=True, blank=True)

    reviewed_by = models.BigIntegerField(null=True, blank=True)
    reviewed_by_name = models.CharField(max_length=100, blank=True, default='')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'applications'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user_name} - {self.status}"


# ── Templates ────────────────────────────────────────────────────────────────

class MessageTemplate(models.Model):
    """Editable message templates."""
    TEMPLATE_TYPES = [
        ('INSTALL_WELCOME', 'Installation Welcome'),
        ('JOIN_LOG_AUTO', 'Join Log (AUTO mode)'),
        ('JOIN_LOG_APPROVAL', 'Join Log (APPROVAL mode)'),
        ('PENDING_CHANNEL_TOPIC', 'Pending Channel – Topic (with form)'),
        ('PENDING_CHANNEL_TOPIC_NO_FORM', 'Pending Channel – Topic (no form)'),
        ('APPLICATION_SENT', 'Application Submitted'),
        ('APPLICATION_APPROVED', 'Application Approved'),
        ('APPLICATION_REJECTED', 'Application Rejected'),
        ('APPROVE_CONFIRM', 'Approve – Admin Confirmation'),
        ('APPROVE_DM', 'Approve – User DM'),
        ('REJECT_CONFIRM', 'Reject – Admin Confirmation'),
        ('REJECT_DM', 'Reject – User DM'),
        ('REJECT_PENDING', 'Reject – Pending Channel Notice'),
        ('APPROVAL_NOTIFICATION', 'Approval Channel Notification'),
        ('GETACCESS_RESPONSE', 'GetAccess Token Response'),
        ('GETACCESS_EXISTS', 'Token Already Exists'),
        ('GETACCESS_NO_ADMIN', 'GetAccess – Not Admin'),
        ('GETACCESS_PICK_SERVER', 'GetAccess – Pick Server'),
        ('HELP_MESSAGE', 'Help Command'),
        ('COMMAND_SUCCESS', 'Command Success'),
        ('COMMAND_ERROR', 'Command Error'),
        ('COMMAND_NOT_FOUND', 'Command Not Found'),
        ('DM_ONLY_WARNING', 'DM-Only Warning'),
        ('SERVER_ONLY_WARNING', 'Server-Only Warning'),
        ('SETUP_DIAGNOSTIC', 'Setup – Role Hierarchy Warning'),
    ]

    template_type = models.CharField(max_length=50, choices=TEMPLATE_TYPES, unique=True)
    default_content = models.TextField()

    class Meta:
        db_table = 'message_templates'

    def __str__(self):
        return self.get_template_type_display()


class GuildMessageTemplate(models.Model):
    """Per-server template overrides."""
    guild = models.ForeignKey(GuildSettings, on_delete=models.CASCADE, related_name='message_templates')
    template = models.ForeignKey(MessageTemplate, on_delete=models.CASCADE)
    custom_content = models.TextField()

    class Meta:
        db_table = 'guild_message_templates'
        unique_together = ['guild', 'template']

    def __str__(self):
        return f"{self.guild.guild_name}: {self.template.template_type}"


# ── Auth ─────────────────────────────────────────────────────────────────────

class AccessToken(models.Model):
    """24-hour access tokens for web panel."""
    token = models.CharField(max_length=64, unique=True, default=secrets.token_urlsafe)
    user_id = models.BigIntegerField()
    user_name = models.CharField(max_length=100)
    guild = models.ForeignKey(GuildSettings, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = 'access_tokens'

    def is_valid(self):
        return timezone.now() < self.expires_at

    def __str__(self):
        return f"{self.user_name} → {self.guild.guild_name}"
