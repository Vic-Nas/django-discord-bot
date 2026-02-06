from django.contrib import admin
from django.urls import path
from core import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('health', views.health_check, name='health_check'),
    path('auth/login/', views.token_login, name='token_login'),
    path('', views.home, name='home'),
]
