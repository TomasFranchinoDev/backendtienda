from rest_framework import viewsets, status
from rest_framework.decorators import action, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.http import JsonResponse
import json
import logging
from apps.orders.services import (
    MercadoPagoService,
)
from .services import process_mercadopago_webhook
from .models import Order, OrderItem
from .serializers import (
    OrderCreateSerializer,
    OrderListSerializer,
    OrderDetailSerializer
)
from .services import MercadoPagoService

logger = logging.getLogger(__name__)


class OrderViewSet(viewsets.ModelViewSet):
    """
    ViewSet para órdenes.
    - Listar órdenes del usuario autenticado
    - Ver detalles de una orden
    - Crear nueva orden
    - Endpoint para generar preferencia de pago (FASE 4)
    """
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        # Cada usuario solo ve sus propias órdenes
        return Order.objects.filter(user=self.request.user).prefetch_related(
        'items__variant__product'  # Nested prefetch
    )

    def get_serializer_class(self):
        if self.action == 'create':
            return OrderCreateSerializer
        elif self.action == 'retrieve':
            return OrderDetailSerializer
        return OrderListSerializer
    
    def create(self, request, *args, **kwargs):
        """Crear una nueva orden"""
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        
        # Devolver la orden creada con serializer detail
        output_serializer = OrderDetailSerializer(order)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)
    
  
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """
        Cancelar una orden (solo si está en estado 'pending').
        BONUS: Restaurar stock de los ítems.
        """
        order = self.get_object()
        
        if order.user != request.user:
            return Response(
            {'error': 'No tienes permiso para cancelar esta orden'},
            status=status.HTTP_403_FORBIDDEN
        )
    
        if order.status != 'pending':
            return Response(
                {'error': f'No se puede cancelar una orden con estado {order.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Restaurar stock
        for item in order.items.all():
            variant = item.variant
            variant.stock += item.quantity
            variant.save()
        
        # Marcar como cancelada
        order.status = 'cancelled'
        order.save()
        
        return Response(
            {'message': 'Orden cancelada. Stock restaurado.'},
            status=status.HTTP_200_OK
        )
    
    @action(detail=True, methods=['post'])
    def payment_preference(self, request, pk=None):
        """
        Generar preferencia de pago en Mercado Pago para una orden.
        
        Solo disponible si:
        - La orden pertenece al usuario autenticado
        - El estado es 'pending'
        
        Retorna: {init_point, preference_id, order_id}
        """
        order = self.get_object()
        
        # Validar permisos
        if order.user != request.user:
            return Response(
                {'error': 'No tienes permiso para esta orden'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Validar estado
        if order.status != 'pending':
            return Response(
                {'error': f'Solo órdenes pendientes pueden generar pago. '
                          f'Estado actual: {order.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            service = MercadoPagoService()
            payment_info = service.create_payment_preference(order)
            order.external_reference = str(order.id)
            order.save(update_fields=["external_reference"])

            return Response({
                'order_id': order.id,
                'init_point': payment_info['init_point'],
                'preference_id': payment_info['preference_id']
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def sync_payment(self, request, pk=None):
        """
        Sincronizar estado del pago con Mercado Pago.
        Útil cuando el webhook no llega o para debugging.
        
        Envía: {"preference_id": "2642975369-xxx"}
        """
        order = self.get_object()
        preference_id = request.data.get('preference_id')
        
        if not preference_id:
            return Response(
                {'error': 'preference_id requerido'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            service = MercadoPagoService()
            # Consultar pagos de esta preferencia
            payment_info = service.sdk.payment().search({
                'preference_id': preference_id
            })
            
            if payment_info["status"] != 200:
                return Response(
                    {'error': f'Error consultando MP: {payment_info}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            payments = payment_info.get('response', {}).get('results', [])
            
            if not payments:
                return Response(
                    {'error': 'No se encontraron pagos para esta preferencia'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Procesar el primer pago (generalmente el más reciente)
            payment = payments[0]
            payment_data = {
                'data': {'id': payment['id']}
            }
            
            # Validar y procesar como si fuera un webhook
            validation_result = service.validate_payment_notification(payment_data)
            
            if not validation_result:
                return Response(
                    {'error': 'No se pudo validar el pago'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            payment_status = validation_result['payment_status']
            payment_id = validation_result['payment_id']
            
            # Actualizar la orden
            if payment_status == 'approved':
                order.status = 'paid'
                order.payment_id = payment_id
                order.save()
                return Response({
                    'status': 'paid',
                    'payment_id': payment_id,
                    'order': OrderDetailSerializer(order).data
                }, status=status.HTTP_200_OK)
            
            elif payment_status == 'pending':
                order.payment_id = payment_id
                order.save()
                return Response({
                    'status': 'pending',
                    'payment_id': payment_id,
                    'order': OrderDetailSerializer(order).data
                }, status=status.HTTP_200_OK)
            
            else:
                return Response({
                    'status': payment_status,
                    'payment_id': payment_id
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error syncing payment:", exc_info=True)
            return Response(
                {'error': "Error interno del servidor"},
                status=status.HTTP_400_BAD_REQUEST
            )


# Webhook handler usando Django puro (sin DRF) para evitar problemas de autenticación
@csrf_exempt
@require_http_methods(["POST"])
def mercadopago_webhook(request):
    try:
        # 1️⃣ Body (puede venir vacío)
        if request.body:
            try:
                body_data = json.loads(request.body.decode("utf-8"))
            except json.JSONDecodeError:
                body_data = {}
        else:
            body_data = {}

        # 2️⃣ Query params (MP los usa muchísimo)
        query_data = request.GET.dict()

        # 3️⃣ Extraer IDs correctamente
        topic = body_data.get("type") or query_data.get("type")
        resource = body_data.get("resource")
        data_id = (
            body_data.get("data", {}).get("id")
            or query_data.get("data.id")
        )

        if not data_id:
            logger.warning("[WEBHOOK] No data.id recibido")
            return JsonResponse({"status": "ignored"}, status=200)

        # 4️⃣ Delegar lógica pesada al service
        
        process_mercadopago_webhook(topic, data_id)

        return JsonResponse({"status": "ok"}, status=200)

    except Exception as e:
        logger.exception("[WEBHOOK] Error procesando webhook")
        return JsonResponse({"error": "Error interno del servidor"}, status=500)