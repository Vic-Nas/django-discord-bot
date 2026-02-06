"""
Ultra-minimal WSGI app to test if gunicorn/port binding works
"""
import sys
import os

print("[WSGI_TEST] Module loaded", flush=True)
sys.stdout.flush()

def application(environ, start_response):
    """Minimal WSGI app that just returns 'OK'"""
    print(f"[WSGI_TEST] Request received: {environ.get('REQUEST_METHOD')} {environ.get('PATH_INFO')}", flush=True)
    sys.stdout.flush()
    
    path = environ.get('PATH_INFO', '/')
    
    if path == '/ping':
        status = '200 OK'
        response_headers = [('Content-Type', 'text/plain')]
        start_response(status, response_headers)
        return [b'pong']
    
    status = '200 OK'
    response_headers = [('Content-Type', 'text/plain')]
    start_response(status, response_headers)
    return [b'OK - gunicorn is working']

print("[WSGI_TEST] Application function defined", flush=True)
sys.stdout.flush()

