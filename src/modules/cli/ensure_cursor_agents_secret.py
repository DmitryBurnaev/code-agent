"""Initialize the shared Cursor service secret in the project dotenv file."""

from fcntl import LOCK_EX, flock
import os
from pathlib import Path
from secrets import token_hex

from dotenv import dotenv_values, set_key

SECRET_NAME = "CURSOR_AGENTS_SECRET"


def ensure_cursor_agents_secret(env_path: Path) -> bool:
    """Set a missing or empty secret and report whether it was generated."""
    env_path = env_path.resolve()
    while True:
        descriptor = os.open(env_path, os.O_CREAT | os.O_RDWR, 0o600)
        with os.fdopen(descriptor, encoding="utf-8") as env_file:
            flock(descriptor, LOCK_EX)
            # dotenv replaces the file atomically. Retry if another invocation replaced it.
            if not os.path.samestat(os.fstat(descriptor), env_path.stat()):
                continue
            value = dotenv_values(stream=env_file, interpolate=False).get(SECRET_NAME)
            if value and value.strip():
                return False
            set_key(env_path, SECRET_NAME, token_hex(32), quote_mode="never")
            return True


if __name__ == "__main__":
    if ensure_cursor_agents_secret(Path(".env")):
        print("CURSOR_AGENTS_SECRET saved to .env")
