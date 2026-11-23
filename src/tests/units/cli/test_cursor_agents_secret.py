from pathlib import Path
import re

import pytest

from src.modules.cli.ensure_cursor_agents_secret import ensure_cursor_agents_secret


@pytest.mark.parametrize("assignment", ["", "CURSOR_AGENTS_SECRET=\n"])
def test_generate_cursor_secret_preserves_other_settings(tmp_path: Path, assignment: str) -> None:
    env_file = tmp_path / ".env"
    other_settings = "# Existing settings\nAPP_SECRET_KEY='fixture-existing-key'\n"
    env_file.write_text(other_settings + assignment, encoding="utf-8")

    assert ensure_cursor_agents_secret(env_file)
    updated = env_file.read_text(encoding="utf-8")
    assert updated.startswith(other_settings)
    assert re.fullmatch(
        r"CURSOR_AGENTS_SECRET=[a-f0-9]{64}\n", updated.removeprefix(other_settings)
    )

    assert not ensure_cursor_agents_secret(env_file)
    assert env_file.read_text(encoding="utf-8") == updated


def test_preserve_existing_cursor_secret(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    existing = "# Existing Cursor configuration\nexport CURSOR_AGENTS_SECRET='fixture-secret'\n"
    env_file.write_text(existing, encoding="utf-8")

    assert not ensure_cursor_agents_secret(env_file)
    assert env_file.read_text(encoding="utf-8") == existing
