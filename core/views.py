from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.http import HttpResponseForbidden, HttpResponse, JsonResponse
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

