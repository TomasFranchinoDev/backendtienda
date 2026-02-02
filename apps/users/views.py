from urllib import response
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken
from django.conf import settings
import os
from datetime import timedelta
from rest_framework.permissions import IsAuthenticated
from rest_framework.permissions import AllowAny
from .serializers import (
    RegisterSerializer,
    CustomTokenObtainPairSerializer,
    UserSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
)
from .services import PasswordResetService


class RegisterView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response(
                {'message': 'Usuario registrado exitosamente', 'user': UserSerializer(user).data},
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CustomLoginView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        access_token = data.get('access')
        refresh_token = data.get('refresh')

        response = Response({'message': 'Login exitoso'}, status=status.HTTP_200_OK)
        _set_auth_cookies(response, access_token, refresh_token)
        return response


class CookieTokenRefreshView(TokenRefreshView):
    """Refresh tokens from HttpOnly cookie, rotate and set new cookies."""
    def post(self, request, *args, **kwargs):
        refresh = request.COOKIES.get('refresh_token')
        if not refresh:
            return Response({'detail': 'Refresh token ausente'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(data={'refresh': refresh})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        response = Response({'message': 'Token refrescado'}, status=status.HTTP_200_OK)
        _set_auth_cookies(response, data.get('access'), data.get('refresh'))
        return response


class LogoutView(APIView):
    """Blacklist refresh token and clear auth cookies."""
    permission_classes = [AllowAny]
    def post(self, request):
        refresh = request.COOKIES.get('refresh_token')
        print(request.COOKIES)
        if refresh:
            try:
                token = RefreshToken(refresh)
                token.blacklist()
            except Exception:
                pass

        response = Response({'message': 'Logout exitoso'}, status=status.HTTP_200_OK)
        _clear_auth_cookies(response)
        return response


class PasswordResetRequestView(APIView):
    """
    Endpoint para solicitar recuperación de contraseña.
    
    POST /api/auth/password-reset/
    
    SEGURIDAD:
    - No requiere autenticación (usuario olvidó contraseña)
    - Valida formato de email en serializer
    - Delega lógica a servicio (separación de responsabilidades)
    - Retorna 200 siempre (no filtra usuarios)
    - Rate limiting debería agregarse en producción
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data['email']
        # Delegar a servicio (toda la lógica de negocio)
        success, message = PasswordResetService.request_password_reset(email)

        # Siempre retornar 200 OK (no revelar si el email existe)
        return Response(
            {'detail': message},
            status=status.HTTP_200_OK
        )


class PasswordResetConfirmView(APIView):
    """
    Endpoint para confirmar cambio de contraseña.
    
    POST /api/auth/password-reset/confirm/
    
    SEGURIDAD:
    - POST only (nunca GET para cambios de estado)
    - Token y password validados antes de procesar
    - Delega reset a servicio en transacción atómica
    - No revela detalles de qué falló exactamente
    - Password cambio completo: logout de otras sesiones
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        token = serializer.validated_data['token']
        new_password = serializer.validated_data['new_password']

        # Delegar al servicio (transacción atómica, validación estricta)
        success, message = PasswordResetService.reset_password(token, new_password)

        if success:
            return Response(
                {'detail': message},
                status=status.HTTP_200_OK
            )
        else:
            # Retornar 400 en caso de error
            return Response(
                {'detail': message},
                status=status.HTTP_400_BAD_REQUEST
            )


def _set_auth_cookies(response, access: str | None, refresh: str | None):
    """
    Establece cookies HttpOnly para JWT.
    
    SEGURIDAD:
    - httponly=True: No accesible desde JavaScript (previene XSS)
    - secure=True: Solo en HTTPS (producción)
    - samesite: Protege contra CSRF
    - Separar access y refresh (granular)
    """
    # ngrok uses HTTPS, which REQUIRES secure=True and SameSite=None for cross-origin
    secure = True
    samesite = 'None' 
    path = '/'
    if access:
        max_age_access = int(settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'].total_seconds())
        response.set_cookie(
            'access_token', access,
            max_age=max_age_access,
            httponly=True,
            secure=secure,
            samesite=samesite,
            path=path,
            domain=None,
        )
    if refresh:
        max_age_refresh = int(settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds())
        response.set_cookie(
            'refresh_token', refresh,
            max_age=max_age_refresh,
            httponly=True,
            secure=secure,
            samesite=samesite,
            path=path,
            domain=None,
        )


def _clear_auth_cookies(response):
    """Borra cookies de autenticación (logout)."""
    path = '/'
    samesite = "None"

    response.delete_cookie(
        'access_token',
        path=path,
        samesite=samesite,
    )

    response.delete_cookie(
        'refresh_token',
        path=path,
        samesite=samesite,
    )


class UserMeView(APIView):
    """Retorna datos del usuario autenticado."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)
