from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from core import views

def favicon(request):
    """Serve favicon.png from static files"""
    return serve(request, 'favicon.png', document_root=settings.STATIC_ROOT)

urlpatterns = [
    path('favicon.png', favicon),
    path('favicon.ico', favicon),  # Browsers often request .ico
    path('admin/', admin.site.urls),
    path('ping', views.ping, name='ping'),
    path('health', views.health_check, name='health_check'),
    path('healthz', views.health_check, name='healthz'),
    path('_health', views.health_check, name='alternate_health'),
    path('auth/login/', views.token_login, name='token_login'),
    path('form/<int:guild_id>/', views.form_view, name='form'),
    path('', views.home, name='home'),
]

# Serve static files
if settings.DEBUG or True:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
