from django.db import models
from django.utils import timezone
import secrets


class GuildSettings(models.Model):
    """Main settings for each Discord server"""
    guild_id = models.BigIntegerField(primary_key=True)
    guild_name = models.CharField(max_length=100)
    
    # Mode
    MODE_CHOICES = [('AUTO', 'Auto'), ('APPROVAL', 'Approval')]
    mode = models.CharField(max_length=20, choices=MODE_CHOICES, default='AUTO')
    
    # Required roles (stored by ID, auto-created if missing)
    bot_admin_role_id = models.BigIntegerField(null=True, blank=True)
    pending_role_id = models.BigIntegerField(null=True, blank=True)
    
    # Channels (stored by ID, auto-created if missing)
    logs_channel_id = models.BigIntegerField(null=True, blank=True)
    approvals_channel_id = models.BigIntegerField(null=True, blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'guild_settings'
        verbose_name_plural = 'Guild Settings'
    
    def __str__(self):
        return f"{self.guild_name} ({self.guild_id})"


class DiscordRole(models.Model):
    """Cached Discord roles"""
    discord_id = models.BigIntegerField()
    guild = models.ForeignKey(GuildSettings, on_delete=models.CASCADE, related_name='roles')
    name = models.CharField(max_length=100)
    
    class Meta:
        db_table = 'discord_roles'
        unique_together = ['guild', 'discord_id']
    
    def __str__(self):
        return self.name


class DiscordChannel(models.Model):
    """Cached Discord channels"""
    discord_id = models.BigIntegerField()
    guild = models.ForeignKey(GuildSettings, on_delete=models.CASCADE, related_name='channels')
    
    class Meta:
        db_table = 'discord_channels'
        unique_together = ['guild', 'discord_id']
    
    def __str__(self):
        return f"Channel {self.discord_id}"


class InviteRule(models.Model):
    """Invite code -> roles mapping"""
    guild = models.ForeignKey(GuildSettings, on_delete=models.CASCADE, related_name='rules')
    invite_code = models.CharField(max_length=50)  # 'default' is special fallback
    roles = models.ManyToManyField(DiscordRole, related_name='rules')
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'invite_rules'
        unique_together = ['guild', 'invite_code']
    
    def __str__(self):
        return f"{self.invite_code} -> {', '.join(r.name for r in self.roles.all())}"


class FormField(models.Model):
    """Dynamic form fields for approval applications"""
    FIELD_TYPES = [
        ('text', 'Short Text'),
        ('textarea', 'Long Text'),
        ('select', 'Dropdown'),
        ('radio', 'Radio Buttons'),
        ('checkbox', 'Checkboxes'),
        ('file', 'File Upload'),
    ]
    
    guild = models.ForeignKey(GuildSettings, on_delete=models.CASCADE, related_name='form_fields')
    label = models.CharField(max_length=200)
    field_type = models.CharField(max_length=20, choices=FIELD_TYPES)
    options = models.JSONField(null=True, blank=True)  # For select/radio/checkbox
    required = models.BooleanField(default=True)
    order = models.IntegerField(default=0)
    
    class Meta:
        db_table = 'form_fields'
        ordering = ['order']
    
    def __str__(self):
        return f"{self.label} ({self.field_type})"


class Application(models.Model):
    """User applications in APPROVAL mode"""
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
    responses = models.JSONField()  # {field_id: value}
    
    reviewed_by = models.BigIntegerField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'applications'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user_name} - {self.status}"


class BotCommand(models.Model):
    """Bot command with per-server configuration"""
    guild = models.ForeignKey(GuildSettings, on_delete=models.CASCADE, related_name='commands', null=True, blank=True)
    name = models.CharField(max_length=50)  # e.g., 'verify', 'welcome'
    description = models.TextField(default='')
    enabled = models.BooleanField(default=True)
    custom_name = models.CharField(max_length=50, blank=True)  # Override display name for this server
    
    class Meta:
        db_table = 'bot_commands'
        unique_together = ['guild', 'name']
    
    def __str__(self):
        display_name = self.custom_name or self.name
        status = 'ON' if self.enabled else 'OFF'
        guild_name = self.guild.guild_name if self.guild else 'Global'
        return f"{guild_name}: {display_name} [{status}]"


class CommandAction(models.Model):
    """Executable action that chains in sequence within a command"""
    ACTION_TYPES = [
        ('SEND_MESSAGE', 'Send Message'),
        ('ASSIGN_ROLE', 'Assign Role'),
        ('REMOVE_ROLE', 'Remove Role'),
        ('CREATE_CHANNEL', 'Create Channel'),
        ('DELETE_CHANNEL', 'Delete Channel'),
        ('POLL', 'Create Poll'),
        ('WEBHOOK', 'Call Webhook'),
    ]
    
    command = models.ForeignKey(BotCommand, on_delete=models.CASCADE, related_name='actions')
    order = models.IntegerField(default=0)  # Execution order
    type = models.CharField(max_length=30, choices=ACTION_TYPES)
    name = models.CharField(max_length=100)  # Unique name within command, e.g., "send_welcome"
    parameters = models.JSONField(default=dict)  # Type-specific config
    enabled = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'command_actions'
        unique_together = ['command', 'name']
        ordering = ['order']
    
    def __str__(self):
        return f"{self.command.name}: {self.name} ({self.get_type_display()})"


class MessageTemplate(models.Model):
    """Editable message templates"""
    TEMPLATE_TYPES = [
        ('INSTALL_WELCOME', 'Installation Welcome'),
        ('JOIN_LOG_AUTO', 'Join Log (AUTO mode)'),
        ('JOIN_LOG_APPROVAL', 'Join Log (APPROVAL mode)'),
        ('APPLICATION_SENT', 'Application Submitted'),
        ('APPLICATION_APPROVED', 'Application Approved'),
        ('APPLICATION_REJECTED', 'Application Rejected'),
        ('APPROVAL_NOTIFICATION', 'Approval Channel Notification'),
        ('GETACCESS_RESPONSE', 'GetAccess Token Response'),
        ('GETACCESS_EXISTS', 'Token Already Exists'),
        ('HELP_MESSAGE', 'Help Command'),
        ('COMMAND_SUCCESS', 'Command Success'),
        ('COMMAND_ERROR', 'Command Error'),
    ]
    
    template_type = models.CharField(max_length=50, choices=TEMPLATE_TYPES, unique=True)
    default_content = models.TextField()
    
    class Meta:
        db_table = 'message_templates'
    
    def __str__(self):
        return self.get_template_type_display()


class GuildMessageTemplate(models.Model):
    """Per-server template overrides"""
    guild = models.ForeignKey(GuildSettings, on_delete=models.CASCADE, related_name='message_templates')
    template = models.ForeignKey(MessageTemplate, on_delete=models.CASCADE)
    custom_content = models.TextField()
    
    class Meta:
        db_table = 'guild_message_templates'
        unique_together = ['guild', 'template']
    
    def __str__(self):
        return f"{self.guild.guild_name}: {self.template.template_type}"


class AccessToken(models.Model):
    """24-hour access tokens for web panel"""
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
        return f"{self.user_name} -> {self.guild.guild_name}"
