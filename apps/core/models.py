from django.db import models
from encrypted_model_fields.fields import EncryptedTextField


class ShopConfig(models.Model):
    site_name = models.CharField(max_length=255, default="Mi Tienda")
    primary_color = models.CharField(max_length=7, default="#FF5733", help_text="Formato Hex: #RRGGBB")
    secondary_color = models.CharField(max_length=7, default="#333333", blank=True)
    logo_url = models.URLField(max_length=500, blank=True, null=True)
    
    # JSONField para redes sociales (flexible)
    social_links = models.JSONField(default=dict, blank=True, help_text='Ej: {"instagram": "@tienda", "whatsapp": "+549..."}')
    
    contact_email = models.EmailField(blank=True)
    
    # Credenciales de Mercado Pago (Encriptarlas sería ideal en el futuro, por ahora texto plano)
    mp_public_key = EncryptedTextField(blank=True)
    mp_access_token = EncryptedTextField(blank=True)

    class Meta:
        verbose_name = "Configuración de Tienda"
        verbose_name_plural = "Configuración de Tienda"

    def __str__(self):
        return self.site_name
        
    def save(self, *args, **kwargs):
        # Lógica opcional: asegurar que solo exista 1 fila (Singleton)
        if not self.pk and ShopConfig.objects.exists():
            # Si ya existe una config, podrías bloquear la creación o actualizar la existente
            pass
        super().save(*args, **kwargs)