import sys
import os

# Gunicorn configuration with proper worker fork handling
workers = 1
worker_class = 'sync'
bind = '0.0.0.0:' + os.environ.get('PORT', '8000')
timeout = 60
accesslog = '-'
errorlog = '-'
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s'


def post_fork(server, worker):
    """Reset database connections after worker fork"""
    print(f"[GUNICORN] post_fork called for worker {worker.pid}", flush=True)
    sys.stdout.flush()
    sys.stderr.flush()
    
    # Close any database connections from parent process
    from django.db import connections
    
    print("[GUNICORN] Closing parent database connections", flush=True)
    sys.stdout.flush()
    
    for conn in connections.all():
        conn.close()
    
    print("[GUNICORN] post_fork handler complete", flush=True)
    sys.stdout.flush()
    sys.stderr.flush()
