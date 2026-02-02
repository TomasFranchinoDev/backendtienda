from rest_framework_simplejwt.authentication import JWTAuthentication
from django.contrib.auth.backends import ModelBackend
from .models import User

class CookieJWTAuthentication(JWTAuthentication):
    """
    JWT auth that reads the access token from an HttpOnly cookie named 'access_token'.
    Falls back to default header-based auth if cookie is missing.
    """
    def authenticate(self, request):
        # Try cookie first
        raw_token = request.COOKIES.get('access_token')
        if raw_token:
            try:
                validated_token = self.get_validated_token(raw_token)
                return self.get_user(validated_token), validated_token
            except Exception:
                # Invalid cookie token; do not authenticate
                return None
        # Fallback to Authorization header
        return super().authenticate(request)



class EmailBackend(ModelBackend):
    """
    Permite login con email o username.
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None

        try:
            user = User.objects.get(email=username)
        except User.DoesNotExist:
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
    def get_user(self, user_id): 
        try: return User.objects.get(pk=user_id) 
        except User.DoesNotExist: 
            return None
