"""HTML views for the browser-facing Code Agent application."""

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, NamedTuple
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.templating import Jinja2Templates

from src.constants import APP_DIR
from src.db.models import TimeEntry, User
from src.db.repositories import ProjectRepository, TimeEntryRepository
from src.db.services import SASessionUOW
from src.modules.web.auth import (
    authenticate_web_user,
    get_current_web_user,
    login_web_user,
    logout_web_user,
)
from src.settings import AppSettings, get_app_settings
from src.modules.time_tracker import TimeTrackerService
from src.modules.time_tracker.service import TimeTrackerValidationError
from src.utils import utcnow

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=APP_DIR / "modules" / "web" / "templates")
MOSCOW_TIME_ZONE = timezone(timedelta(hours=3))
STATIC_ASSETS_DIR = APP_DIR / "static"


class NavigationItem(NamedTuple):
    """A link shown in the application sidebar."""

    title: str
    path: str
    slug: str


class CalendarPeriod(NamedTuple):
    """The date range and FullCalendar view requested by the user."""

    selected_date: date
    starts_at: datetime
    ends_before: datetime
    view: str


class DashboardTimeSummary(NamedTuple):
    """Time-tracking data rendered on the dashboard for the current week."""

    week_started: date
    total_seconds: int
    session_count: int
    active_entry: TimeEntry | None
    active_seconds: int


NAVIGATION = (
    NavigationItem(title="Dashboard", path="/", slug="dashboard"),
    NavigationItem(title="Time Tracker", path="/time-tracker", slug="time_tracker"),
)


def get_app_version(request: Request) -> str:
    """Return the version configured for the currently running application."""
    app = getattr(request, "app", None)
    settings = getattr(app, "settings", None)
    if isinstance(settings, AppSettings):
        return settings.app_version

    return get_app_settings().app_version


def static_assets_version() -> str:
    """Return a cache-busting version that changes with the web assets."""
    assets = (STATIC_ASSETS_DIR / "css" / "code-agent.css", STATIC_ASSETS_DIR / "js" / "web-ui.js")
    return str(max(asset.stat().st_mtime_ns for asset in assets))


def render_template(
    request: Request,
    template_name: str,
    *,
    title: str,
    current: str,
    current_user: User | None,
    context: dict[str, Any] | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    """Render a page with values shared by the application shell."""
    return templates.TemplateResponse(
        request,
        template_name,
        {
            "title": title,
            "current": current,
            "current_user": current_user,
            "navigation": NAVIGATION,
            "app_version": get_app_version(request),
            "static_assets_version": static_assets_version(),
        }
        | (context or {}),
        status_code=status_code,
    )


async def require_web_user(request: Request) -> User | RedirectResponse:
    """Return the signed-in user or redirect the browser to login."""
    user = await get_current_web_user(request)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)
    return user


def calendar_period(request: Request) -> CalendarPeriod:
    """Build a safe calendar period from the optional page query parameters."""
    try:
        selected_date = date.fromisoformat(request.query_params.get("date", ""))
    except ValueError:
        selected_date = datetime.now(MOSCOW_TIME_ZONE).date()

    view = request.query_params.get("view", "week")
    if view == "day":
        starts_at = _moscow_midnight_in_utc(selected_date)
        return CalendarPeriod(selected_date, starts_at, starts_at + timedelta(days=1), view)

    week_start = selected_date - timedelta(days=selected_date.weekday())
    starts_at = _moscow_midnight_in_utc(week_start)
    return CalendarPeriod(selected_date, starts_at, starts_at + timedelta(days=7), "week")


def _moscow_midnight_in_utc(value: date) -> datetime:
    """Convert a Moscow calendar day boundary to the naive UTC storage convention."""
    return (
        datetime.combine(value, time.min, tzinfo=MOSCOW_TIME_ZONE)
        .astimezone(timezone.utc)
        .replace(tzinfo=None)
    )


