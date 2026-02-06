import sys
import os
import threading

print(f"[GUNICORN_CONFIG] Loading gunicorn config", flush=True)
print(f"[GUNICORN_CONFIG] PORT env var: {os.environ.get('PORT', 'NOT SET')}", flush=True)
print(f"[GUNICORN_CONFIG] DEBUG env var: {os.environ.get('DEBUG', 'NOT SET')}", flush=True)
sys.stdout.flush()

# Gunicorn configuration with proper worker fork handling
workers = 1
worker_class = 'sync'
port_value = os.environ.get('PORT', '8000')
bind = '0.0.0.0:' + port_value
timeout = 60
accesslog = '-'
errorlog = '-'
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s'

print(f"[GUNICORN_CONFIG] Binding to: {bind}", flush=True)
sys.stdout.flush()


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


