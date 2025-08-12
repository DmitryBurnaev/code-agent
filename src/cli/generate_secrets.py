"""Generate a secure encryption key for vendor API keys."""
import os
import secrets
from pathlib import Path

ENV_FILE_PATH = Path(".env")


def main() -> None:
    """Generate and display an encryption key, also write to .env file."""
    print("Generating secure secrets...", end="\n\n")

    app_secret_key = secrets.token_urlsafe(32)
    vendor_encryption_key = secrets.token_urlsafe(32)
    db_password = secrets.token_urlsafe(15)
    admin_password = secrets.token_urlsafe(15)

    # Prepare secrets for .env file
    env_secrets = [
        "",
        "# Generated secrets",
        f"DB_PASSWORD={db_password}",
        f"ADMIN_PASSWORD={admin_password}",
        f"VENDOR_ENCRYPTION_KEY={vendor_encryption_key}",
        f"APP_SECRET_KEY={app_secret_key}",
    ]

    # Write to .env file
    try:
        # Append secrets to .env file
        with open(ENV_FILE_PATH, "a", encoding="utf-8") as env_file:
            env_file.write("\n".join(env_secrets) + "\n")

        print(f"✅ Secrets written to {ENV_FILE_PATH}")

    except Exception as e:
        print(f"⚠️  Warning: Could not write to .env file: {e}")
        print("Please add the secrets manually to your .env file")


    # Now change the permissions of the .env file to 600
    try:
        os.chmod(ENV_FILE_PATH, 0o600)
        print(f"✅ Permissions changed to 600 for {ENV_FILE_PATH}")
    except Exception as e:
        print(f"⚠️  Warning: Could not change permissions for {ENV_FILE_PATH}: {e}")
        print("Please change the permissions manually to 600")


if __name__ == "__main__":
    main()
