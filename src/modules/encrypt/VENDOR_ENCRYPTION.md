# Vendor API Key Encryption

This document describes the implementation of vendor API key encryption in the code-agent application.

## Overview

Vendor API keys are now encrypted using AES-256-GCM before being stored in the database. This provides both confidentiality and integrity protection for sensitive API credentials.

## Implementation Details

### Encryption Algorithm
- **Algorithm**: AES-256-GCM (Galois/Counter Mode)
- **Key Derivation**: SHA-256 hash of the secret key
- **Nonce**: 12 bytes (random for each encryption)
- **Tag**: 16 bytes (authentication tag)
- **Encoding**: Base64 for storage

### Key Features
- **Authenticated Encryption**: GCM mode provides both encryption and integrity verification
- **Random Nonce**: Each encryption uses a unique nonce for security
- **Error Handling**: Clear error messages if decryption fails

## Configuration

### Environment Variable
Add the following environment variable to your `.env` file:

```bash
VENDOR_ENCRYPTION_KEY=your-secret-key-here
```

**Important**: 
- Use a strong, random secret key (at least 32 characters)
- Keep this key secure and consistent across deployments
- If you change this key, existing encrypted API keys will become unusable

### Example Secret Key Generation
```bash
# Generate a random 32-character key using the CLI tool
python -m src.cli.generate_encryption_key

# Or using openssl
openssl rand -base64 24
```

## Usage

### In Admin Interface
API keys are automatically encrypted when:
- Creating a new vendor in the admin interface
- Updating an existing vendor's API key

### In Code
```python
from src.db.models import Vendor
from src.modules.auth.encryption import VendorKeyEncryption
from src.settings import get_app_settings

# Create vendor with encrypted API key
vendor = Vendor()
vendor.slug = "openai"
vendor.api_url = "https://api.openai.com/v1"

# Encrypt API key manually if needed
settings = get_app_settings()
encryption = VendorKeyEncryption(settings.vendor_encryption_key)
vendor.api_key = encryption.encrypt("sk-your-openai-key-here")

# Retrieve decrypted API key
decrypted_key = vendor.decrypted_api_key
```

## Migration

### For New Installations
No special migration is required. API keys will be encrypted automatically.

### For Existing Installations
All API keys must be encrypted. If you have existing unencrypted keys, they will need to be re-encrypted through the admin interface.

## Security Considerations

1. **Key Management**: Store the encryption key securely and rotate it periodically
2. **Database Access**: Ensure database access is restricted and encrypted
3. **Logging**: API keys are never logged in plaintext
4. **Memory**: Decrypted keys are only available in memory during request processing

## Testing

Run the encryption tests:
```bash
python -m pytest src/tests/units/test_vendor_encryption.py -v
python -m pytest src/tests/units/test_vendor_model_encryption.py -v
```

## Troubleshooting

### Common Issues

1. **Decryption Fails**: Check that the `VENDOR_ENCRYPTION_KEY` environment variable is set correctly
2. **Key Rotation**: If you need to change the encryption key, you'll need to re-encrypt all API keys

### Debug Mode
Enable debug logging to see encryption/decryption operations:
```bash
LOG_LEVEL=DEBUG
```

## Performance

- **Encryption**: ~1ms per operation
- **Decryption**: ~1ms per operation  
- **Memory Usage**: Minimal overhead
- **Database Storage**: Encrypted keys are ~1.5x larger than original

The encryption is designed to be fast enough for high-frequency API requests while maintaining strong security. 