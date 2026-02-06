from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import authenticate
from .models import User, PasswordResetToken
from .validators import validate_non_disposable_email, validate_password_strength
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ['email', 'username', 'first_name', 'last_name', 'password', 'password_confirm']

    def validate(self, data):
        if data['password'] != data.pop('password_confirm'):
            raise serializers.ValidationError({"password": "Las contraseñas no coinciden"})
        return data

    def create(self, validated_data):
        user = User.objects.create_user(
            email=validated_data['email'],
            username=validated_data['username'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            password=validated_data['password']
        )
        return user
    
    def validate_email(self, value):
        # Check for disposable emails
        try:
            validate_non_disposable_email(value)
        except ValidationError as e:
            raise serializers.ValidationError({"detail": "No es posible registrar con este email"})
        
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError({"detail": "No es posible registrar con este email"})
        return value


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Login personalizado que acepta email en lugar de username.
    """
    username_field = 'email'

    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')

        # Validación de formato de email (RFC 5322)
        try:
            validate_email(email)
        except ValidationError:
            raise serializers.ValidationError({
                'email': 'Formato de email inválido'
            })

        user = User.objects.filter(email=email).first()

        if user and user.check_password(password):
            data = super().validate({
                'email': user.email,
                'password': password
            })

            # Datos extra en la respuesta
            data['first_name'] = user.first_name
            data['email'] = user.email

            return data

        raise serializers.ValidationError({"detail": "Email o contraseña incorrectos"})


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'first_name', 'last_name', 'phone_number', 'is_verified']


class PasswordResetRequestSerializer(serializers.Serializer):
    """
    Serializer para solicitar recuperación de contraseña.
    
    Endpoint: POST /api/auth/password-reset/
    
    SEGURIDAD:
    - Validamos formato de email pero NO que exista (previene user enumeration)
    - La lógica real de búsqueda está en el servicio
    """
    email = serializers.EmailField(required=True)

    def validate_email(self, value):
        """Validar solo formato de email, no existencia."""
        try:
            validate_email(value)
        except ValidationError:
            raise serializers.ValidationError("Formato de email inválido")
        return value


class PasswordResetConfirmSerializer(serializers.Serializer):
    """
    Serializer para confirmar cambio de contraseña con token.
    
    Endpoint: POST /api/auth/password-reset/confirm/
    
    SEGURIDAD:
    - Token debe ser sólido (50+ caracteres)
    - Password es write_only (no se devuelve)
    - Validación básica aquí, más estricta en service (validate_password de Django)
    """
    token = serializers.CharField(required=True, min_length=50, max_length=255)
    new_password = serializers.CharField(
        required=True,
        min_length=8,
        write_only=True,  # No se devuelve en respuesta
        help_text="La contraseña debe cumplir los requisitos de seguridad"
    )

    def validate_new_password(self, value):
        """Validación básica (más estricta en PasswordResetService.reset_password)."""
        if len(value) < 8:
            raise serializers.ValidationError("La contraseña debe tener al menos 8 caracteres")
        
        # No puede ser solo números (previene contraseñas débiles)
        if value.isdigit():
            raise serializers.ValidationError("La contraseña no puede ser completamente numérica")
        
        return value

