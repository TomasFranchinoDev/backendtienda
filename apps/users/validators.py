"""
Custom validators for User app.

Security validators for email, password, and other user-related fields.
"""

from django.core.exceptions import ValidationError
import requests

# List of disposable email domains (you can use a library or API for this)
# For production, consider using python-decouple to load from env
DISPOSABLE_EMAIL_DOMAINS = {
    # Temporary/Disposable email services
    'tempmail.com',
    'throwaway.email',
    '10minutemail.com',
    'guerrillamail.com',
    'mailinator.com',
    'maildrop.cc',
    'yopmail.com',
    'yopmail.fr',
    'yopmail.net',
    'yopmail.de',
    'yopmail.es',
    'yopmail.ca',
    'yopmail.jp',
    'yopmail.it',
    'yopmail.co.uk',
    'temp-mail.org',
    'sharklasers.com',
    'trashmail.com',
    'spam4.me',
    'fakemail.net',
    'mailnesia.com',
    '0-mail.com',
    'mytrashmail.com',
    'grr.la',
    'fake-email.com',
    'minusemail.com',
    'throwawaymail.com',
    'trashemaildomain.com',
    'temp-mail.io',
    'tempmail.email',
    '10minutemail.net',
    'guerrillamail.info',
    'guerrillamail.net',
    'guerrillamail.org',
    'mailinator.net',
    'mailinator.org',
}


def validate_non_disposable_email(value):
    """
    Validator to prevent registration with disposable email addresses.
    
    Args:
        value (str): Email address to validate
        
    Raises:
        ValidationError: If email domain is in disposable list
        
    Security Notes:
    - Applied to: Register and Change Password endpoints
    - NOT applied to: Login (existing users with disposable emails must login)
    - Helps prevent spam accounts and abuse
    """
    if not isinstance(value, str):
        return
    
    # Extract domain from email
    if '@' not in value:
        return
    
    try:
        _, domain = value.rsplit('@', 1)
    except ValueError:
        # Invalid email format (already caught by EmailField validator)
        return
    
    domain = domain.lower().strip()
    
    if domain in DISPOSABLE_EMAIL_DOMAINS:
        raise ValidationError(
            "No puedes registrarte con un email temporal o desechable. "
            "Por favor usa un email permanente (gmail.com, outlook.com, etc.)"
        )


def validate_password_strength(value):
    """
    Validate password strength requirements.
    
    Requirements:
    - At least 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character
    
    Args:
        value (str): Password to validate
        
    Raises:
        ValidationError: If password doesn't meet requirements
    """
    import re
    
    errors = []
    
    if len(value) < 8:
        errors.append("La contraseña debe tener al menos 8 caracteres")
    
    if not re.search(r'[A-Z]', value):
        errors.append("Debe contener al menos una letra mayúscula")
    
    if not re.search(r'[a-z]', value):
        errors.append("Debe contener al menos una letra minúscula")
    
    if not re.search(r'\d', value):
        errors.append("Debe contener al menos un número")
    
    if not re.search(r'[!@#$%^&*()_+\-=\[\]{};:\'",.<>?/\\|`~]', value):
        errors.append("Debe contener al menos un carácter especial (!@#$%^&*, etc.)")
    
    if errors:
        raise ValidationError(errors)
