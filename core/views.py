import os
import json
import urllib.error
import urllib.request

from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.http import HttpResponseForbidden, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import AccessToken, GuildSettings


def health_check(request):
    """Simple health check for Railway - no database access"""
    import sys
    print("[HEALTH_CHECK] Health check endpoint called", flush=True)
    sys.stdout.flush()
    sys.stderr.flush()
    return JsonResponse({'status': 'healthy', 'timestamp': str(__import__('datetime').datetime.now())}, status=200)


def ping(request):
    """Ultra-simple ping endpoint for testing"""
    import sys
    print("[PING] Ping endpoint called", flush=True)
    sys.stdout.flush()
    sys.stderr.flush()
    return HttpResponse('pong')



def token_login(request):
    """Handle token-based authentication from Discord bot"""
    import sys
    print("[TOKEN_LOGIN] Token login view called", flush=True)
    sys.stdout.flush()
    
    token = request.GET.get('token')
    
    if not token:
        return HttpResponseForbidden("No token provided")
    
    try:
        access_token = AccessToken.objects.get(token=token)
        
        if not access_token.is_valid():
            return HttpResponseForbidden("Token expired")
        
        # Get or create Django user for this Discord user
        username = f"discord_{access_token.user_id}"
        user, created = User.objects.get_or_create(
            username=username,
            defaults={'is_staff': True, 'is_superuser': True}
        )
        
        # Log them in
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        
        # Store guild context in session
        request.session['guild_id'] = str(access_token.guild.guild_id)
        request.session['discord_user_id'] = str(access_token.user_id)
        request.session['discord_username'] = access_token.user_name
        
        return redirect('/admin/')
        
    except AccessToken.DoesNotExist:
        return HttpResponseForbidden("Invalid token")


def home(request):
    """Simple home page"""
    return render(request, 'home.html')


# ---------------------------------------------------------------------------
# Application form (public, no login required)
# ---------------------------------------------------------------------------

def _resolve_display_value(field, raw_value):
    """Convert raw response value to a human-readable string.

    For dropdown fields backed by ROLES/CHANNELS, the stored value is a
    discord_id (or comma-separated list). This resolves those IDs to cached
    names so the #approvals embed shows real names instead of numbers.
    """
    from .models import DiscordRole, DiscordChannel

    if not raw_value or raw_value == 'No answer':
        return raw_value

    if field.field_type != 'dropdown' or not field.dropdown:
        return raw_value

    ids = [v.strip() for v in raw_value.split(',') if v.strip()]
    source = field.dropdown.source_type

    if source == 'ROLES':
        names = []
        for rid in ids:
            try:
                role = DiscordRole.objects.get(guild=field.guild, discord_id=int(rid))
                names.append(role.name)
            except (DiscordRole.DoesNotExist, ValueError):
                names.append(rid)
        return ', '.join(names)

    if source == 'CHANNELS':
        names = []
        for cid in ids:
            try:
                ch = DiscordChannel.objects.get(guild=field.guild, discord_id=int(cid))
                names.append(f'#{ch.name}' if ch.name else cid)
            except (DiscordChannel.DoesNotExist, ValueError):
                names.append(cid)
        return ', '.join(names)

    if source == 'CUSTOM':
        option_map = {o.value: o.label for o in field.dropdown.custom_options.all()}
        return ', '.join(option_map.get(v, v) for v in ids)

    return raw_value


def _post_application_embed(guild_settings, application, fields):
    """Post the application embed to the #bounce channel via Discord REST API."""
    channel_id = guild_settings.bounce_channel_id
    if not channel_id:
        print('\u274c No bounce_channel_id set — cannot post application embed')
        return

    token = os.environ.get('DISCORD_TOKEN')
    if not token:
        print('\u274c DISCORD_TOKEN not set — cannot post application embed')
        return

    print(f'\U0001f4e4 Posting application #{application.id} to channel {channel_id}')

    # Build responses text with name resolution
    responses_text = ''
    for field in fields:
        raw = application.responses.get(str(field.id), 'No answer')
        display = _resolve_display_value(field, raw)
        responses_text += f'**{field.label}:** {display}\n'

    embed = {
        'title': f'\U0001f4cb Application #{application.id} \u2014 {application.user_name}',
        'color': 16753920,  # orange
        'fields': [
            {'name': 'User', 'value': f'<@{application.user_id}>', 'inline': True},
            {'name': 'Invite', 'value': application.invite_code or 'N/A', 'inline': True},
            {'name': 'Invited by', 'value': application.inviter_name or 'Unknown', 'inline': True},
        ],
    }

    if responses_text:
        if len(responses_text) > 1024:
            responses_text = responses_text[:1021] + '...'
        embed['fields'].append({'name': 'Responses', 'value': responses_text, 'inline': False})

    embed['fields'].append({
        'name': 'Actions',
        'value': (
            f'\u2705 **@Bot approve** <@{application.user_id}>\n'
            f'\u274c **@Bot reject** <@{application.user_id}> [reason]'
        ),
        'inline': False,
    })

    url = f'https://discord.com/api/v10/channels/{channel_id}/messages'
    data = json.dumps({'embeds': [embed]}).encode()
    req = urllib.request.Request(url, data=data, headers={
        'Authorization': f'Bot {token}',
        'Content-Type': 'application/json',
        'User-Agent': 'DiscordBot (https://github.com/Vic-Nas/django-discord-bot, 1.0)',
    })
    try:
        resp = urllib.request.urlopen(req)
        resp_data = json.loads(resp.read().decode())
        # Save message_id for in-place editing later
        msg_id = resp_data.get('id')
        if msg_id:
            application.message_id = int(msg_id)
            application.save(update_fields=['message_id'])
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors='replace')
        print(f'\u274c Failed to post application embed to Discord: {e} — {body}')
    except Exception as e:
        print(f'\u274c Failed to post application embed to Discord: {e}')


