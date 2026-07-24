"""Business rules for user-owned time entries and timers."""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Project, Tag, TimeEntry
from src.db.repositories import ProjectRepository, TagRepository, TimeEntryRepository
from src.utils import utcnow


class TimeTrackerValidationError(ValueError):
    """Raised when an entry or timer request is not valid."""


class TimeTrackerService:
    """Apply time-tracking rules within a single database session."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.entries = TimeEntryRepository(session)
        self.tags = TagRepository(session)
        self.projects = ProjectRepository(session)

    async def start_timer(
        self,
        user_id: int,
        project: str,
        task: str,
        note: str | None,
        tag_names: list[str],
        *,
        started_at: datetime | None = None,
    ) -> TimeEntry:
        """Start a timer unless the user already has an active one."""
        if await self.entries.active_for_user(user_id) is not None:
            raise TimeTrackerValidationError("A timer is already running.")

        configured_project = await self._resolve_project(project)
        entry = TimeEntry(
            user_id=user_id,
            project_id=configured_project.id,
            project=configured_project.name,
            task=self._required_text(task, "Task"),
            note=self._optional_text(note),
            started_at=(started_at or utcnow()).replace(microsecond=0),
        )
        entry.tags = await self._resolve_tags(tag_names)
        self.session.add(entry)
        return entry

    async def stop_timer(self, user_id: int) -> TimeEntry:
        """Stop the user's active timer."""
        entry = await self.entries.active_for_user(user_id)
        if entry is None:
            raise TimeTrackerValidationError("There is no active timer to stop.")

        entry.ended_at = utcnow().replace(microsecond=0)
        self.session.add(entry)
        return entry

    async def create_entry(
        self,
        user_id: int,
        project: str,
        task: str,
        note: str | None,
        started_at: datetime,
        ended_at: datetime,
        tag_names: list[str],
    ) -> TimeEntry:
        """Create a completed manually recorded entry."""
        self._validate_range(started_at, ended_at)
        configured_project = await self._resolve_project(project)
        entry = TimeEntry(
            user_id=user_id,
            project_id=configured_project.id,
            project=configured_project.name,
            task=self._required_text(task, "Task"),
            note=self._optional_text(note),
            started_at=started_at,
            ended_at=ended_at,
        )
        entry.tags = await self._resolve_tags(tag_names)
        self.session.add(entry)
        return entry

    async def update_entry(
        self,
        entry: TimeEntry,
        project: str,
        task: str,
        note: str | None,
        started_at: datetime,
        ended_at: datetime | None,
        tag_names: list[str],
    ) -> TimeEntry:
        """Update a user-owned entry while preserving timer validity."""
        if entry.is_running and ended_at is not None:
            self._validate_range(started_at, ended_at)
        elif not entry.is_running and ended_at is None:
            raise TimeTrackerValidationError("A completed entry must have an end time.")
        elif ended_at is not None:
            self._validate_range(started_at, ended_at)

        configured_project = await self._resolve_project(project)
        entry.project_id = configured_project.id
        entry.project = configured_project.name
        entry.task = self._required_text(task, "Task")
        entry.note = self._optional_text(note)
        entry.started_at = started_at
        entry.ended_at = ended_at
        entry.tags = await self._resolve_tags(tag_names)
        self.session.add(entry)
        return entry

    async def _resolve_tags(self, tag_names: list[str]) -> list[Tag]:
        names = list(dict.fromkeys(name.strip().lower() for name in tag_names if name.strip()))
        return [await self.tags.get_or_create_by_name(name) for name in names]

    async def _resolve_project(self, name: str) -> Project:
        """Resolve a project that an administrator has configured."""
        normalized_name = self._required_text(name, "Project")
        project = await self.projects.get_by_name(normalized_name)
        if project is None:
            raise TimeTrackerValidationError(
                "Choose a project configured in Administration before tracking time."
            )
        return project

    @staticmethod
    def _required_text(value: str, label: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise TimeTrackerValidationError(f"{label} is required.")
        return normalized

    @staticmethod
    def _optional_text(value: str | None) -> str | None:
        normalized = (value or "").strip()
        return normalized or None

    @staticmethod
    def _validate_range(started_at: datetime, ended_at: datetime) -> None:
        if ended_at <= started_at:
            raise TimeTrackerValidationError("End time must be after the start time.")
