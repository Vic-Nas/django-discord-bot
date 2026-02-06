from django.contrib import admin
from django.urls import path
from core import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('health', views.health_check, name='health_check'),
    path('ping', views.ping, name='ping'),
    path('auth/login/', views.token_login, name='token_login'),
    path('', views.home, name='home'),
]
