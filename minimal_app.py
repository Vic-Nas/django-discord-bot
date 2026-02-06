"""
Minimal WSGI application for testing Railway deployment
"""
import sys
import os

def application(environ, start_response):
    path = environ['PATH_INFO']
    method = environ['REQUEST_METHOD']
    
    print(f"[MINIMAL_APP] {method} {path}", flush=True)
    sys.stdout.flush()
    
    if path == '/health' or path == '/healthz' or path == '/_health':
        response = b'{"status":"healthy"}'
        status = '200 OK'
        headers = [('Content-Type', 'application/json'), ('Content-Length', str(len(response)))]
    else:
        response = b'pong'
        status = '200 OK'
        headers = [('Content-Type', 'text/plain'), ('Content-Length', str(len(response)))]
    
    start_response(status, headers)
    return [response]
