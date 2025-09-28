"""
CLI for some management operations
"""

import asyncio
import os
import click
import secrets

from src.db import (
    get_session_factory,
    initialize_database,
    close_database,
    SASessionUOW,
    UserRepository,
    User,
)

DEFAULT_ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
MIN_PASSWORD_LENGTH: int = int(os.getenv("MIN_PASSWORD_LENGTH", 1))
DEFAULT_PASSWORD_LENGTH: int = int(os.getenv("DEFAULT_PASSWORD_LENGTH", MIN_PASSWORD_LENGTH))


async def update_user(username: str, new_password: str) -> bool:
    """Make users find and update operations"""

    await initialize_database()
    success = False
    try:
        async with SASessionUOW() as uow:
            user_repo = UserRepository(session=uow.session)
            user = await user_repo.get_by_username(username)
            if user is not None:
                click.echo(f"Found user {username}. Lets update him password :)")
                user.password = User.make_password(new_password)
                uow.mark_for_commit()
                success = True
            else:
                click.echo(f"User {username} not found.")

    except Exception as exc:
        click.echo(f"Unable to update user: {exc!r}", err=True)
        success = False

    finally:
        await close_database()

    return success


@click.command("change-admin-password", help="Change the admin password.")
@click.help_option("--help", help="Show this help message")
@click.option("--username", default=DEFAULT_ADMIN_USERNAME, help="Admin username")
@click.option(
    "--random-password",
    "random_password",
    default=False,
    is_flag=True,
    help="Generate a random password.",
)
@click.option(
    "--random-password-length",
    "random_password_length",
    default=DEFAULT_PASSWORD_LENGTH,
    help="Set length of generated random password.",
)
def change_admin_password(
    username: str,
    random_password: bool = False,
    random_password_length: int = DEFAULT_PASSWORD_LENGTH,
) -> None:
    click.echo("===")
    click.echo("Changing admin password...")
    password: str
    if random_password:
        click.echo("Generating a random password...")
        password = secrets.token_urlsafe(random_password_length)
    else:
        click.echo(f"Set a new password for {username}")
        password = click.prompt("New Password", hide_input=True, confirmation_prompt=True)
        if len(password) < MIN_PASSWORD_LENGTH:
            raise click.exceptions.BadParameter(
                f"Password must be at least {MIN_PASSWORD_LENGTH} characters long."
            )

    success_updated = asyncio.run(update_user(username, password))
    if success_updated:
        click.echo(f"Password for user '{username}' updated.")
        if random_password:
            click.echo(f"New password: '{password}'")

    else:
        click.echo(f"Password for user '{username}' wasn't updated.")


if __name__ == "__main__":
    change_admin_password()
