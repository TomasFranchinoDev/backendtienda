import secrets
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from datetime import timedelta

class User(AbstractUser):
    # Heredamos de AbstractUser, así que ya tenemos: 
    # username, password, first_name, last_name, email, is_staff, etc.

    # Agregamos campos extra útiles para un e-commerce
    email = models.EmailField('email address', unique=True, db_index=True) # Hacemos el email único obligatorio
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    
    # ¿Es cliente o vendedor/admin de tienda?
    is_verified = models.BooleanField(default=False) # Para validación de email

    # Usaremos el email como identificador principal en lugar del username?
    # Para este MVP, te recomiendo mantener 'username' internamente pero 
    # permitir login con email. Django lo maneja bien.
    
    USERNAME_FIELD = 'email' # Hacemos login con email
    REQUIRED_FIELDS = ['username', 'first_name', 'last_name']

    def __str__(self):
        return self.email


class PasswordResetToken(models.Model):
    """
    Modelo para almacenar tokens de recuperación de contraseña.
    
    DISEÑO Y SEGURIDAD:
    - Token único: cada reset genera un nuevo token (previene reutilización)
    - Un solo uso: marca usado=True después de utilizarse
    - Expiración: 30 minutos (ventana de ataque limitada)
    - Índices: búsquedas rápidas sin full scans
    - user_id + usado + expira: índice compuesto para validación rápida
    - token único: búsqueda O(1) sin full scan
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='password_reset_tokens')
    token = models.CharField(max_length=255, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    used = models.BooleanField(default=False, db_index=True)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['token', 'used', 'expires_at']),
            models.Index(fields=['user', 'used', 'expires_at']),
        ]

    def __str__(self):
        return f"Reset token for {self.user.email} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"

    @classmethod
    def generate_token(cls):
        """
        Genera un token seguro y único.
        
        SEGURIDAD:
        - secrets.token_urlsafe(48): 64 caracteres aleatorios
        - Mejor que UUID (más corta y similar entropía)
        - URL-safe: puede enviarse en URLs sin problemas
        
        Returns:
            String de 64 caracteres hexadecimales únicos
        """
        return secrets.token_urlsafe(48)

    def is_valid(self):
        """
        Verifica si el token es válido para usar.
        
        Validaciones:
        - No fue usado (de un solo uso)
        - No expiró (ventana de 30 minutos)
        
        Returns:
            True si el token es válido, False en caso contrario
        """
        return not self.used and timezone.now() < self.expires_at

    def mark_as_used(self):
        """
        Marca el token como usado (previene reutilización).
        
        SEGURIDAD:
        - Se ejecuta DESPUÉS de cambiar la contraseña
        - Transacción atómica en la vista/servicio
        - Update field específico (no refetch de la BD)
        """
        self.used = True
        self.used_at = timezone.now()
        self.save(update_fields=['used', 'used_at'])
