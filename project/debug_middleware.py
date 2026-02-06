import sys
import logging

logger = logging.getLogger(__name__)


class DebugRequestMiddleware:
    """Log all incoming requests for debugging"""
    
    def __init__(self, get_response):
        print("[MIDDLEWARE] DebugRequestMiddleware initialized", flush=True)
        sys.stdout.flush()
        self.get_response = get_response
    
    def __call__(self, request):
        print(f"[REQUEST] Incoming request: {request.method} {request.path}", flush=True)
        sys.stdout.flush()
        
        try:
            response = self.get_response(request)
            print(f"[REQUEST] Response: {response.status_code} for {request.path}", flush=True)
            sys.stdout.flush()
            return response
        except Exception as e:
            print(f"[REQUEST] Exception in request handling: {e}", flush=True)
            sys.stdout.flush()
            raise
