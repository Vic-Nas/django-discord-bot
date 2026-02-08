from django.contrib import admin
from .models import (
    GuildSettings, DiscordRole, DiscordChannel, InviteRule,
    Dropdown, DropdownOption, FormField, Application,
    Automation, Action,
    MessageTemplate, GuildMessageTemplate, AccessToken
)

# Customize admin site
admin.site.site_header = "Discord Bot Admin"
admin.site.site_title = "Bot Management"
admin.site.index_title = "Dashboard"


# ─── Guild Settings ──────────────────────────────────────────────────────────

@admin.register(GuildSettings)
class GuildSettingsAdmin(admin.ModelAdmin):
    list_display = ('guild_name', 'guild_id', 'mode', 'language', 'updated_at')
    list_filter = ('mode', 'language')
    readonly_fields = ('guild_id', 'created_at', 'updated_at')
    fieldsets = (
        (None, {'fields': ('guild_id', 'guild_name', 'mode', 'language')}),
        ('Roles (auto-managed)', {
            'fields': ('bot_admin_role_id', 'pending_role_id'),
            'description': 'These are auto-created by the bot. Only edit if you know the Discord role IDs.',
        }),
        ('Channels (auto-managed)', {
            'fields': ('bounce_channel_id', 'pending_channel_id'),
            'description': 'These are auto-created by the bot. Only edit if you know the Discord channel IDs.',
        }),
        ('Metadata', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )


# ─── Discord Resources ───────────────────────────────────────────────────────

@admin.register(DiscordRole)
class DiscordRoleAdmin(admin.ModelAdmin):
    list_display = ('name', 'discord_id', 'guild')
    list_filter = ('guild',)
    search_fields = ('name',)


@admin.register(DiscordChannel)
class DiscordChannelAdmin(admin.ModelAdmin):
    list_display = ('name', 'discord_id', 'guild')
    list_filter = ('guild',)
    search_fields = ('name',)


# ─── Automations ──────────────────────────────────────────────────────────────

class ActionInline(admin.TabularInline):
    model = Action
    fields = ('order', 'action_type', 'config', 'enabled')
    extra = 1
    ordering = ('order',)


@admin.register(Automation)
class AutomationAdmin(admin.ModelAdmin):
    list_display = ('name', 'guild', 'trigger', 'admin_only', 'enabled')
    list_filter = ('guild', 'trigger', 'enabled')
    search_fields = ('name', 'description')
    inlines = [ActionInline]
    fieldsets = (
        (None, {'fields': ('guild', 'name', 'trigger', 'trigger_config', 'enabled', 'admin_only', 'description')}),
    )


@admin.register(Action)
class ActionAdmin(admin.ModelAdmin):
    list_display = ('automation', 'action_type', 'order', 'enabled')
    list_filter = ('automation__guild', 'action_type', 'enabled')


# ─── Invite Rules ─────────────────────────────────────────────────────────────

@admin.register(InviteRule)
class InviteRuleAdmin(admin.ModelAdmin):
    list_display = ('invite_code', 'guild', 'description', 'created_at')
    list_filter = ('guild',)
    filter_horizontal = ('roles',)


# ─── Dropdowns ────────────────────────────────────────────────────────────────

class DropdownOptionInline(admin.TabularInline):
    model = DropdownOption
    fields = ('order', 'label', 'value')
    extra = 2
    ordering = ('order',)


@admin.register(Dropdown)
class DropdownAdmin(admin.ModelAdmin):
    list_display = ('name', 'source_type', 'multiselect', 'option_count', 'guild')
    list_filter = ('guild', 'source_type')
    inlines = [DropdownOptionInline]
    filter_horizontal = ('roles', 'channels')
    fieldsets = (
        (None, {'fields': ('guild', 'name', 'source_type', 'multiselect')}),
        ('Role Selection', {
            'fields': ('roles',),
            'description': 'Pick which roles appear in this dropdown. Leave empty = ALL guild roles.',
        }),
        ('Channel Selection', {
            'fields': ('channels',),
            'description': 'Pick which channels appear in this dropdown. Leave empty = ALL guild channels.',
        }),
    )

    def option_count(self, obj):
        if obj.source_type == 'ROLES':
            count = obj.roles.count()
            return f"{count} roles" if count else "All roles"
        elif obj.source_type == 'CHANNELS':
            count = obj.channels.count()
            return f"{count} channels" if count else "All channels"
        else:
            return f"{obj.custom_options.count()} options"
    option_count.short_description = 'Options'

    def get_inline_instances(self, request, obj=None):
        inlines = super().get_inline_instances(request, obj)
        if obj and obj.source_type != 'CUSTOM':
            return []
        return inlines

    def get_fieldsets(self, request, obj=None):
        base = list(super().get_fieldsets(request, obj))
        if obj:
            if obj.source_type == 'ROLES':
                return [fs for fs in base if fs[0] != 'Channel Selection']
            elif obj.source_type == 'CHANNELS':
                return [fs for fs in base if fs[0] != 'Role Selection']
            else:
                return [fs for fs in base if fs[0] not in ('Role Selection', 'Channel Selection')]
        return base


@admin.register(DropdownOption)
class DropdownOptionAdmin(admin.ModelAdmin):
    list_display = ('label', 'value', 'dropdown', 'order')
    list_filter = ('dropdown__guild', 'dropdown')


# ─── Form Fields ──────────────────────────────────────────────────────────────

@admin.register(FormField)
class FormFieldAdmin(admin.ModelAdmin):
    list_display = ('label', 'field_type', 'dropdown', 'required', 'order', 'guild')
    list_filter = ('guild', 'field_type', 'required')
    list_editable = ('order',)
    fieldsets = (
        (None, {'fields': ('guild', 'label', 'field_type', 'required', 'order')}),
        ('For Dropdown fields', {
            'fields': ('dropdown',),
            'classes': ('collapse',),
        }),
        ('For Text fields', {
            'fields': ('placeholder',),
            'classes': ('collapse',),
        }),
    )


# ─── Applications ─────────────────────────────────────────────────────────────

@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ('user_name', 'guild', 'status', 'invite_code', 'reviewed_by_name', 'created_at')
    list_filter = ('guild', 'status')
    search_fields = ('user_name',)
    readonly_fields = ('created_at', 'responses', 'status', 'reviewed_by', 'reviewed_by_name', 'reviewed_at', 'message_id')

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields
        return ('created_at', 'responses')

    fieldsets = (
        ('Application Info', {
            'fields': ('guild', 'user_id', 'user_name', 'invite_code', 'inviter_id', 'inviter_name'),
        }),
        ('Status', {
            'fields': ('status', 'reviewed_by', 'reviewed_by_name', 'reviewed_at', 'message_id'),
        }),
        ('Responses', {'fields': ('responses',)}),
        ('Timestamps', {'fields': ('created_at',)}),
    )


# ─── Message Templates ────────────────────────────────────────────────────────

@admin.register(MessageTemplate)
class MessageTemplateAdmin(admin.ModelAdmin):
    list_display = ('template_type', 'get_category', 'default_content_preview')
    list_filter = ('template_type',)
    search_fields = ('template_type', 'default_content')

    def get_category(self, obj):
        """Group templates by their prefix for easier browsing."""
        t = obj.template_type
        if t.startswith(('INSTALL', 'SETUP')):
            return 'Setup'
        if t.startswith('JOIN'):
            return 'Join'
        if t.startswith(('PENDING', 'APPLICATION')):
            return 'Application'
        if t.startswith(('APPROVE', 'REJECT', 'BULK', 'NO_PENDING')):
            return 'Approval'
        if t.startswith('GETACCESS'):
            return 'Access'
        if t.startswith(('COMMAND', 'HELP')):
            return 'Commands'
        if t.startswith(('CLEANUP', 'CLEANALL', 'CLEAN')):
            return 'Cleanup'
        if t.startswith('AUTO_TRANSLATE'):
            return 'Translate'
        return 'Other'
    get_category.short_description = 'Category'

    def default_content_preview(self, obj):
        return obj.default_content[:80] + '...' if len(obj.default_content) > 80 else obj.default_content
    default_content_preview.short_description = 'Content Preview'


@admin.register(GuildMessageTemplate)
class GuildMessageTemplateAdmin(admin.ModelAdmin):
    list_display = ('guild', 'template_type', 'custom_content_preview')
    list_filter = ('guild', 'template__template_type')

    def template_type(self, obj):
        return obj.template.get_template_type_display()
    template_type.short_description = 'Template'

    def custom_content_preview(self, obj):
        return obj.custom_content[:100] + '...' if len(obj.custom_content) > 100 else obj.custom_content
    custom_content_preview.short_description = 'Custom Content'


# ─── Access Tokens ────────────────────────────────────────────────────────────

@admin.register(AccessToken)
class AccessTokenAdmin(admin.ModelAdmin):
    list_display = ('user_name', 'guild', 'created_at', 'expires_at', 'is_valid_display')
    list_filter = ('guild',)
    readonly_fields = ('token', 'created_at')

    def is_valid_display(self, obj):
        return obj.is_valid()
    is_valid_display.boolean = True
    is_valid_display.short_description = 'Valid'
