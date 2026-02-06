import os
import sys
import signal
from django.core.wsgi import get_wsgi_application

# Install signal handlers FIRST
def handle_signal(signum, frame):
    sig_name = signal.Signals(signum).name
    print(f"[WSGI] Received signal {sig_name} ({signum})", flush=True)
    sys.stdout.flush()
    sys.stderr.flush()

signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)

print("[WSGI] Starting WSGI initialization", flush=True)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project.settings')

print("[WSGI] Environment set", flush=True)
sys.stdout.flush()
sys.stderr.flush()

print("[WSGI] About to call get_wsgi_application()", flush=True)
sys.stdout.flush()
sys.stderr.flush()

# Set a timeout to catch hangs
def timeout_handler(signum, frame):
    print("[WSGI] TIMEOUT! get_wsgi_application() took too long", flush=True)
    sys.stdout.flush()
    sys.stderr.flush()
    raise TimeoutError("get_wsgi_application() timeout")

signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(30)  # 30 second timeout

try:
    application = get_wsgi_application()
    signal.alarm(0)  # Cancel alarm
    print("[WSGI] get_wsgi_application() returned successfully", flush=True)
    sys.stdout.flush()
    sys.stderr.flush()
except Exception as e:
    signal.alarm(0)  # Cancel alarm
    print(f"[WSGI] ERROR in get_wsgi_application(): {e}", flush=True)
    sys.stdout.flush()
    sys.stderr.flush()
    raise

# Wrap application to reset database connections
from django.db import connections


class DatabaseResetMiddleware:
    """Ensure database connections are properly reset"""
    
    def __init__(self, wsgi_app):
        print("[WSGI_MIDDLEWARE] DatabaseResetMiddleware initialized", flush=True)
        sys.stdout.flush()
        self.wsgi_app = wsgi_app
    
    def __call__(self, environ, start_response):
        path = environ.get('PATH_INFO', '/')
        method = environ.get('REQUEST_METHOD', 'GET')
        print(f"[WSGI_MIDDLEWARE] Request: {method} {path}", flush=True)
        sys.stdout.flush()
        sys.stderr.flush()
        
        try:
            print("[WSGI_MIDDLEWARE] Closing database connections", flush=True)
            sys.stdout.flush()
            
            # Ensure all connections are closed before handling request
            connections.close_all()
            
            print("[WSGI_MIDDLEWARE] Calling wrapped app", flush=True)
            sys.stdout.flush()
            
            result = self.wsgi_app(environ, start_response)
            
            print("[WSGI_MIDDLEWARE] App returned successfully", flush=True)
            sys.stdout.flush()
            
            return result
        except Exception as e:
            print(f"[WSGI_MIDDLEWARE] Exception: {e}", flush=True)
            sys.stdout.flush()
            sys.stderr.flush()
            raise


# Wrap the application
application = DatabaseResetMiddleware(application)

print("[WSGI] WSGI application loaded successfully", flush=True)
sys.stdout.flush()
sys.stderr.flush()
