from django.conf import settings
from cryptography.fernet import Fernet, MultiFernet
from django.core.exceptions import ImproperlyConfigured

def get_fernet_instance():
    """
    Creates a MultiFernet instance based on the ENCRYPTION_KEY setting.
    Keys are comma-separated. The first key is used for encryption.
    All keys can be used for decryption (for key rotation).
    """
    if not hasattr(settings, 'ENCRYPTION_KEY') or not settings.ENCRYPTION_KEY:
        raise ImproperlyConfigured("ENCRYPTION_KEY setting is missing or empty.")

    keys = [k.strip() for k in settings.ENCRYPTION_KEY.split(',') if k.strip()]
    if not keys:
        raise ImproperlyConfigured("No valid keys found in ENCRYPTION_KEY.")

    fernets = []
    for key in keys:
        if key == getattr(settings, 'SECRET_KEY', None):
            raise ImproperlyConfigured("ENCRYPTION_KEY must not be equal to APP_SECRET_KEY.")
        try:
            fernets.append(Fernet(key.encode('utf-8')))
        except ValueError as e:
            raise ImproperlyConfigured(f"Invalid Fernet key in ENCRYPTION_KEY: {str(e)}")

    return MultiFernet(fernets)

def validate_encryption_settings():
    """
    Validates encryption keys at startup.
    Raises ImproperlyConfigured if invalid.
    """
    # Simply instantiating will run the checks
    get_fernet_instance()

def encrypt(plaintext: str) -> bytes:
    """
    Encrypts a plaintext string to bytes.
    """
    if not isinstance(plaintext, str):
        raise TypeError("plaintext must be a string")

    f = get_fernet_instance()
    return f.encrypt(plaintext.encode('utf-8'))

def decrypt(ciphertext: bytes) -> str:
    """
    Decrypts ciphertext bytes back to a plaintext string.
    """
    if not isinstance(ciphertext, bytes):
        raise TypeError("ciphertext must be bytes")

    f = get_fernet_instance()
    return f.decrypt(ciphertext).decode('utf-8')

def mask_value(value: str, visible_chars: int = 4) -> str:
    """
    Masks a string, leaving only the last `visible_chars` visible.
    """
    if not value:
        return ""
    if len(value) <= visible_chars:
        return "•" * len(value)

    masked_part = "•" * 6
    visible_part = value[-visible_chars:]
    return f"{masked_part}{visible_part}"
