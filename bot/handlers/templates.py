from core.models import MessageTemplate, GuildMessageTemplate
from asgiref.sync import sync_to_async


# Default templates
DEFAULT_TEMPLATES = {
    'INSTALL_WELCOME': """🤖 **Bot installed successfully!**

✅ Created roles: {bot_admin}, {pending}
✅ Created channel: {logs}

📝 **Next steps:**
1. Assign {bot_admin} role to your admins
2. DM me `@myusername getaccess` to access the web panel
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

    'PENDING_CHANNEL_TOPIC': """Welcome! Please fill out the application form to get started: {form_url}""",

    'PENDING_CHANNEL_TOPIC_NO_FORM': """Welcome! Please wait for an admin to review your join request.""",

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

    'APPROVE_CONFIRM': """✅ Approved **{user}**. Roles assigned: {roles}""",

    'APPROVE_DM': """✅ Your application in **{server}** has been approved! Roles assigned: {roles}""",

    'REJECT_CONFIRM': """❌ Rejected **{user}**. Reason: {reason}""",

    'REJECT_DM': """❌ Your application in **{server}** has been rejected.
Reason: {reason}""",

    'REJECT_PENDING': """❌ {user}, your application has been rejected.
**Reason:** {reason}""",

    'APPROVAL_NOTIFICATION': """📋 **New Application**

👤 **User:** {user}
🔗 **Invite:** `{invite_code}`
👥 **Invited by:** {inviter}

**Responses:**
{responses}

✅ `@Bot approve {user_mention} role1,role2`
❌ `@Bot reject {user_mention} [reason]`""",

    'GETACCESS_RESPONSE': """🔑 Access token for **{server}**:
[Admin Panel]({url})
Expires: {expires}""",

    'GETACCESS_EXISTS': """🔑 You already have an active token for **{server}**:
[Admin Panel]({url})
Expires: {expires}""",

    'GETACCESS_NO_ADMIN': """⚠️ You are not a BotAdmin in any server I'm in.""",

    'GETACCESS_PICK_SERVER': """You are a BotAdmin in multiple servers. Reply with the number:
{guild_list}""",

    'HELP_MESSAGE': """🤖 **Bot Commands**

{commands}

💡 Use {bot_mention} <command> to run commands""",

    'COMMAND_SUCCESS': """✅ **Success!**

{message}""",

    'COMMAND_ERROR': """❌ **Error**

{message}""",

    'COMMAND_NOT_FOUND': """❌ Command `{command}` not found.

📋 **Available commands:** {commands}""",

    'COMMAND_DISABLED': """❌ Command `{command}` is disabled on this server.""",

    'DM_ONLY_WARNING': """⚠️ This command only works in DMs. Please send me a direct message!""",

    'SERVER_ONLY_WARNING': """❌ Commands only work in servers. Use `getaccess` in DMs for web panel access.""",

    'SETUP_DIAGNOSTIC': """⚠️ **Setup Issue Detected**

I couldn't assign the BotAdmin role to myself. My role is: **{bot_role}**

**Possible fixes:**
1. **Role Hierarchy**: In Server Settings → Roles, make sure my role (**{bot_role}**) is positioned **above** BotAdmin in the hierarchy
2. **Permissions**: Make sure I have the "Manage Roles" permission
3. **Re-add the bot**: Kick me from the server and add me back (this might trigger a fresh setup)

I need this to manage BotAdmin role assignments and channel permissions.""",
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


async def get_template_async(guild_settings, template_type):
    """Async wrapper for get_template"""
    return await sync_to_async(get_template)(guild_settings, template_type)


def init_default_templates():
    """Initialize default templates in database (call during setup)"""
    for template_type, content in DEFAULT_TEMPLATES.items():
        MessageTemplate.objects.get_or_create(
            template_type=template_type,
            defaults={'default_content': content}
        )
