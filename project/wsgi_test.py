"""
Ultra-minimal WSGI app to test if gunicorn/port binding works
"""
import os
import sys

def test_app(environ, start_response):
    """Minimal WSGI app that just returns 'OK'"""
    status = '200 OK'
    response_headers = [('Content-Type', 'text/plain')]
    start_response(status, response_headers)
    return [b'OK - gunicorn is working']

def application(environ, start_response):
    """Try to load Django, fall back to test app if it fails"""
    try:
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project.settings')
        from django.core.wsgi import get_wsgi_application
        django_app = get_wsgi_application()
        return django_app(environ, start_response)
    except Exception as e:
        print(f"[WSGI] Failed to load Django: {e}", flush=True)
        print(f"[WSGI] Error type: {type(e).__name__}", flush=True)
        import traceback
        traceback.print_exc()
        sys.stdout.flush()
        sys.stderr.flush()
        # Return error response
        status = '500 Internal Server Error'
        response_headers = [('Content-Type', 'text/plain')]
        start_response(status, response_headers)
        return [f"Django load failed: {e}".encode()]
