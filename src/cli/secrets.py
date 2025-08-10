"""Generate a secure encryption key for vendor API keys."""

import secrets


def main() -> None:
    """Generate and display an encryption key."""
    print("Generating secure secrets...", end="\n\n")

    secret_key = secrets.token_urlsafe(32)
    vendor_encryption_key = secrets.token_urlsafe(32)
    db_password = secrets.token_urlsafe(15)
    admin_password = secrets.token_urlsafe(15)

    print("Add this to your .env file:", end="\n\n")

    print(f"SECRET_KEY={secret_key}")
    print(f"VENDOR_ENCRYPTION_KEY={vendor_encryption_key}")
    print(f"DB_PASSWORD={db_password}")
    print(f"ADMIN_PASSWORD={admin_password}")

    print("\n⚠️  Important:")
    print("- Keep this secrets secure and consistent across deployments")
    print("- If you change this secrets, existing encrypted API keys will become unusable")
    print("- Use at least 32 characters for strong security")


if __name__ == "__main__":
    main()
