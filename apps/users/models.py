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
    
    Características:
    - Token único de un solo uso
    - Expiración de 30 minutos
    - Rastreo de uso
    - Validación estricta
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
        """Genera un token seguro de 64 caracteres hexadecimales."""
        return secrets.token_urlsafe(48)

    def is_valid(self):
        """Verifica si el token es válido (no usado y no expirado)."""
        return not self.used and timezone.now() < self.expires_at

    def mark_as_used(self):
        """Marca el token como usado."""
        self.used = True
        self.used_at = timezone.now()
        self.save(update_fields=['used', 'used_at'])