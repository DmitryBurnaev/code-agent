"""HTML views for the browser-facing Code Agent application."""

from typing import Any, NamedTuple

from fastapi import APIRouter, Request
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.templating import Jinja2Templates

from src.constants import APP_DIR
from src.db.models import User
from src.modules.web.auth import (
    authenticate_web_user,
    get_current_web_user,
    login_web_user,
    logout_web_user,
)
from src.settings import AppSettings, get_app_settings

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=APP_DIR / "modules" / "web" / "templates")


class NavigationItem(NamedTuple):
    """A link shown in the application sidebar."""

    title: str
    path: str
    slug: str


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
    """Render the Dashboard placeholder."""
    user = await require_web_user(request)
    if isinstance(user, RedirectResponse):
        return user

    return render_template(
        request,
        "dashboard.html",
        title="Dashboard",
        current="dashboard",
        current_user=user,
    )


@router.get("/time-tracker", response_class=HTMLResponse, response_model=None)
async def time_tracker(request: Request) -> HTMLResponse | RedirectResponse:
    """Render the Time Tracker placeholder."""
    user = await require_web_user(request)
    if isinstance(user, RedirectResponse):
        return user

    return render_template(
        request,
        "time_tracker.html",
        title="Time Tracker",
        current="time_tracker",
        current_user=user,
    )
