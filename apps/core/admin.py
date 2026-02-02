from django.contrib import admin
from .models import ShopConfig

@admin.register(ShopConfig)
class ShopConfigAdmin(admin.ModelAdmin):
    list_display = ('site_name', 'contact_email')
    
    # Lógica Singleton: Si ya existe 1 configuración, no dejar crear otra.
    def has_add_permission(self, request):
        if self.model.objects.exists():
            return False
        return super().has_add_permission(request)