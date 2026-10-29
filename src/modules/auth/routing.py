"""Mandatory access policies and validation for registered HTTP routes."""

from collections.abc import Iterator

from fastapi import FastAPI
from fastapi.routing import APIRoute, RouteContext, iter_route_contexts
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from src.modules.admin.app import AdminApp
from src.modules.admin.auth import AdminAuth
from src.modules.admin.authorization import FeatureAuthorization
from src.modules.auth.dependencies import APIAccess, WebAccess
from src.modules.auth.permissions import Permission

type Access = APIAccess | WebAccess


def iter_application_routes(app: FastAPI) -> Iterator[RouteContext]:
    """Expand included routers using FastAPI's effective paths and dependencies."""
    yield from iter_route_contexts(app.routes)


def route_access_policies(route: RouteContext) -> list[Access]:
    """Inspect executed dependencies rather than trusting endpoint labels."""
    dependant = getattr(route, "dependant", None)
    if dependant is None:
        return []
    return [
        dependency.call
        for dependency in dependant.dependencies
        if isinstance(dependency.call, (APIAccess, WebAccess))
    ]


def validate_access_policies(app: FastAPI) -> None:
    """Reject missing policies and accidental expansion of public/auth-only access."""
    public = {("GET", "/login"), ("POST", "/login"), ("POST", "/logout")}
    docs = {
        "openapi": app.openapi_url,
        "swagger_ui_html": app.docs_url,
        "swagger_ui_redirect": app.swagger_ui_oauth2_redirect_url,
        "redoc_html": app.redoc_url,
    }
    for context in iter_application_routes(app):
        route = context.original_route
        path = context.path
        methods = context.methods or set()
        if isinstance(route, Mount):
            if path == "/static" and isinstance(route.app, StaticFiles):
                continue
            # SQLAdmin owns its framework routes; application views are validated on registration.
            controller = getattr(getattr(route.app, "state", None), "access_controller", None)
            if (
                isinstance(controller, AdminApp)
                and controller.admin is route.app
                and isinstance(controller.authentication_backend, AdminAuth)
                and isinstance(controller.authorization_backend, FeatureAuthorization)
            ):
                for view in controller.views:
                    controller._validate_view(type(view))
                continue
            raise ValueError(f"Mount without access policy: {path}")
        if not isinstance(route, APIRoute):
            if (
                isinstance(route, Route)
                and context.name in docs
                and docs[context.name] == path
                and methods <= {"GET", "HEAD"}
            ):
                continue
            raise ValueError(f"Route without access policy: {path}")
        policies = route_access_policies(context)
        if not policies:
            if methods and all((method, path) in public for method in methods):
                continue
            raise ValueError(f"Route without access policy: {path}")
        for policy in policies:
            if isinstance(policy, WebAccess) and policy.permission is None:
                if path != "/" or methods != {"GET"}:
                    raise ValueError(f"Unexpected authentication-only route: {path}")
            elif not isinstance(policy.permission, Permission):
                raise ValueError(f"Unknown feature permission: {path}")
