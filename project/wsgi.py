import os
import sys
import signal
import time
from django.core.wsgi import get_wsgi_application

# Install signal handlers FIRST
def handle_signal(signum, frame):
    sig_name = signal.Signals(signum).name
    print(f"[WSGI] Received signal {sig_name} ({signum})", flush=True)
    sys.stdout.flush()
    sys.stderr.flush()

signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)

wsgi_start = time.time()
print(f"[WSGI] Starting WSGI initialization at {wsgi_start}", flush=True)

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

get_wsgi_start = time.time()
try:
    application = get_wsgi_application()
    signal.alarm(0)  # Cancel alarm
    get_wsgi_time = time.time() - get_wsgi_start
    print(f"[WSGI] get_wsgi_application() took {get_wsgi_time:.2f}s", flush=True)
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


class SimpleLogMiddleware:
    """Minimal middleware just for logging"""
    
    def __init__(self, wsgi_app):
        print("[WSGI_APP] SimpleLogMiddleware initialized", flush=True)
        sys.stdout.flush()
        self.wsgi_app = wsgi_app
    
    def __call__(self, environ, start_response):
        try:
            return self.wsgi_app(environ, start_response)
        except Exception as e:
            print(f"[WSGI_APP] Request failed: {e}", flush=True)
            sys.stdout.flush()
            raise


# Wrap the application
application = SimpleLogMiddleware(application)

wsgi_time = time.time() - wsgi_start
print(f"[WSGI] WSGI application loaded successfully in {wsgi_time:.2f}s total", flush=True)
print("[WSGI] *** WORKER READY TO HANDLE REQUESTS ***", flush=True)
sys.stdout.flush()
sys.stderr.flush()
