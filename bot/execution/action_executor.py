"""
ExecutionEngine for CommandActions

Reads CommandActions from database and executes them sequentially.
Each action type (SEND_MESSAGE, ASSIGN_ROLE, etc) is executed with parameters from JSON.
"""

import json
import discord
from asgiref.sync import sync_to_async


class ExecutionError(Exception):
    """Raised when an action fails to execute"""
    pass


async def execute_command_actions(bot, message, command_obj):
    """
    Execute all CommandActions for a BotCommand in order.
    
    Args:
        bot: discord.py Bot instance
        message: discord.Message that triggered the command
        command_obj: BotCommand instance from database
    
    Returns:
        List of (success: bool, message: str) tuples for each action
    """
    
    results = []
    
    # Get all actions ordered by order field
    actions = await sync_to_async(
        lambda: list(command_obj.actions.filter(enabled=True).order_by('order'))
    )()
    
    if not actions:
        await message.channel.send(f"⚠️ Command `{command_obj.name}` has no actions configured.")
        return results
    
    # Execute each action
    for action in actions:
        try:
            await execute_single_action(bot, message, action)
            results.append((True, f"✅ {action.name}"))
        except ExecutionError as e:
            results.append((False, f"❌ {action.name}: {str(e)}"))
            # Continue to next action even if one fails
        except Exception as e:
            results.append((False, f"❌ {action.name}: Unexpected error: {str(e)}"))
    
    return results


async def execute_single_action(bot, message, action_obj):
    """
    Execute a single CommandAction.
    
    Args:
        bot: discord.py Bot instance
        message: discord.Message that triggered the command
        action_obj: CommandAction instance
        
    Raises:
        ExecutionError: If action fails
    """
    
    action_type = action_obj.type
    params = action_obj.parameters or {}
    
    # Route to appropriate handler based on action type string
    if action_type == 'SEND_MESSAGE':
        await handle_send_message(bot, message, params)
    
    elif action_type == 'ASSIGN_ROLE':
        await handle_assign_role(bot, message, params)
    
    elif action_type == 'REMOVE_ROLE':
        await handle_remove_role(bot, message, params)
    
    elif action_type == 'CREATE_CHANNEL':
        await handle_create_channel(bot, message, params)
    
    elif action_type == 'DELETE_CHANNEL':
        await handle_delete_channel(bot, message, params)
    
    elif action_type == 'POLL':
        await handle_poll(bot, message, params)
    
    elif action_type == 'WEBHOOK':
        await handle_webhook(bot, message, params)
    
    else:
        raise ExecutionError(f"Unknown action type: {action_type}")


async def handle_send_message(bot, message, params):
    """SEND_MESSAGE: Send a message to a channel"""
    
    if not params or 'text' not in params:
        raise ExecutionError("Missing 'text' parameter")
    
    text = params.get('text', '')
    channel_id = params.get('channel_id')  # If None, use current channel
    
    target_channel = None
    if channel_id:
        target_channel = bot.get_channel(int(channel_id))
        if not target_channel:
            raise ExecutionError(f"Channel {channel_id} not found")
    else:
        target_channel = message.channel
    
    if not text.strip():
        raise ExecutionError("Message text is empty")
    
    try:
        await target_channel.send(text)
    except discord.Forbidden:
        raise ExecutionError(f"No permission to send message to {target_channel.mention}")
    except discord.HTTPException as e:
        raise ExecutionError(f"Failed to send message: {str(e)}")


async def handle_assign_role(bot, message, params):
    """ASSIGN_ROLE: Assign a role to the user"""
    
    if not params or 'role_id' not in params:
        raise ExecutionError("Missing 'role_id' parameter")
    
    role_id = int(params.get('role_id'))
    target_member = params.get('target_user_id')
    
    # If no target user specified, assign to command invoker
    if target_member:
        try:
            member = await message.guild.fetch_member(int(target_member))
        except discord.NotFound:
            raise ExecutionError(f"User {target_member} not found in this server")
    else:
        member = message.author
    
    role = message.guild.get_role(role_id)
    if not role:
        raise ExecutionError(f"Role {role_id} not found in this server")
    
    if role in member.roles:
        raise ExecutionError(f"{member.mention} already has role {role.mention}")
    
    try:
        await member.add_roles(role)
    except discord.Forbidden:
        raise ExecutionError(f"Bot doesn't have permission to assign {role.mention}")
    except discord.HTTPException as e:
        raise ExecutionError(f"Failed to assign role: {str(e)}")


