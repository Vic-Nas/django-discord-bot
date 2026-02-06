import os
import sys
from django.core.wsgi import get_wsgi_application

print("[WSGI] Starting WSGI initialization", flush=True)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project.settings')

print("[WSGI] Environment set", flush=True)
sys.stdout.flush()
sys.stderr.flush()

print("[WSGI] About to call get_wsgi_application()", flush=True)
sys.stdout.flush()
sys.stderr.flush()

try:
    application = get_wsgi_application()
    print("[WSGI] get_wsgi_application() returned successfully", flush=True)
    sys.stdout.flush()
    sys.stderr.flush()
except Exception as e:
    print(f"[WSGI] ERROR in get_wsgi_application(): {e}", flush=True)
    sys.stdout.flush()
    sys.stderr.flush()
    raise

print("[WSGI] WSGI application loaded successfully", flush=True)
sys.stdout.flush()
sys.stderr.flush()
