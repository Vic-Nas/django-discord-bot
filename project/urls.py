from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from core import views

def favicon(request):
    """Serve favicon.png directly without relying on static files"""
    return serve(request, 'favicon.png', document_root=settings.STATIC_ROOT)

urlpatterns = [
    path('favicon.png', favicon),
    path('favicon.ico', favicon),  # Browser looks for .ico, but we serve .png
    path('admin/', admin.site.urls),
    path('ping', views.ping, name='ping'),
    path('health', views.health_check, name='health_check'),
    path('healthz', views.health_check, name='healthz'),  # Alternative health check path
    path('_health', views.health_check, name='alternate_health'),  # Another alternative
    path('auth/login/', views.token_login, name='token_login'),
    path('', views.home, name='home'),
]

# Serve static files in development and production
if settings.DEBUG or True:  # Always serve static files
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
