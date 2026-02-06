import os
import sys
from django.core.wsgi import get_wsgi_application

print("[WSGI] Starting WSGI initialization", flush=True)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project.settings')

print("[WSGI] Calling get_wsgi_application()", flush=True)
sys.stdout.flush()
sys.stderr.flush()

application = get_wsgi_application()

print("[WSGI] WSGI application loaded successfully", flush=True)
sys.stdout.flush()
sys.stderr.flush()
