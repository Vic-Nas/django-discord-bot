from django.contrib import admin
from .models import (
    GuildSettings, DiscordRole, DiscordChannel, InviteRule,
    FormField, Application, BotCommand, CommandAction,
    MessageTemplate, GuildMessageTemplate, AccessToken
)

# Customize admin site
admin.site.site_header = "Discord Bot Admin"
admin.site.site_title = "Bot Management"
admin.site.index_title = "Dashboard"


class CommandActionInline(admin.TabularInline):
    """Inline editor for actions within a command"""
    model = CommandAction
    fields = ('order', 'name', 'type', 'enabled', 'parameters')
    extra = 1


class BotCommandAdmin(admin.ModelAdmin):
    """Custom admin for BotCommand to show inline actions"""
    list_display = ('name', 'guild', 'description', 'enabled')
    list_filter = ('guild', 'enabled')
    search_fields = ('name', 'description')
    inlines = [CommandActionInline]


admin.site.register(GuildSettings)
admin.site.register(DiscordRole)
admin.site.register(DiscordChannel)
admin.site.register(InviteRule)
admin.site.register(FormField)
admin.site.register(Application)
admin.site.register(BotCommand, BotCommandAdmin)
admin.site.register(CommandAction)
admin.site.register(MessageTemplate)
admin.site.register(GuildMessageTemplate)
admin.site.register(AccessToken)
