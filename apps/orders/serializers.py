from django.db import DatabaseError, transaction
from rest_framework import serializers
from decimal import Decimal
from .models import Order, OrderItem
from apps.catalog.models import ProductVariant
from apps.catalog.serializers import ProductVariantSerializer


class OrderItemSerializer(serializers.ModelSerializer):
    variant_details = ProductVariantSerializer(source='variant', read_only=True)
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = ['id', 'variant', 'variant_details', 'quantity', 'price_at_purchase', 'subtotal']

    def get_subtotal(self, obj):
        return obj.quantity * obj.price_at_purchase


class OrderListSerializer(serializers.ModelSerializer):
    """Serializer ligero para listar órdenes del usuario"""
    class Meta:
        model = Order
        fields = ['id', 'status', 'total', 'created_at', 'updated_at']


class OrderDetailSerializer(serializers.ModelSerializer):
    """Serializer completo con detalles de ítems"""
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            'id',
            'status',
            'items',
            'shipping_address_data',
            'shipping_cost',
            'payment_method',
            'payment_id',
            'total',
            'created_at',
            'updated_at',
        ]

class ShippingAddressSerializer(serializers.Serializer):
    street = serializers.CharField(max_length=255)
    number = serializers.CharField(max_length=20)
    city = serializers.CharField(max_length=100)
    state = serializers.CharField(max_length=100, required=False, allow_blank=True)
    postal_code = serializers.CharField(max_length=20)
    country = serializers.CharField(max_length=100)
    additional_info = serializers.CharField(
        max_length=255, required=False, allow_blank=True
    )


class OrderCreateSerializer(serializers.Serializer):
    """
    Serializer para crear órdenes.
    Recibe una lista de items con variant_id y quantity.
    El backend valida stock y calcula el total.
    """
    items = serializers.ListField(
        child=serializers.DictField(
            child=serializers.IntegerField(),
            help_text='Ej: {"variant_id": 1, "quantity": 2}'
        ),
        min_length=1
    )
    shipping_address_data = ShippingAddressSerializer()
    payment_method = serializers.CharField(max_length=50)

    def validate_items(self, items):
        """Validar que cada item tenga variant_id y quantity"""
        for item in items:
            if 'variant_id' not in item or 'quantity' not in item:
                raise serializers.ValidationError(
                    "Cada item debe tener 'variant_id' y 'quantity'"
                )
            if item['quantity'] < 1:
                raise serializers.ValidationError(
                    "La cantidad debe ser mayor a 0"
                )
        return items

    
    def create(self, validated_data):
        items_data = validated_data['items']
        shipping_address = validated_data['shipping_address_data']
        payment_method = validated_data['payment_method']
        user = self.context['request'].user

        # 1. Extraemos los IDs de las variantes solicitadas
        variant_ids = [item['variant_id'] for item in items_data]
        
        # Mapa para acceder rápidamente a la cantidad solicitada por ID
        # { variant_id: quantity }
        quantities_map = {item['variant_id']: item['quantity'] for item in items_data}

        try:
            with transaction.atomic():
                # PASO A: Crear la Orden (Estado inicial)
                order = Order.objects.create(
                    user=user,
                    shipping_address_data=shipping_address,
                    payment_method=payment_method,
                    status='pending',
                    total=Decimal('0.00')
                )

                # PASO B: Fetch masivo y bloqueo (SELECT ... FOR UPDATE)
                # Traemos TODAS las variantes en una sola consulta
                variants = (
                    ProductVariant.objects
                    .select_for_update(nowait=True)
                    .select_related('product')
                    .filter(id__in=variant_ids)
                )

                # Validar que encontramos todas las variantes solicitadas
                if len(variants) != len(variant_ids):
                    found_ids = set(v.id for v in variants)
                    missing_ids = set(variant_ids) - found_ids
                    raise serializers.ValidationError(
                        f"Algunos productos no están disponibles o no existen: IDs {missing_ids}"
                    )

                order_items_to_create = []
                variants_to_update = []
                total = Decimal('0.00')

                # PASO C: Procesamiento en Memoria (Bucle rápido en Python)
                for variant in variants:
                    quantity = quantities_map[variant.id]

                    # Validaciones
                    if not variant.product.is_active:
                        raise serializers.ValidationError(
                            f"El producto {variant.product.name} ya no está disponible."
                        )

                    if variant.stock < quantity:
                        raise serializers.ValidationError(
                            f"Stock insuficiente para {variant.sku}. "
                            f"Disponible: {variant.stock}, Solicitado: {quantity}"
                        )

                    # Actualizamos el stock en el objeto Python (Aún no en DB)
                    variant.stock -= quantity
                    variants_to_update.append(variant)

                    # Preparamos el objeto OrderItem (Aún no en DB)
                    order_items_to_create.append(
                        OrderItem(
                            order=order,
                            variant=variant,
                            quantity=quantity,
                            price_at_purchase=variant.price
                        )
                    )

                    total += Decimal(variant.price) * Decimal(quantity)

                # PASO D: Escritura Masiva (Bulk Operations)
                
                # 1. Guardar todos los items de una sola vez
                OrderItem.objects.bulk_create(order_items_to_create)

                # 2. Actualizar stock de variantes de una sola vez
                # fields=['stock'] es CRÍTICO para no sobrescribir otros datos
                ProductVariant.objects.bulk_update(variants_to_update, fields=['stock'])

                # 3. Actualizar total de la orden
                order.total = total
                order.save(update_fields=['total'])

                return order

        except DatabaseError:
            raise serializers.ValidationError(
                "Hubo un conflicto de concurrencia al procesar tu orden. Por favor intenta nuevamente."
            )