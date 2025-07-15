"""Generate a secure encryption key for vendor API keys."""

import base64
import secrets


def generate_key(length: int = 32) -> str:
    """Generate a secure random encryption key.

    Args:
        length: Length of the key in bytes (default: 32 for AES-256)

    Returns:
        Base64 encoded key string
    """
    random_bytes = secrets.token_bytes(length)
    return base64.b64encode(random_bytes).decode()


def main() -> None:
    """Generate and display an encryption key."""
    print("Generating secure encryption key for vendor API keys...")
    print()

    key = generate_key()

    print("Add this to your .env file:")
    print(f"VENDOR_ENCRYPTION_KEY={key}")
    print()
    print("⚠️  Important:")
    print("- Keep this key secure and consistent across deployments")
    print("- If you change this key, existing encrypted API keys will become unusable")
    print("- Use at least 32 characters for strong security")


if __name__ == "__main__":
    main()
