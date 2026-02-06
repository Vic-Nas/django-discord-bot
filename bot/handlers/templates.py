from core.models import MessageTemplate, GuildMessageTemplate


# Default templates
DEFAULT_TEMPLATES = {
    'INSTALL_WELCOME': """🤖 **Bot installed successfully!**

✅ Created roles: {bot_admin}, {pending}
✅ Created channel: {logs}

📝 **Next steps:**
1. Assign {bot_admin} role to your admins
2. DM me `{bot_mention} getaccess` to access the web panel
3. Configure your server mode (AUTO or APPROVAL)

💡 You can rename these roles/channels - I track them by ID!""",

    'JOIN_LOG_AUTO': """🔥 **New Member Joined**

👤 **User:** {user}
🔗 **Invite:** `{invite_code}`
👥 **Invited by:** {inviter}
✅ **Roles Assigned:** {roles}""",

    'JOIN_LOG_APPROVAL': """🔥 **New Member Joined (Pending Approval)**

👤 **User:** {user}
🔗 **Invite:** `{invite_code}`
👥 **Invited by:** {inviter}
⏳ **Status:** Awaiting application review
🏷️ **Role:** {pending}""",

    'APPLICATION_SENT': """✅ **Application Submitted!**

Thank you for applying to **{server}**!

Your application is now pending review. Server admins will review it soon.
You'll receive a DM when there's an update.

⏳ Please be patient!""",

    'APPLICATION_APPROVED': """🎉 **Application Approved!**

Congratulations! Your application to **{server}** has been approved.

✅ **Roles assigned:** {roles}

Welcome to the server!""",

    'APPLICATION_REJECTED': """❌ **Application Rejected**

Unfortunately, your application to **{server}** was not approved at this time.

{reason}

You may reapply in the future if server rules allow.""",

    'APPROVAL_NOTIFICATION': """📋 **New Application**

👤 **User:** {user}
🔗 **Invite:** `{invite_code}`
👥 **Invited by:** {inviter}

**Responses:**
{responses}

✅ React with ✅ to approve
❌ React with ❌ to reject""",

    'GETACCESS_RESPONSE': """🔑 **Admin Panel Access**

Here's your access link:
{url}

⏰ **Expires:** {expires}

Click the link to access the admin panel. Keep this link private!""",

    'GETACCESS_EXISTS': """🔑 **You already have an active token!**

{url}

⏰ **Expires:** {expires}""",

    'HELP_MESSAGE': """🤖 **Bot Commands**

{commands}

💡 Use {bot_mention} <command> to run commands""",

    'COMMAND_SUCCESS': """✅ **Success!**

{message}""",

    'COMMAND_ERROR': """❌ **Error**

{message}""",
}


def get_template(guild_settings, template_type):
    """Get template for guild (custom or default)"""
    
    # Try to get custom template
    try:
        custom = GuildMessageTemplate.objects.get(
            guild=guild_settings,
            template__template_type=template_type
        )
        return custom.custom_content
    except GuildMessageTemplate.DoesNotExist:
        pass
    
    # Try to get default template
    try:
        template = MessageTemplate.objects.get(template_type=template_type)
        return template.default_content
    except MessageTemplate.DoesNotExist:
        pass
    
    # Fallback to hardcoded default
    return DEFAULT_TEMPLATES.get(template_type, "{message}")


def init_default_templates():
    """Initialize default templates in database (call during setup)"""
    for template_type, content in DEFAULT_TEMPLATES.items():
        MessageTemplate.objects.get_or_create(
            template_type=template_type,
            defaults={'default_content': content}
        )
