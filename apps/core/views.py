from rest_framework.views import APIView
from rest_framework.response import Response

from .models import ShopConfig
from .serializers import ShopConfigSerializer


class ShopConfigView(APIView):
    """
    Vista Singleton para recuperar la configuración de la tienda.
    Siempre devuelve UN ÚNICO objeto ShopConfig (nunca una lista).
    """
    
    def get(self, request):
        # Obtiene o crea el singleton de configuración
        config, _ = ShopConfig.objects.get_or_create(pk=1)
        serializer = ShopConfigSerializer(config)
        return Response(serializer.data)