@csrf_exempt
def form_view(request, guild_id):
    """GET  — render the application form (or lookup page if no user param)
    POST — save responses and notify #approvals"""
    from .models import FormField, Application

    # ---- guild check ----
    try:
        guild_settings = GuildSettings.objects.get(guild_id=guild_id)
    except GuildSettings.DoesNotExist:
        return HttpResponse('Server not found.', status=404)

    user_id = request.GET.get('user') or request.POST.get('user_id')
    invite_code = request.GET.get('invite') or request.POST.get('invite_code')

    # ---- lookup flow: no user param ----
    if not user_id:
        if request.method == 'POST' and request.POST.get('lookup_username'):
            # User submitted the lookup form
            username = request.POST.get('lookup_username', '').strip()
            matches = Application.objects.filter(
                guild=guild_settings,
                status='PENDING',
                user_name__icontains=username,
            ).filter(responses={})  # only un-submitted
            if matches.count() == 1:
                app = matches.first()
                # Redirect to the form with the user param
                return redirect(f'/form/{guild_id}/?user={app.user_id}&invite={app.invite_code}')
            elif matches.count() > 1:
                return render(request, 'form_lookup.html', {
                    'guild_name': guild_settings.guild_name,
                    'guild_id': guild_id,
                    'error': 'Multiple pending applications found. Please use your exact Discord username (e.g. myname#1234).',
                })
            else:
                return render(request, 'form_lookup.html', {
                    'guild_name': guild_settings.guild_name,
                    'guild_id': guild_id,
                    'error': 'No pending application found for that username. Make sure you joined the server first.',
                })
        # Show lookup page
        return render(request, 'form_lookup.html', {
            'guild_name': guild_settings.guild_name,
            'guild_id': guild_id,
        })

    # ---- find pending application ----
    try:
        application = Application.objects.get(
            guild=guild_settings,
            user_id=int(user_id),
            status='PENDING',
        )
    except Application.DoesNotExist:
        return HttpResponse(
            'No pending application found. You may have already submitted or your application was processed.',
            status=404,
        )

    # ---- already submitted? ----
    if application.responses:
        return HttpResponse(
            'Your application has already been submitted. Please wait for an admin to review it.',
        )

    # ---- form fields ----
    fields = list(
        FormField.objects.select_related('dropdown').filter(guild=guild_settings).order_by('order')
    )
    if not fields:
        return HttpResponse('No form fields configured for this server.', status=404)

    # Prepare template-friendly data
    field_data = []
    for f in fields:
        fd = {
            'id': f.id,
            'label': f.label,
            'field_type': f.field_type,
            'required': f.required,
            'placeholder': f.placeholder or '',
            'options': [],
            'multiselect': False,
        }
        if f.field_type == 'dropdown' and f.dropdown:
            fd['options'] = f.dropdown.get_options()
            fd['multiselect'] = f.dropdown.multiselect
        field_data.append(fd)

    # ---- POST: save + notify ----
    if request.method == 'POST':
        responses = {}
        for f in fields:
            key = f'field_{f.id}'
            if f.field_type == 'dropdown' and f.dropdown and f.dropdown.multiselect:
                values = request.POST.getlist(key)
                responses[str(f.id)] = ','.join(values)
            elif f.field_type == 'checkbox':
                responses[str(f.id)] = 'Yes' if request.POST.get(key) else 'No'
            else:
                responses[str(f.id)] = request.POST.get(key, '')

        # Validate required
        missing = []
        for f in fields:
            if f.required:
                val = responses.get(str(f.id), '')
                if not val or val == 'No answer':
                    missing.append(f.label)
        if missing:
            return render(request, 'form.html', {
                'guild_name': guild_settings.guild_name,
                'fields': field_data,
                'guild_id': guild_id,
                'user_id': user_id,
                'invite_code': invite_code or '',
                'error': f'Please fill in: {", ".join(missing)}',
            })

        application.responses = responses
        application.save()

        # Post to #approvals via Discord REST API
        _post_application_embed(guild_settings, application, fields)

        return render(request, 'form_success.html', {'guild_name': guild_settings.guild_name})

    # ---- GET: render form ----
    return render(request, 'form.html', {
        'guild_name': guild_settings.guild_name,
        'fields': field_data,
        'guild_id': guild_id,
        'user_id': user_id,
        'invite_code': invite_code or '',
    })


