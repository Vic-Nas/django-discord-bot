"""
Middleware to catch and log any rejected requests
"""
import sys


class ErrorLoggingMiddleware:
    """Log all exceptions before Django rejects requests"""
    
    def __init__(self, get_response):
        print("[ERROR_LOGGING] ErrorLoggingMiddleware initialized", flush=True)
        sys.stdout.flush()
        self.get_response = get_response
    
    def __call__(self, request):
        try:
            print(f"[ERROR_LOGGING] Request received: {request.method} {request.path} Host: {request.META.get('HTTP_HOST', 'NONE')}", flush=True)
            sys.stdout.flush()
            response = self.get_response(request)
            print(f"[ERROR_LOGGING] Response: {response.status_code}", flush=True)
            sys.stdout.flush()
            return response
        except Exception as e:
            print(f"[ERROR_LOGGING] Exception: {type(e).__name__}: {e}", flush=True)
            print(f"[ERROR_LOGGING] Request Host header: {request.META.get('HTTP_HOST', 'NOT SET')}", flush=True)
            print(f"[ERROR_LOGGING] ALLOWED_HOSTS: {__import__('django.conf').conf.settings.ALLOWED_HOSTS}", flush=True)
            sys.stdout.flush()
            raise
