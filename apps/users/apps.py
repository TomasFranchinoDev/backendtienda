from django.apps import AppConfig

class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.users'  # <--- ANTES DECÍA SOLO 'users', CÁMBIALO A 'apps.users'
