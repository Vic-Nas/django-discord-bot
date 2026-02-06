from django.apps import AppConfig
import sys


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'
    
    def ready(self):
        print("[DJANGO_APP] CoreConfig.ready() called", flush=True)
        sys.stdout.flush()
        print("[DJANGO_APP] CoreConfig initialization complete", flush=True)
        sys.stdout.flush()
