from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Project, TimeEntry
from src.db.repositories import ProjectRepository, TimeEntryRepository
from src.modules.time_tracker.service import TimeTrackerService, TimeTrackerValidationError
from src.modules.web.views import (
    CalendarPeriod,
    calendar_period,
    entry_event,
    parse_datetime,
    parse_tags,
)


def test_manual_entry_rejects_an_invalid_time_range() -> None:
    with pytest.raises(TimeTrackerValidationError, match="End time must be after"):
        TimeTrackerService._validate_range(
            datetime(2026, 7, 22, 10, 0), datetime(2026, 7, 22, 10, 0)
        )


async def test_start_timer_rejects_a_second_active_timer() -> None:
    session = AsyncMock(spec=AsyncSession)
    active_entry = TimeEntry(
        user_id=1,
        project="code-agent",
        task="Issue #36",
        started_at=datetime(2026, 7, 22, 9, 0),
    )
    with patch.object(TimeEntryRepository, "active_for_user", AsyncMock(return_value=active_entry)):
        with pytest.raises(TimeTrackerValidationError, match="already running"):
            await TimeTrackerService(session).start_timer(1, "code-agent", "Issue #36", None, [])


async def test_create_entry_requires_a_project_configured_in_administration() -> None:
    session = AsyncMock(spec=AsyncSession)
    with patch.object(ProjectRepository, "get_by_name", AsyncMock(return_value=None)):
        with pytest.raises(TimeTrackerValidationError, match="configured in Administration"):
            await TimeTrackerService(session).create_entry(
                1,
                "not-configured",
                "Issue #36",
                None,
                datetime(2026, 7, 22, 9, 0),
                datetime(2026, 7, 22, 10, 0),
                [],
            )


async def test_create_entry_links_the_configured_project() -> None:
    session = AsyncMock(spec=AsyncSession)
    project = Project(id=7, name="code-agent")
    with patch.object(ProjectRepository, "get_by_name", AsyncMock(return_value=project)):
        entry = await TimeTrackerService(session).create_entry(
            1,
            "code-agent",
            "Issue #36",
            None,
            datetime(2026, 7, 22, 9, 0),
            datetime(2026, 7, 22, 10, 0),
            [],
        )

    assert entry.project == "code-agent"
    assert entry.project_id == 7


def test_tracker_form_helpers_parse_calendar_and_tag_input(mock_request: MagicMock) -> None:
    mock_request.query_params = {"date": "2026-07-22", "view": "day"}

    period = calendar_period(mock_request)

    assert period == CalendarPeriod(
        selected_date=datetime(2026, 7, 22).date(),
        starts_at=datetime(2026, 7, 21, 21),
        ends_before=datetime(2026, 7, 22, 21),
        view="day",
    )
    assert parse_datetime("2026-07-22T10:15", "Start time") == datetime(2026, 7, 22, 10, 15)
    assert parse_tags("feature,  planning") == ["feature", "  planning"]


def test_tracker_form_helpers_reject_an_invalid_datetime() -> None:
    with pytest.raises(TimeTrackerValidationError, match="valid date"):
        parse_datetime("not-a-date", "Start time")


def test_entry_event_includes_fields_needed_by_the_calendar_edit_dialog() -> None:
    entry = TimeEntry(
        id=9,
        user_id=1,
        project="code-agent",
        task="Issue #36",
        note="Calendar polish",
        started_at=datetime(2026, 7, 22, 10, 0),
        ended_at=datetime(2026, 7, 22, 10, 5),
    )

    event = entry_event(entry)

    assert event["extendedProps"] == {
        "project": "code-agent",
        "task": "Issue #36",
        "note": "Calendar polish",
        "tags": [],
        "is_running": False,
    }
    assert event["start"] == "2026-07-22T10:00:00+00:00"
    assert event["end"] == "2026-07-22T10:05:00+00:00"


def test_running_entry_event_extends_to_the_current_time() -> None:
    entry = TimeEntry(
        id=10,
        user_id=1,
        project="code-agent",
        task="Issue #36",
        started_at=datetime(2026, 7, 22, 10, 0),
    )
    now = datetime(2026, 7, 22, 11, 30)

    with patch("src.modules.web.views.utcnow", return_value=now):
        event = entry_event(entry)

    assert event["end"] == "2026-07-22T11:30:00+00:00"
    assert event["extendedProps"]["is_running"] is True
