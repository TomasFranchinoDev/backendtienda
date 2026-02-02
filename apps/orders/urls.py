from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import OrderViewSet, mercadopago_webhook

router = DefaultRouter()
router.register(r'orders', OrderViewSet, basename='order')

urlpatterns = [
    # IMPORTANTE: Poner el webhook ANTES del router para que tenga prioridad
    path('orders/webhook/', mercadopago_webhook, name='mp-webhook'),
    # Router de órdenes (para CRUD)
    path('', include(router.urls)),
]