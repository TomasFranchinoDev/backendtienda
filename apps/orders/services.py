import mercadopago
import logging
import os
from django.db import transaction
from .models import Order

logger = logging.getLogger(__name__)


class MercadoPagoService:
    """
    Servicio para interactuar con la API de Mercado Pago.
    Encapsula la lógica de negocio relacionada con pagos.
    Procesa webhooks de forma idempotente y confiable.
    """

    def __init__(self):
        """Inicializa el cliente de MP con credenciales desde variables de entorno."""
        access_token = os.getenv('MERCADOPAGO_ACCESS_TOKEN')
        if not access_token:
            raise ValueError('MERCADOPAGO_ACCESS_TOKEN not configured in .env')
        self.sdk = mercadopago.SDK(access_token)

    def create_payment_preference(self, order: Order):
        """
        Crea una preferencia de pago en Mercado Pago para una orden.

        Args:
            order: Instancia de Order

        Returns:
            dict con 'init_point' (URL de pago) y 'preference_id'

        Raises:
            Exception si falla la creación
        """
        # Construir items para MP (solo productos, sin shipping)
        items = []
        for item in order.items.all():
            items.append({
                "id": str(item.id),
                "title": f"{item.variant.product.name} ({item.variant.sku})",
                "unit_price": float(item.price_at_purchase),
                "quantity": item.quantity,
            })

        # Obtener URLs de frontend desde variables de entorno
        frontend_base_url = os.getenv('FRONTEND_URL', 'http://localhost:3000')
        is_production = not frontend_base_url.startswith('http://localhost')

        # Crear preferencia de pago con el formato correcto para Mercado Pago
        preference_data = {
            "items": items,
            "payer": {
                "email": order.user.email,
                "name": order.user.first_name,
                "surname": order.user.last_name,
            },
            "back_urls": {
                "success": f"{frontend_base_url}/orders/{order.id}",
                "failure": f"{frontend_base_url}/orders/{order.id}",
                "pending": f"{frontend_base_url}/orders/{order.id}",
            },
            "external_reference": str(order.id),
        }

        # Solo agregar auto_return en producción (MP no acepta localhost)
        if is_production:
            preference_data["auto_return"] = "approved"

        try:
            response = self.sdk.preference().create(preference_data)

            if response["status"] == 201:
                return {
                    "init_point": response["response"]["init_point"],
                    "preference_id": response["response"]["id"]
                }
            else:
                logger.error(
                    f"Failed to create MP preference for Order: Status {response['status']}"
                )
                raise Exception(
                    f"Mercado Pago returned status {response['status']}"
                )

        except Exception as e:
            logger.error(f"Error creating MP preference", exc_info=True)
            raise Exception(f"No se pudo generar el link de pago")

    def validate_payment_notification(self, data: dict):
        """
        Valida y procesa una notificación de pago de Mercado Pago.

        Args:
            data: Diccionario con los datos recibidos en el webhook de MP.

        Returns:
            dict con información relevante si es válido, None si no es válido.
        """

        payment_id = data.get('data', {}).get('id')

        if not payment_id:
            logger.warning("MP notification without payment ID")
            return None

        try:
            # 1️⃣ Fuente de verdad: API MP
            payment_info = self.sdk.payment().get(payment_id)

            if payment_info["status"] != 200:
                logger.error(f"Failed to fetch MP payment: Status {payment_info['status']}", exc_info=True)
                return None

            payment_data = payment_info["response"]

            status = payment_data.get("status")
            external_reference = payment_data.get("external_reference")
            amount = payment_data.get("transaction_amount")
            currency = payment_data.get("currency_id")

            # 2️⃣ Validaciones estructurales
            if not external_reference:
                logger.warning(f"MP Payment has no external_reference")
                return None

            if not amount:
                logger.warning(f"MP Payment has no amount")
                return None

            # 3️⃣ Normalizar estado
            if status not in ["approved", "pending", "rejected", "cancelled", "refunded"]:
                logger.warning(f"Unknown MP status {status} for payment")
                return None

            return {
                "order_id": int(external_reference),
                "payment_status": status,
                "payment_id": payment_id,
                "amount": float(amount),
                "currency": currency,
            }

        except Exception as e:
            logger.error(f"Error validating MP notification:", exc_info=True)
            return None
def process_mercadopago_webhook(topic: str, data_id: str):
    """
    Procesa webhooks de Mercado Pago (merchant_order / payment)
    """
    access_token = os.getenv('MERCADOPAGO_ACCESS_TOKEN')
    if not access_token:
        raise ValueError('MERCADOPAGO_ACCESS_TOKEN not configured in .env')
    sdk = mercadopago.SDK(access_token)

    # 🟡 MERCHANT ORDER
    if topic in ("topic_merchant_order_wh", "merchant_order"):
        response = sdk.merchant_order().get(data_id)
        merchant_order = response.get("response")

        if not merchant_order:
            logger.warning("[WEBHOOK] merchant_order vacío")
            return

        external_reference = merchant_order.get("external_reference")
        payments = merchant_order.get("payments", [])

        if not external_reference:
            logger.warning("[WEBHOOK] merchant_order sin external_reference")
            return

        with transaction.atomic():
            try:
                order = Order.objects.select_for_update().get(
                    external_reference=external_reference
                )
            except Order.DoesNotExist:
                logger.warning(f"[WEBHOOK] Order no encontrada: External Reference")
                return

            # Idempotencia
            if order.status == "paid":
                return

            # Buscar pago aprobado
            approved_payment = next(
                (
                    p for p in payments
                    if p.get("status") == "approved"
                ),
                None
            )

            if not approved_payment:
                return

            order.status = "paid"
            order.payment_id = approved_payment.get("id")
            order.save(update_fields=["status", "payment_id"])

    # 🟡 PAYMENT (opcional pero recomendado)
    elif topic == "payment":
        response = sdk.payment().get(data_id)
        payment = response.get("response")

        if not payment:
            return

        external_reference = payment.get("external_reference")
        if not external_reference:
            return

        with transaction.atomic():
            try:
                order = Order.objects.select_for_update().get(
                    external_reference=external_reference
                )
            except Order.DoesNotExist:
                return

            if payment.get("status") == "approved":
                order.status = "paid"
                order.payment_id = payment.get("id")
                order.save(update_fields=["status", "payment_id"])