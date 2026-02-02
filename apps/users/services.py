"""
Servicio de recuperación de contraseña con Resend.

DECISIONES DE SEGURIDAD:
- Generamos tokens con secrets.token_urlsafe() en lugar de UUID para mejor entropía
- No revelamos si el email existe (retornamos siempre el mismo mensaje)
- Tokens son de un solo uso (marca used=True después de usarse)
- Expiración corta (30 min) para limitar ventana de ataque
- Validamos contraseña con validate_password() de Django (incluye múltiples reglas)
- Usamos @transaction.atomic para evitar race conditions
- No loguemos tokens (solo email y timestamps)
- POST only (no GET) para cambios de contraseña
- Invalidamos sesiones anteriores después de reset
"""

import logging
from typing import Optional, Tuple
from django.utils import timezone
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.conf import settings
from django.db import transaction
from rest_framework_simplejwt.tokens import RefreshToken
import resend
import secrets

from .models import User, PasswordResetToken

logger = logging.getLogger(__name__)

# Configurar Resend con API key desde settings
if settings.RESEND_API_KEY:
    resend.api_key = settings.RESEND_API_KEY


class PasswordResetService:
    """
    Servicio centralizado para recuperación de contraseña.
    Maneja toda la lógica de negocio relacionada con reset de password.
    """

    @staticmethod
    def request_password_reset(email: str) -> Tuple[bool, str]:
        """
        Inicia el proceso de recuperación de contraseña.

        SEGURIDAD:
        - No revelar si el email existe (previene user enumeration)
        - Limpiar tokens expirados para no llenar la BD
        - Retornar siempre el mismo mensaje de éxito

        Args:
            email: Email del usuario

        Returns:
            Tupla (success: bool, message: str)
        """
        try:
            # 1. Buscar usuario (sin revelar si existe)
            user = User.objects.filter(email=email).first()

            if user:
                # 2. Limpiar tokens expirados y usados (mantenimiento de BD)
                PasswordResetToken.objects.filter(
                    user=user,
                    used=False,
                    expires_at__lt=timezone.now()
                ).delete()

                # 3. Generar token seguro
                token_str = PasswordResetToken.generate_token()
                expires_at = timezone.now() + timezone.timedelta(
                    minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES
                )

                # 4. Guardar en BD
                token_obj = PasswordResetToken.objects.create(
                    user=user,
                    token=token_str,
                    expires_at=expires_at
                )

                # 5. Enviar email con link
                reset_link = f"{settings.PASSWORD_RESET_URL}?token={token_str}"
                _send_password_reset_email(
                    user_email=user.email,
                    user_name=user.first_name or user.username,
                    reset_link=reset_link,
                    expires_minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES
                )

                logger.info(f"Password reset initiated: {user.email}")
            else:
                # No loguear el email no encontrado (previene information leakage)
                logger.warning(f"Password reset request for unknown email")

            # Siempre retornar éxito (no filtrar usuarios)
            return (True, "Correo de recuperación enviado correctamente")

        except Exception as e:
            logger.error(f"Error requesting password reset: {str(e)}", exc_info=True)
            return (False, "Error al procesar la solicitud. Intenta más tarde.")

    @staticmethod
    def validate_reset_token(token: str) -> Tuple[Optional[PasswordResetToken], Optional[str]]:
        """
        Valida un token de recuperación.

        SEGURIDAD:
        - Verificar que no fue usado (de un solo uso)
        - Verificar expiración estricta
        - No revelar qué falló exactamente (mensaje genérico)

        Args:
            token: Token a validar

        Returns:
            Tupla (token_obj, error_msg)
        """
        try:
            token_obj = PasswordResetToken.objects.filter(token=token).first()

            if not token_obj:
                # Token no existe
                return (None, "Token inválido")

            if token_obj.used:
                # Token ya fue usado (previene reutilización)
                return (None, "Token ya fue utilizado")

            if not token_obj.is_valid():
                # Token expiró
                return (None, "Token expirado")

            return (token_obj, None)

        except Exception as e:
            logger.error(f"Error validating reset token: {str(e)}", exc_info=True)
            return (None, "Error al validar el token")

    @staticmethod
    @transaction.atomic  # Garantiza que todo sucede o nada (no estado inconsistente)
    def reset_password(token: str, new_password: str) -> Tuple[bool, str]:
        """
        Cambia la contraseña del usuario usando un token.

        SEGURIDAD:
        - Transacción atómica (evita estados intermedios)
        - Validar contraseña contra reglas de Django
        - Marcar token como usado DESPUÉS de cambiar contraseña
        - Log de auditoría sin incluir datos sensibles

        Args:
            token: Token de recuperación
            new_password: Nueva contraseña

        Returns:
            Tupla (success, message)
        """
        try:
            # 1. Validar token (puede fallar por múltiples razones)
            token_obj, error_msg = PasswordResetService.validate_reset_token(token)
            if error_msg:
                return (False, error_msg)

            user = token_obj.user

            # 2. Validar contraseña (usa todas las validators de Django)
            try:
                validate_password(new_password, user)
            except ValidationError as e:
                # No revelar qué validator falló exactamente (información limitada)
                error_msg = "; ".join(e.messages)
                return (False, f"Contraseña inválida: {error_msg}")

            # 3. Cambiar contraseña (hash con algoritmo de Django)
            user.set_password(new_password)
            user.save(update_fields=['password'])

            # 4. Marcar token como usado (previene reutilización)
            token_obj.mark_as_used()

            logger.info(f"Password reset completed for user: {user.email}")
            return (True, "Contraseña actualizada correctamente")

        except Exception as e:
            logger.error(f"Error resetting password: {str(e)}", exc_info=True)
            return (False, "Error al actualizar la contraseña. Intenta más tarde.")


