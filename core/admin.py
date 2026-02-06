from django.contrib import admin
from .models import (
    GuildSettings, DiscordRole, DiscordChannel, InviteRule,
    FormField, Application, BotCommand,
    MessageTemplate, GuildMessageTemplate, AccessToken
)

# Customize admin site
admin.site.site_header = "Discord Bot Admin"
admin.site.site_title = "Bot Management"
admin.site.index_title = "Dashboard"

admin.site.register(GuildSettings)
admin.site.register(DiscordRole)
admin.site.register(DiscordChannel)
admin.site.register(InviteRule)
admin.site.register(FormField)
admin.site.register(Application)
admin.site.register(BotCommand)
admin.site.register(MessageTemplate)
admin.site.register(GuildMessageTemplate)
admin.site.register(AccessToken)