def redirect_to_tracker(message: str | None = None) -> RedirectResponse:
    """Redirect to the tracker and surface a concise form result."""
    suffix = f"?{urlencode({'message': message})}" if message else ""
    return RedirectResponse(url=f"/time-tracker{suffix}", status_code=303)


def parse_datetime(value: object, label: str, *, required: bool = True) -> datetime | None:
    """Parse HTML datetime-local values into the app's naive UTC datetimes."""
    text = str(value or "").strip()
    if not text and not required:
        return None
    if not text:
        raise TimeTrackerValidationError(f"{label} is required.")
    try:
        return datetime.fromisoformat(text)
    except ValueError as exc:
        raise TimeTrackerValidationError(f"{label} must be a valid date and time.") from exc


def parse_tags(value: object) -> list[str]:
    """Split comma-separated tag input while leaving normalization to the service."""
    return str(value or "").split(",")


def entry_event(entry: TimeEntry) -> dict[str, Any]:
    """Serialize an entry into the event format consumed by FullCalendar."""
    return {
        "id": entry.id,
        "title": f"{entry.project} · {entry.task}",
        "start": entry.started_at.replace(tzinfo=timezone.utc).isoformat(),
        "end": (entry.ended_at or utcnow()).replace(tzinfo=timezone.utc).isoformat(),
        "classNames": (
            ["calendar-event", "calendar-event-running"] if entry.is_running else ["calendar-event"]
        ),
        "extendedProps": {
            "project": entry.project,
            "task": entry.task,
            "note": entry.note or "",
            "tags": [tag.name for tag in entry.tags],
            "is_running": entry.is_running,
        },
    }