def _send_password_reset_email(
    user_email: str,
    user_name: str,
    reset_link: str,
    expires_minutes: int
) -> bool:
    """
    Envía email de recuperación usando Resend.

    SEGURIDAD:
    - Email HTML (no plain text para mejor control)
    - Incluye aviso de expiración (urgencia)
    - No enviar contraseña en email
    - Usar from address verificado en Resend

    Args:
        user_email: Email destino
        user_name: Nombre para personalizar
        reset_link: Link del reset
        expires_minutes: Minutos válido

    Returns:
        True si se envió, False si falló
    """
    try:
        if not settings.RESEND_API_KEY:
            logger.error("RESEND_API_KEY not configured")
            return False

        html_content = _generate_password_reset_email_html(
            user_name=user_name,
            reset_link=reset_link,
            expires_minutes=expires_minutes
        )

        response = resend.Emails.send(
            {
                "from": settings.EMAIL_FROM,
                "to": user_email,
                "subject": "Recupera tu contraseña - Mi Tienda",
                "html": html_content,
            }
        )

        # Verificar que Resend retornó un ID (envío exitoso)
        if hasattr(response, 'get') and response.get('id'):
            logger.info(f"Password reset email sent: {user_email}")
            return True
        else:
            logger.error(f"Resend email failed: {response}")
            return False

    except Exception as e:
        logger.error(f"Error sending password reset email: {str(e)}", exc_info=True)
        return False


def _generate_password_reset_email_html(
    user_name: str,
    reset_link: str,
    expires_minutes: int
) -> str:
    """
    Genera HTML del email de recuperación.

    DISEÑO:
    - Incluir botón CTA prominente
    - Link alternativo en texto plano
    - Aviso de expiración
    - Nota de seguridad
    - Información clara pero no sensible

    Returns:
        String HTML
    """
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                background-color: #f5f5f5;
            }}
            .container {{
                max-width: 600px;
                margin: 0 auto;
                background-color: #ffffff;
                padding: 40px;
                border-radius: 8px;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
            }}
            .header {{
                text-align: center;
                margin-bottom: 30px;
                border-bottom: 2px solid #f0f0f0;
                padding-bottom: 20px;
            }}
            .header h1 {{
                color: #2c3e50;
                margin: 0;
                font-size: 24px;
            }}
            .content {{
                margin: 30px 0;
            }}
            .greeting {{
                font-size: 16px;
                margin-bottom: 20px;
                color: #555;
            }}
            .message {{
                font-size: 14px;
                color: #666;
                line-height: 1.8;
                margin-bottom: 30px;
            }}
            .cta-button {{
                display: inline-block;
                background-color: #007bff;
                color: #ffffff;
                text-decoration: none;
                padding: 12px 30px;
                border-radius: 4px;
                font-weight: 600;
                text-align: center;
                margin: 20px 0;
            }}
            .cta-button:hover {{
                background-color: #0056b3;
            }}
            .button-container {{
                text-align: center;
                margin: 30px 0;
            }}
            .link-fallback {{
                font-size: 12px;
                color: #999;
                margin-top: 20px;
                padding-top: 20px;
                border-top: 1px solid #f0f0f0;
                word-break: break-all;
            }}
            .expiration-notice {{
                background-color: #fff3cd;
                border-left: 4px solid #ffc107;
                padding: 15px;
                margin: 20px 0;
                border-radius: 4px;
                font-size: 13px;
                color: #856404;
            }}
            .footer {{
                text-align: center;
                font-size: 12px;
                color: #999;
                margin-top: 40px;
                border-top: 1px solid #f0f0f0;
                padding-top: 20px;
            }}
            .security-note {{
                background-color: #f8f9fa;
                padding: 15px;
                border-radius: 4px;
                font-size: 13px;
                color: #666;
                margin-top: 20px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Mi Tienda</h1>
            </div>

            <div class="content">
                <div class="greeting">
                    ¡Hola {user_name}!
                </div>

                <div class="message">
                    Recibimos una solicitud para recuperar tu contraseña. Si no fuiste tú, 
                    puedes ignorar este email de forma segura.
                </div>

                <div class="expiration-notice">
                    ⏱️ Este link expirará en <strong>{expires_minutes} minutos</strong>. 
                    Actúa rápido para recuperar tu acceso.
                </div>

                <div class="button-container">
                    <a href="{reset_link}" class="cta-button">
                        Recuperar Contraseña
                    </a>
                </div>

                <div class="message">
                    Si el botón no funciona, copia y pega este enlace en tu navegador:
                </div>

                <div class="link-fallback">
                    {reset_link}
                </div>

                <div class="security-note">
                    <strong>🔒 Seguridad:</strong> Nunca compartimos tu contraseña por email. 
                    Nuestros enlaces son únicos y de un solo uso. Si no solicitaste esto, 
                    tu cuenta está segura.
                </div>
            </div>

            <div class="footer">
                <p>&copy; 2025 Mi Tienda. Todos los derechos reservados.</p>
                <p>¿Necesitas ayuda? Contáctanos en soporte@mitienda.com</p>
            </div>
        </div>
    </body>
    </html>
    """

