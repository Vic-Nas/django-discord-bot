import sys
import os
import threading

# Gunicorn configuration with proper worker fork handling
workers = 1
worker_class = 'sync'
bind = '0.0.0.0:' + os.environ.get('PORT', '8000')
timeout = 60
accesslog = '-'
errorlog = '-'
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s'


def when_ready(server):
    """Called when the master initializes"""
    print("[GUNICORN] Master initialized - accepting connections", flush=True)
    sys.stdout.flush()
    sys.stderr.flush()


def worker_int(worker):
    """Called when worker receives SIGINT"""
    print(f"[GUNICORN] Worker {worker.pid} received SIGINT", flush=True)
    sys.stdout.flush()
    sys.stderr.flush()


def worker_abort(worker):
    """Called when worker is aborted"""
    print(f"[GUNICORN] Worker {worker.pid} aborted", flush=True)
    sys.stdout.flush()
    sys.stderr.flush()


