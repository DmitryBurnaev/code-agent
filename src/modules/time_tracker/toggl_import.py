"""Import Toggl CSV exports into configured projects and time entries."""

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta
from io import StringIO

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Client, Project, TimeEntry
from src.db.repositories import (
    ClientRepository,
    ProjectRepository,
    TagRepository,
    TimeEntryRepository,
)

TOGGL_REQUIRED_COLUMNS = frozenset(
    {"Project", "Start date", "Start time", "End date", "End time", "Duration"}
)


class TogglImportValidationError(ValueError):
    """Raised when a Toggl CSV file cannot be imported safely."""


@dataclass(frozen=True)
class TogglEntry:
    """Normalized representation of one completed Toggl work session."""

    client_name: str | None
    project_name: str
    task: str
    note: str | None
    started_at: datetime
    ended_at: datetime
    tag_names: list[str]


@dataclass(frozen=True)
class TogglImportResult:
    """Counts displayed after a completed Toggl import."""

    imported_entries: int
    skipped_entries: int
    created_clients: int
    created_projects: int


def parse_toggl_csv(contents: bytes) -> list[TogglEntry]:
    """Validate and parse a standard Toggl time-entries CSV export."""
    try:
        text = contents.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise TogglImportValidationError("The CSV file must use UTF-8 encoding.") from exc

    reader = csv.DictReader(StringIO(text))
    fields = set(reader.fieldnames or ())
    missing_columns = TOGGL_REQUIRED_COLUMNS - fields
    if missing_columns:
        names = ", ".join(sorted(missing_columns))
        raise TogglImportValidationError(f"Missing Toggl CSV columns: {names}.")

    entries: list[TogglEntry] = []
    try:
        for row_number, row in enumerate(reader, start=2):
            entries.append(_parse_row(row_number, row))
    except csv.Error as exc:
        raise TogglImportValidationError(f"Invalid CSV data: {exc}.") from exc

    if not entries:
        raise TogglImportValidationError("The CSV file does not contain any time entries.")
    return entries


def _parse_row(row_number: int, row: dict[str, str | None]) -> TogglEntry:
    project_name = _required_value(row_number, row, "Project")
    description = _optional_value(row, "Description")
    task = _optional_value(row, "Task") or description or "Imported Toggl entry"
    started_at = _parse_datetime(row_number, row, "Start date", "Start time")
    ended_at = _parse_end_datetime(row_number, row, started_at)
    if ended_at <= started_at:
        raise TogglImportValidationError(f"Row {row_number}: end time must be after start time.")

    tags = [tag.strip() for tag in (_optional_value(row, "Tags") or "").split(",") if tag.strip()]
    return TogglEntry(
        client_name=_optional_value(row, "Client"),
        project_name=project_name,
        task=task,
        note=description,
        started_at=started_at,
        ended_at=ended_at,
        tag_names=tags,
    )


def _required_value(row_number: int, row: dict[str, str | None], name: str) -> str:
    value = _optional_value(row, name)
    if value is None:
        raise TogglImportValidationError(f"Row {row_number}: {name} is required.")
    return value


def _optional_value(row: dict[str, str | None], name: str) -> str | None:
    value = (row.get(name) or "").strip()
    return value or None


def _parse_datetime(
    row_number: int, row: dict[str, str | None], date_column: str, time_column: str
) -> datetime:
    date_value = _required_value(row_number, row, date_column)
    time_value = _required_value(row_number, row, time_column)
    try:
        return datetime.fromisoformat(f"{date_value}T{time_value}")
    except ValueError as exc:
        raise TogglImportValidationError(
            f"Row {row_number}: {date_column} and {time_column} must be valid date and time values."
        ) from exc


def _parse_end_datetime(
    row_number: int, row: dict[str, str | None], started_at: datetime
) -> datetime:
    end_date = _optional_value(row, "End date")
    end_time = _optional_value(row, "End time")
    if end_date is not None and end_time is not None:
        return _parse_datetime(row_number, row, "End date", "End time")
    if end_date is not None or end_time is not None:
        raise TogglImportValidationError(
            f"Row {row_number}: end date and end time must be provided together."
        )
    return started_at + _parse_duration(row_number, _required_value(row_number, row, "Duration"))


