from django.contrib import admin
from django.urls import path
from core import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('ping', views.ping, name='ping'),
    path('health', views.health_check, name='health_check'),
    path('healthz', views.health_check, name='healthz'),  # Alternative health check path
    path('_health', views.health_check, name='alternate_health'),  # Another alternative
    path('auth/login/', views.token_login, name='token_login'),
    path('', views.home, name='home'),
]
