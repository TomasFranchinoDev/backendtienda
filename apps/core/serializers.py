from rest_framework import serializers

from .models import ShopConfig


class ShopConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShopConfig
        fields = [
            'id',
            'site_name',
            'primary_color',
            'secondary_color',
            'logo_url',
            'social_links',
            'contact_email',
            # Solo la clave pública (segura para frontend)
            # NUNCA exponer mp_access_token en API pública (es privada)
        ]