def format_duration(total_seconds: int) -> str:
    """Format a duration compactly for a dashboard metric."""
    total_minutes = max(total_seconds, 0) // 60
    hours, minutes = divmod(total_minutes, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"


async def dashboard_time_summary(user_id: int) -> DashboardTimeSummary:
    """Calculate current-week tracked time, including a running timer."""
    now = utcnow()
    week_started = now.date() - timedelta(days=now.weekday())
    starts_at = datetime.combine(week_started, time.min)
    ends_before = starts_at + timedelta(days=7)

    async with SASessionUOW() as uow:
        entries = TimeEntryRepository(uow.session)
        week_entries = await entries.list_overlapping_for_user(user_id, starts_at, ends_before)
        active_entry = await entries.active_for_user(user_id)

    total_seconds = 0
    for entry in week_entries:
        entry_end = entry.ended_at or now
        clipped_start = max(entry.started_at, starts_at)
        clipped_end = min(entry_end, ends_before)
        total_seconds += max(int((clipped_end - clipped_start).total_seconds()), 0)

    active_seconds = 0
    if active_entry is not None:
        active_seconds = max(int((now - active_entry.started_at).total_seconds()), 0)

    return DashboardTimeSummary(
        week_started=week_started,
        total_seconds=total_seconds,
        session_count=len(week_entries),
        active_entry=active_entry,
        active_seconds=active_seconds,
    )


async def time_tracker_context(user_id: int, period: CalendarPeriod) -> dict[str, Any]:
    """Load only the signed-in user's tracker data for the requested calendar range."""
    now = utcnow()
    today_starts_at = datetime.combine(now.date(), time.min)
    tomorrow_starts_at = today_starts_at + timedelta(days=1)
    async with SASessionUOW() as uow:
        entries = TimeEntryRepository(uow.session)
        period_entries = await entries.list_overlapping_for_user(
            user_id, period.starts_at, period.ends_before
        )
        active_entry = await entries.active_for_user(user_id)
        today_entries = await entries.list_overlapping_for_user(
            user_id, today_starts_at, tomorrow_starts_at
        )
        recent_entries = await entries.recent_for_user(user_id)
        project_names = await ProjectRepository(uow.session).list_names()
        task_names = await entries.task_names_for_user(user_id)

    today_total_seconds = sum(
        max(
            int(
                (
                    min(entry.ended_at or now, tomorrow_starts_at)
                    - max(entry.started_at, today_starts_at)
                ).total_seconds()
            ),
            0,
        )
        for entry in today_entries
    )

    return {
        "calendar_events": [entry_event(entry) for entry in period_entries],
        "entries": period_entries,
        "active_entry": active_entry,
        "today_total_seconds": today_total_seconds,
        "today_total_duration": format_duration(today_total_seconds),
        "tracker_rendered_at": now.replace(tzinfo=timezone.utc).isoformat(),
        "recent_entries": recent_entries,
        "project_names": project_names,
        "task_names": task_names,
        "calendar_date": period.selected_date.isoformat(),
        "calendar_view": period.view,
        "previous_date": (
            period.selected_date - timedelta(days=1 if period.view == "day" else 7)
        ).isoformat(),
        "next_date": (
            period.selected_date + timedelta(days=1 if period.view == "day" else 7)
        ).isoformat(),
    }


@router.get("/login", response_class=HTMLResponse, response_model=None)
async def login_page(request: Request) -> HTMLResponse | RedirectResponse:
    """Render the login form for anonymous users."""
    user = await get_current_web_user(request)
    if user is not None:
        return RedirectResponse(url="/", status_code=303)

    return render_template(
        request,
        "login.html",
        title="Sign in",
        current="",
        current_user=None,
        context={"login_error": request.query_params.get("error")},
    )


@router.post("/login", response_model=None)
async def login_submit(request: Request) -> RedirectResponse:
    """Authenticate username and password submitted by the login form."""
    form = await request.form()
    username = str(form.get("username") or "").strip()
    password = str(form.get("password") or "")
    if not username or not password:
        return RedirectResponse(url="/login?error=missing", status_code=303)

    user = await authenticate_web_user(username=username, password=password)
    if user is None:
        return RedirectResponse(url="/login?error=invalid", status_code=303)

    login_web_user(request, user)
    return RedirectResponse(url="/", status_code=303)


@router.post("/logout", response_model=None)
async def logout(request: Request) -> RedirectResponse:
    """Clear the browser session and return to login."""
    logout_web_user(request)
    return RedirectResponse(url="/login", status_code=303)


@router.get("/", response_class=HTMLResponse, response_model=None)
async def dashboard(request: Request) -> HTMLResponse | RedirectResponse:
    """Render the Dashboard with current-week time-tracking status."""
    user = await require_web_user(request)
    if isinstance(user, RedirectResponse):
        return user

    summary = await dashboard_time_summary(user.id)
    return render_template(
        request,
        "dashboard.html",
        title="Dashboard",
        current="dashboard",
        current_user=user,
        context={
            "week_started": summary.week_started,
            "week_duration": format_duration(summary.total_seconds),
            "week_sessions": summary.session_count,
            "active_entry": summary.active_entry,
            "active_duration": format_duration(summary.active_seconds),
        },
    )


@router.get("/time-tracker", response_class=HTMLResponse, response_model=None)
async def time_tracker(request: Request) -> HTMLResponse | RedirectResponse:
    """Render the authenticated user's calendar and time tracker."""
    user = await require_web_user(request)
    if isinstance(user, RedirectResponse):
        return user

    time_tracker_context_value = await time_tracker_context(user.id, calendar_period(request))

    return render_template(
        request,
        "time_tracker.html",
        title="Time Tracker",
        current="time_tracker",
        current_user=user,
        context=time_tracker_context_value | {"message": request.query_params.get("message")},
    )


@router.post("/time-tracker/timer/start", response_model=None)
async def start_timer(request: Request) -> RedirectResponse:
    """Start a timer for the signed-in user."""
    user = await require_web_user(request)
    if isinstance(user, RedirectResponse):
        return user
    form = await request.form()
    try:
        async with SASessionUOW() as uow:
            tracker = TimeTrackerService(uow.session)
            await tracker.start_timer(
                user.id,
                str(form.get("project") or ""),
                str(form.get("task") or ""),
                str(form.get("note") or ""),
                parse_tags(form.get("tags")),
            )
            uow.mark_for_commit()
    except TimeTrackerValidationError as exc:
        return redirect_to_tracker(str(exc))
    return redirect_to_tracker("Timer started.")


@router.post("/time-tracker/timer/stop", response_model=None)
async def stop_timer(request: Request) -> RedirectResponse:
    """Stop the signed-in user's active timer."""
    user = await require_web_user(request)
    if isinstance(user, RedirectResponse):
        return user
    try:
        async with SASessionUOW() as uow:
            await TimeTrackerService(uow.session).stop_timer(user.id)
            uow.mark_for_commit()
    except TimeTrackerValidationError as exc:
        return redirect_to_tracker(str(exc))
    return redirect_to_tracker("Timer stopped and entry saved.")


@router.post("/time-tracker/entries", response_model=None)
async def create_time_entry(request: Request) -> RedirectResponse:
    """Create a completed entry or start a timer from the selected calendar time."""
    user = await require_web_user(request)
    if isinstance(user, RedirectResponse):
        return user
    form = await request.form()
    try:
        started_at = parse_datetime(form.get("started_at"), "Start time")
        ended_at = parse_datetime(form.get("ended_at"), "End time", required=False)
        assert started_at is not None
        async with SASessionUOW() as uow:
            tracker = TimeTrackerService(uow.session)
            if ended_at is None:
                await tracker.start_timer(
                    user.id,
                    str(form.get("project") or ""),
                    str(form.get("task") or ""),
                    str(form.get("note") or ""),
                    parse_tags(form.get("tags")),
                    started_at=started_at,
                )
            else:
                await tracker.create_entry(
                    user.id,
                    str(form.get("project") or ""),
                    str(form.get("task") or ""),
                    str(form.get("note") or ""),
                    started_at,
                    ended_at,
                    parse_tags(form.get("tags")),
                )
            uow.mark_for_commit()
    except TimeTrackerValidationError as exc:
        return redirect_to_tracker(str(exc))
    return redirect_to_tracker("Timer started." if ended_at is None else "Time entry created.")


@router.post("/time-tracker/entries/{entry_id}", response_model=None)
async def update_time_entry(entry_id: int, request: Request) -> RedirectResponse:
    """Update a time entry if it belongs to the signed-in user."""
    user = await require_web_user(request)
    if isinstance(user, RedirectResponse):
        return user
    form = await request.form()
    try:
        started_at = parse_datetime(form.get("started_at"), "Start time")
        ended_at = parse_datetime(form.get("ended_at"), "End time", required=False)
        assert started_at is not None
        async with SASessionUOW() as uow:
            tracker = TimeTrackerService(uow.session)
            entry = await tracker.entries.get_for_user(entry_id, user.id)
            if entry is None:
                return redirect_to_tracker("Time entry not found.")
            await tracker.update_entry(
                entry,
                str(form.get("project") or ""),
                str(form.get("task") or ""),
                str(form.get("note") or ""),
                started_at,
                ended_at,
                parse_tags(form.get("tags")),
            )
            uow.mark_for_commit()
    except TimeTrackerValidationError as exc:
        return redirect_to_tracker(str(exc))
    return redirect_to_tracker("Time entry updated.")


@router.post("/time-tracker/entries/{entry_id}/delete", response_model=None)
async def delete_time_entry(entry_id: int, request: Request) -> RedirectResponse:
    """Delete a time entry if it belongs to the signed-in user."""
    user = await require_web_user(request)
    if isinstance(user, RedirectResponse):
        return user
    async with SASessionUOW() as uow:
        entries = TimeEntryRepository(uow.session)
        entry = await entries.get_for_user(entry_id, user.id)
        if entry is None:
            return redirect_to_tracker("Time entry not found.")
        await entries.delete(entry)
        uow.mark_for_commit()
    return redirect_to_tracker("Time entry deleted.")
