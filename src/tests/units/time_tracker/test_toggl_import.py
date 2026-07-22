from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Client, Project, Tag, TimeEntry
from src.db.repositories import (
    ClientRepository,
    ProjectRepository,
    TagRepository,
    TimeEntryRepository,
)
from src.modules.time_tracker.toggl_import import (
    TogglImportService,
    TogglImportValidationError,
    parse_toggl_csv,
)

TOGGL_CSV = b"""\xef\xbb\xbf"User","Email","Client","Project","Task","Description","Billable","Start date","Start time","End date","End time","Duration","Tags"\n"Dmitry","dmitry@example.com","Hexway","Vampy","","VCS review","No","2023-12-20","16:08:57","2023-12-20","16:32:40","00:23:43","code-review, planning"\n"""


def test_parse_toggl_csv_normalizes_a_standard_export() -> None:
    entries = parse_toggl_csv(TOGGL_CSV)

    assert len(entries) == 1
    entry = entries[0]
    assert entry.client_name == "Hexway"
    assert entry.project_name == "Vampy"
    assert entry.task == "VCS review"
    assert entry.note == "VCS review"
    assert entry.started_at == datetime(2023, 12, 20, 16, 8, 57)
    assert entry.ended_at == datetime(2023, 12, 20, 16, 32, 40)
    assert entry.tag_names == ["code-review", "planning"]


def test_parse_toggl_csv_requires_the_project_column() -> None:
    invalid_csv = b'"Start date","Start time","End date","End time","Duration"\n'

    with pytest.raises(TogglImportValidationError, match="Project"):
        parse_toggl_csv(invalid_csv)


async def test_import_toggl_csv_creates_a_time_entry_for_a_configured_project() -> None:
    session = MagicMock(spec=AsyncSession)
    client = Client(id=4, name="Hexway")
    project = Project(id=7, name="Vampy")
    tags = [Tag(id=9, name="code-review"), Tag(id=10, name="planning")]
    with (
        patch.object(ClientRepository, "get_by_name", AsyncMock(return_value=client)),
        patch.object(ProjectRepository, "get_by_name", AsyncMock(return_value=project)),
        patch.object(TimeEntryRepository, "find_matching_entry", AsyncMock(return_value=None)),
        patch.object(TagRepository, "get_or_create_by_name", AsyncMock(side_effect=tags)),
    ):
        result = await TogglImportService(session).import_csv(3, TOGGL_CSV)

    assert result.imported_entries == 1
    assert result.skipped_entries == 0
    created_entry = session.add.call_args.args[0]
    assert isinstance(created_entry, TimeEntry)
    assert created_entry.user_id == 3
    assert created_entry.project_id == 7
    assert created_entry.task == "VCS review"
    assert created_entry.tags == tags


async def test_import_toggl_csv_skips_an_existing_matching_entry() -> None:
    session = MagicMock(spec=AsyncSession)
    client = Client(id=4, name="Hexway")
    project = Project(id=7, name="Vampy")
    existing_entry = TimeEntry(
        user_id=3,
        project_id=7,
        project="Vampy",
        task="VCS review",
        started_at=datetime(2023, 12, 20, 16, 8, 57),
        ended_at=datetime(2023, 12, 20, 16, 32, 40),
    )
    with (
        patch.object(ClientRepository, "get_by_name", AsyncMock(return_value=client)),
        patch.object(ProjectRepository, "get_by_name", AsyncMock(return_value=project)),
        patch.object(
            TimeEntryRepository, "find_matching_entry", AsyncMock(return_value=existing_entry)
        ),
    ):
        result = await TogglImportService(session).import_csv(3, TOGGL_CSV)

    assert result.imported_entries == 0
    assert result.skipped_entries == 1
    session.add.assert_not_called()
