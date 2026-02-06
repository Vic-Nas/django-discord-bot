import sys

class DebugHostMiddleware:
    """Log incoming Host header to debug ALLOWED_HOSTS issues"""
    
    def __init__(self, get_response):
        print("[DebugHostMiddleware] Initialized", flush=True)
        sys.stdout.flush()
        self.get_response = get_response
    
    def __call__(self, request):
        host = request.META.get('HTTP_HOST', 'NOT_SET')
        print(f"[DebugHostMiddleware] Incoming Host header: {host}", flush=True)
        print(f"[DebugHostMiddleware] ALLOWED_HOSTS: {__import__('django.conf').conf.settings.ALLOWED_HOSTS}", flush=True)
        sys.stdout.flush()
        return self.get_response(request)
