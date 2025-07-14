"""Vendor API key encryption module using AES-256-GCM."""

import base64
import logging
from typing import Any

from Cryptodome.Cipher import AES
from Cryptodome.Random import get_random_bytes
from pydantic import SecretStr

logger = logging.getLogger(__name__)


class VendorKeyEncryption:
    """AES-256-GCM encryption for vendor API keys.
    
    Uses authenticated encryption to ensure both confidentiality and integrity.
    Each encryption operation uses a random nonce for security.
    """

    # AES-256 requires 32 bytes key
    KEY_SIZE = 32
    # GCM nonce size (12 bytes is recommended for AES-GCM)
    NONCE_SIZE = 12
    # GCM tag size (16 bytes for full authentication)
    TAG_SIZE = 16

    def __init__(self, secret_key: SecretStr) -> None:
        """Initialize encryption with secret key.
        
        Args:
            secret_key: Secret key for encryption/decryption
        """
        self._secret_key = self._derive_key(secret_key.get_secret_value())

    def _derive_key(self, secret_key: str) -> bytes:
        """Derive a 32-byte key from the secret string.
        
        Uses SHA-256 to ensure consistent key size for AES-256.
        """
        import hashlib
        return hashlib.sha256(secret_key.encode()).digest()

    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext API key.
        
        Args:
            plaintext: API key to encrypt
            
        Returns:
            Base64 encoded encrypted data (nonce + ciphertext + tag)
        """
        if not plaintext:
            raise ValueError("Plaintext cannot be empty")

        # Generate random nonce
        nonce = get_random_bytes(self.NONCE_SIZE)
        
        # Create cipher
        cipher = AES.new(self._secret_key, AES.MODE_GCM, nonce=nonce)
        
        # Encrypt and get tag
        ciphertext, tag = cipher.encrypt_and_digest(plaintext.encode())
        
        # Combine nonce + ciphertext + tag
        encrypted_data = nonce + ciphertext + tag
        
        # Return base64 encoded
        return base64.b64encode(encrypted_data).decode()

    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt encrypted API key.
        
        Args:
            encrypted_data: Base64 encoded encrypted data
            
        Returns:
            Decrypted API key
            
        Raises:
            ValueError: If decryption fails or data is corrupted
        """
        if not encrypted_data:
            raise ValueError("Encrypted data cannot be empty")

        try:
            # Decode base64
            data = base64.b64decode(encrypted_data)
            
            # Extract components
            if len(data) < self.NONCE_SIZE + self.TAG_SIZE:
                raise ValueError("Encrypted data too short")
                
            nonce = data[:self.NONCE_SIZE]
            tag = data[-self.TAG_SIZE:]
            ciphertext = data[self.NONCE_SIZE:-self.TAG_SIZE]
            
            # Create cipher
            cipher = AES.new(self._secret_key, AES.MODE_GCM, nonce=nonce)
            
            # Decrypt and verify
            plaintext = cipher.decrypt_and_verify(ciphertext, tag)
            
            return plaintext.decode()
            
        except Exception as exc:
            logger.error("Failed to decrypt vendor API key: %s", exc)
            raise ValueError("Failed to decrypt API key") from exc

    def is_encrypted(self, data: str) -> bool:
        """Check if data appears to be encrypted.
        
        Args:
            data: Data to check
            
        Returns:
            True if data looks like encrypted data
        """
        if not data:
            return False
            
        try:
            decoded = base64.b64decode(data)
            # Check if it has the expected structure: nonce + ciphertext + tag
            return len(decoded) >= self.NONCE_SIZE + self.TAG_SIZE
        except Exception:
            return False 