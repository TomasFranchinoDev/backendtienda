from django.db import models
from django.conf import settings

class Order(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pendiente'),
        ('paid', 'Pagado'),
        ('shipped', 'Enviado'),
        ('delivered', 'Entregado'),
        ('cancelled', 'Cancelado'),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='orders', on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # SNAPSHOTS: Copia de datos al momento de compra
    shipping_address_data = models.JSONField(help_text="Snapshot de la dirección de envío")
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tracking_number = models.CharField(max_length=100, blank=True, null=True)
    # MODIFICACIÓN SUGERIDA
    # Guardará: {"carrier": "Andreani", "service_id": 12, "mode": "domicilio", "carrier_icon": "..."}
    shipping_option_data = models.JSONField(null=True, blank=True, help_text="Datos del servicio de correo elegido")
    # ID único del envío dentro de la plataforma de Enviopack
    enviopack_id = models.CharField(max_length=50, blank=True, null=True, db_index=True)

    # DATOS DE PAGO
    payment_method = models.CharField(max_length=50) # 'mercadopago', 'transferencia'
    payment_id = models.CharField(max_length=100, blank=True, null=True) # ID externo de MP
    total = models.DecimalField(max_digits=12, decimal_places=2)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    external_reference = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        null=True,
        blank=True
    )
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"Order #{self.id} - {self.user.email}"

class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    # Importación diferida o string para evitar ciclos si fuera necesario, 
    # pero como apps.catalog está separado, usamos string path:
    variant = models.ForeignKey('catalog.ProductVariant', related_name='order_items', on_delete=models.PROTECT)
    
    quantity = models.PositiveIntegerField(default=1)
    
    # PRECIO HISTÓRICO CONGELADO
    price_at_purchase = models.DecimalField(max_digits=10, decimal_places=2, blank=True)

    def save(self, *args, **kwargs):
        # Si no se estableció precio, tomamos el actual de la variante
        if not self.price_at_purchase:
            self.price_at_purchase = self.variant.price
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.quantity}x {self.variant.sku} in Order #{self.order.id}"