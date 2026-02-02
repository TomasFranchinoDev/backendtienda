from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from django.utils import timezone
from .models import User, PasswordResetToken

# Extendemos la configuración visual base de Django para incluir nuestros campos
class CustomUserAdmin(UserAdmin):
    model = User
    # Agregamos 'phone_number' a la lista de campos visibles en el admin
    list_display = ['email', 'username', 'phone_number', 'is_staff']
    
    # Agregamos el campo al formulario de edición
    fieldsets = UserAdmin.fieldsets + (
        ('Información Extra', {'fields': ('phone_number', 'is_verified')}),
    )

admin.site.register(User, CustomUserAdmin)


class PasswordResetTokenAdmin(admin.ModelAdmin):
    """
    Admin para gestionar tokens de recuperación de contraseña.
    
    SEGURIDAD:
    - No mostramos el token completo en lista (solo primeros 10 caracteres)
    - Marcar como solo lectura en la mayoría de campos
    - Permitir marcar como usado manualmente
    - Filtrar por estado (usado/no usado, expirado/vigente)
    """
    
    list_display = [
        'user_email',
        'token_preview',
        'created_at',
        'expires_at',
        'status_badge',
        'used_at'
    ]
    
    list_filter = ['used', 'created_at', 'expires_at']
    search_fields = ['user__email', 'token']
    readonly_fields = ['token', 'created_at', 'expires_at', 'used_at', 'token_display']
    
    fieldsets = (
        ('Información del Usuario', {
            'fields': ('user',)
        }),
        ('Token', {
            'fields': ('token_display', 'token'),
            'classes': ('collapse',),  # Campo oculto por defecto
            'description': 'No compartir este token'
        }),
        ('Fechas', {
            'fields': ('created_at', 'expires_at', 'used_at')
        }),
        ('Estado', {
            'fields': ('used',)
        }),
    )
    
    def user_email(self, obj):
        """Mostrar email del usuario."""
        return obj.user.email
    user_email.short_description = 'Usuario'
    
    def token_preview(self, obj):
        """Mostrar solo primeros caracteres del token."""
        return f"{obj.token[:10]}..." if obj.token else "-"
    token_preview.short_description = 'Token (primeros caracteres)'
    
    def token_display(self, obj):
        """Mostrar token completo en readonly."""
        return f"<code>{obj.token}</code>" if obj.token else "-"
    token_display.allow_tags = True
    token_display.short_description = 'Token Completo'
    
    def status_badge(self, obj):
        """Mostrar estado visual del token."""
        if obj.used:
            return format_html(
                '<span style="background-color: #ccc; color: #666; padding: 3px 8px; border-radius: 3px;">Usado</span>'
            )
        elif timezone.now() > obj.expires_at:
            return format_html(
                '<span style="background-color: #ff6b6b; color: white; padding: 3px 8px; border-radius: 3px;">Expirado</span>'
            )
        else:
            return format_html(
                '<span style="background-color: #51cf66; color: white; padding: 3px 8px; border-radius: 3px;">Vigente</span>'
            )
    status_badge.short_description = 'Estado'
    
    def has_add_permission(self, request):
        """No permitir crear tokens desde admin (solo desde endpoint)."""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Permitir eliminar tokens (limpieza manual)."""
        return True

admin.site.register(PasswordResetToken, PasswordResetTokenAdmin)