async def handle_remove_role(bot, message, params):
    """REMOVE_ROLE: Remove a role from the user"""
    
    if not params or 'role_id' not in params:
        raise ExecutionError("Missing 'role_id' parameter")
    
    role_id = int(params.get('role_id'))
    target_member = params.get('target_user_id')
    
    # If no target user specified, remove from command invoker
    if target_member:
        try:
            member = await message.guild.fetch_member(int(target_member))
        except discord.NotFound:
            raise ExecutionError(f"User {target_member} not found in this server")
    else:
        member = message.author
    
    role = message.guild.get_role(role_id)
    if not role:
        raise ExecutionError(f"Role {role_id} not found in this server")
    
    if role not in member.roles:
        raise ExecutionError(f"{member.mention} doesn't have role {role.mention}")
    
    try:
        await member.remove_roles(role)
    except discord.Forbidden:
        raise ExecutionError(f"Bot doesn't have permission to remove {role.mention}")
    except discord.HTTPException as e:
        raise ExecutionError(f"Failed to remove role: {str(e)}")


async def handle_create_channel(bot, message, params):
    """CREATE_CHANNEL: Create a new text channel"""
    
    if not params or 'name' not in params:
        raise ExecutionError("Missing 'name' parameter")
    
    channel_name = params.get('name', '').strip()
    
    if not channel_name:
        raise ExecutionError("Channel name is empty")
    
    # Validate channel name (Discord requirements)
    if len(channel_name) > 100:
        raise ExecutionError("Channel name too long (max 100 chars)")
    
    try:
        new_channel = await message.guild.create_text_channel(channel_name)
    except discord.Forbidden:
        raise ExecutionError("Bot doesn't have permission to create channels")
    except discord.HTTPException as e:
        raise ExecutionError(f"Failed to create channel: {str(e)}")


async def handle_delete_channel(bot, message, params):
    """DELETE_CHANNEL: Delete a channel"""
    
    if not params or 'channel_id' not in params:
        raise ExecutionError("Missing 'channel_id' parameter")
    
    channel_id = int(params.get('channel_id'))
    channel = bot.get_channel(channel_id)
    
    if not channel:
        raise ExecutionError(f"Channel {channel_id} not found")
    
    if channel.guild.id != message.guild.id:
        raise ExecutionError("Channel is not in this server")
    
    try:
        await channel.delete()
    except discord.Forbidden:
        raise ExecutionError("Bot doesn't have permission to delete this channel")
    except discord.HTTPException as e:
        raise ExecutionError(f"Failed to delete channel: {str(e)}")


async def handle_poll(bot, message, params):
    """POLL: Create a poll with reactions"""
    
    if not params or 'question' not in params:
        raise ExecutionError("Missing 'question' parameter")
    
    question = params.get('question', '').strip()
    options = params.get('options', [])  # List of option strings
    
    if not question:
        raise ExecutionError("Poll question is empty")
    
    if not options or len(options) < 2:
        raise ExecutionError("Poll needs at least 2 options")
    
    # Build poll message
    poll_text = f"📊 **{question}**\n\n"
    emojis = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']
    
    for i, option in enumerate(options[:len(emojis)]):
        poll_text += f"{emojis[i]} {option}\n"
    
    try:
        poll_msg = await message.channel.send(poll_text)
        
        # Add reactions
        for i in range(len(options)):
            await poll_msg.add_reaction(emojis[i])
    
    except discord.Forbidden:
        raise ExecutionError("Bot doesn't have permission to send or react to messages")
    except discord.HTTPException as e:
        raise ExecutionError(f"Failed to create poll: {str(e)}")


async def handle_webhook(bot, message, params):
    """WEBHOOK: Send message to external webhook"""
    
    if not params or 'webhook_url' not in params:
        raise ExecutionError("Missing 'webhook_url' parameter")
    
    webhook_url = params.get('webhook_url', '').strip()
    text = params.get('text', '').strip()
    
    if not webhook_url:
        raise ExecutionError("Webhook URL is empty")
    
    if not text:
        raise ExecutionError("Webhook message text is empty")
    
    # Note: Actual webhook execution would require aiohttp or requests
    # For now, just validate and log
    if not webhook_url.startswith('http'):
        raise ExecutionError("Invalid webhook URL")
    
    # In production, implement actual HTTP POST here
    # import aiohttp
    # async with aiohttp.ClientSession() as session:
    #     await session.post(webhook_url, json={'content': text})
    
    raise ExecutionError("Webhook execution not yet implemented")
