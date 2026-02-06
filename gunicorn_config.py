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