def _parse_duration(row_number: int, value: str) -> timedelta:
    try:
        hours, minutes, seconds = (int(part) for part in value.split(":"))
        return timedelta(hours=hours, minutes=minutes, seconds=seconds)
    except ValueError as exc:
        raise TogglImportValidationError(
            f"Row {row_number}: Duration must use the HH:MM:SS format."
        ) from exc


class TogglImportService:
    """Persist parsed Toggl data in one transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.clients = ClientRepository(session)
        self.projects = ProjectRepository(session)
        self.tags = TagRepository(session)
        self.entries = TimeEntryRepository(session)
        self._clients_by_name: dict[str, Client] = {}
        self._projects_by_name: dict[str, Project] = {}

    async def import_csv(self, user_id: int, contents: bytes) -> TogglImportResult:
        """Create clients, projects, tags, and non-duplicate completed entries."""
        imported_entries = 0
        skipped_entries = 0
        created_clients = 0
        created_projects = 0
        imported_fingerprints: set[tuple[int, str, str | None, datetime, datetime]] = set()

        for toggl_entry in parse_toggl_csv(contents):
            project, client_created, project_created = await self._resolve_project(toggl_entry)
            created_clients += int(client_created)
            created_projects += int(project_created)
            fingerprint = (
                project.id,
                toggl_entry.task,
                toggl_entry.note,
                toggl_entry.started_at,
                toggl_entry.ended_at,
            )
            if fingerprint in imported_fingerprints or await self.entries.find_matching_entry(
                user_id=user_id,
                project_id=project.id,
                task=toggl_entry.task,
                note=toggl_entry.note,
                started_at=toggl_entry.started_at,
                ended_at=toggl_entry.ended_at,
            ):
                skipped_entries += 1
                continue

            entry = TimeEntry(
                user_id=user_id,
                project_id=project.id,
                project=project.name,
                task=toggl_entry.task,
                note=toggl_entry.note,
                started_at=toggl_entry.started_at,
                ended_at=toggl_entry.ended_at,
            )
            entry.tags = [
                await self.tags.get_or_create_by_name(tag_name)
                for tag_name in toggl_entry.tag_names
            ]
            self.session.add(entry)
            imported_fingerprints.add(fingerprint)
            imported_entries += 1

        return TogglImportResult(
            imported_entries=imported_entries,
            skipped_entries=skipped_entries,
            created_clients=created_clients,
            created_projects=created_projects,
        )

    async def _resolve_project(self, entry: TogglEntry) -> tuple[Project, bool, bool]:
        client, client_created = await self._resolve_client(entry.client_name)
        cached_project = self._projects_by_name.get(entry.project_name)
        if cached_project is not None:
            self._ensure_project_client(cached_project, client)
            return cached_project, client_created, False

        project = await self.projects.get_by_name(entry.project_name)
        project_created = False
        if project is None:
            project = Project(name=entry.project_name, client=client)
            self.session.add(project)
            await self.session.flush()
            project_created = True
        else:
            self._ensure_project_client(project, client)

        self._projects_by_name[entry.project_name] = project
        return project, client_created, project_created

    async def _resolve_client(self, name: str | None) -> tuple[Client | None, bool]:
        if name is None:
            return None, False
        cached_client = self._clients_by_name.get(name)
        if cached_client is not None:
            return cached_client, False

        client = await self.clients.get_by_name(name)
        client_created = False
        if client is None:
            client = Client(name=name)
            self.session.add(client)
            await self.session.flush()
            client_created = True

        self._clients_by_name[name] = client
        return client, client_created

    @staticmethod
    def _ensure_project_client(project: Project, client: Client | None) -> None:
        if client is None:
            return
        if project.client_id is None:
            project.client = client
            return
        if project.client_id != client.id:
            raise TogglImportValidationError(
                f"Project '{project.name}' is already assigned to another client in Administration."
            )
