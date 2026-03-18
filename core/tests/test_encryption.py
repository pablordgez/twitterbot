import pytest
from django.core.exceptions import ImproperlyConfigured
from cryptography.fernet import Fernet
from core.services.encryption import encrypt, decrypt, mask_value, validate_encryption_settings

class TestEncryptionService:
    @pytest.fixture
    def mock_settings(self, settings):
        self.key1 = Fernet.generate_key().decode('utf-8')
        self.key2 = Fernet.generate_key().decode('utf-8')
        settings.ENCRYPTION_KEY = f"{self.key1},{self.key2}"
        settings.SECRET_KEY = "dummy-app-secret-key"
        return settings

    def test_encrypt_decrypt_roundtrip(self, mock_settings):
        plaintext = "my-super-secret-password-123"
        ciphertext = encrypt(plaintext)
        assert isinstance(ciphertext, bytes)
        assert ciphertext != plaintext.encode('utf-8')

        decrypted = decrypt(ciphertext)
        assert decrypted == plaintext

    def test_wrong_key_fails_decryption(self, mock_settings):
        plaintext = "test-data"
        ciphertext = encrypt(plaintext)

        # Change keys entirely
        mock_settings.ENCRYPTION_KEY = Fernet.generate_key().decode('utf-8')

        from cryptography.fernet import InvalidToken
        with pytest.raises(InvalidToken):
            decrypt(ciphertext)

    def test_multifernet_rotation(self, mock_settings):
        # Encrypt with key1 (primary)
        mock_settings.ENCRYPTION_KEY = self.key1
        ciphertext1 = encrypt("data1")

        # Rotate: key2 is now primary, key1 is secondary
        mock_settings.ENCRYPTION_KEY = f"{self.key2},{self.key1}"

        # Should still be able to decrypt data encrypted with key1
        assert decrypt(ciphertext1) == "data1"

        # New encryptions use key2
        ciphertext2 = encrypt("data2")

        # If we remove key2, we can't decrypt ciphertext2 but we can decrypt ciphertext1 if key1 is there
        mock_settings.ENCRYPTION_KEY = self.key1
        assert decrypt(ciphertext1) == "data1"
        from cryptography.fernet import InvalidToken
        with pytest.raises(InvalidToken):
            decrypt(ciphertext2)

    def test_startup_validation_valid(self, mock_settings):
        # Should not raise
        validate_encryption_settings()

    def test_startup_validation_duplicate_key(self, mock_settings):
        mock_settings.ENCRYPTION_KEY = mock_settings.SECRET_KEY
        with pytest.raises(ImproperlyConfigured, match="must not be equal to APP_SECRET_KEY"):
            validate_encryption_settings()

    def test_startup_validation_weak_key(self, mock_settings):
        mock_settings.ENCRYPTION_KEY = "too-short"
        with pytest.raises(ImproperlyConfigured, match="Invalid Fernet key"):
            validate_encryption_settings()

    def test_startup_validation_missing_key(self, mock_settings):
        mock_settings.ENCRYPTION_KEY = ""
        with pytest.raises(ImproperlyConfigured, match="ENCRYPTION_KEY setting is missing or empty."):
            validate_encryption_settings()

    def test_mask_value(self):
        assert mask_value("1234567890") == "••••••7890"
        assert mask_value("abcd") == "••••"
        assert mask_value("") == ""
        assert mask_value("12345") == "••••••2345"
        assert mask_value("12345", visible_chars=2) == "••••••45"
