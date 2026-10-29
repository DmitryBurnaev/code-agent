"""Guardrails for future features, including deliberately unsafe route additions."""

import re
from unittest.mock import AsyncMock

import pytest
import sqlalchemy as sa
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from starlette.applications import Starlette
from starlette.responses import Response
from starlette.testclient import TestClient

from src.db.models import BaseModel, User
from src.application import CodeAgentAPP
from src.main import make_app
from src.modules.admin.app import ADMIN_VIEWS
from src.modules.admin.views.users import UserAdminForm
from src.modules.auth.dependencies import APIAccess, WebAccess
from src.modules.auth.permissions import PERMISSION_DEFINITIONS, Permission
from src.modules.auth.routing import (
    iter_application_routes,
    route_access_policies,
    validate_access_policies,
)
from src.modules.auth.tokens import AuthenticatedAPIToken, authenticate_api_token
from src.modules.web.views import NAVIGATION
from src.settings import AppSettings


@pytest.fixture
def test_app(app_settings_test: AppSettings) -> CodeAgentAPP:
    return make_app(app_settings_test)


async def sample_feature() -> dict[str, bool]:
    return {"ok": True}


def test_catalog_model_and_admin_form_are_complete() -> None:
    permissions = {permission.value for permission in Permission}
    assert set(PERMISSION_DEFINITIONS) == set(Permission)
    columns = sa.inspect(User).columns
    assert {column.key for column in columns if column.key.startswith("can_")} == permissions
    form = UserAdminForm()
    assert {name for name in form._fields if name.startswith("can_")} == permissions
    for permission, definition in PERMISSION_DEFINITIONS.items():
        column = columns[permission.value]
        assert isinstance(column.type, sa.Boolean)
        assert column.nullable is False
        assert isinstance(column.default, sa.ColumnDefault) and column.default.arg is False
        assert (
            isinstance(column.server_default, sa.DefaultClause)
            and str(column.server_default.arg) == "false"
        )
        field = form[permission.value]
        assert field.data is False
        assert field.label.text == definition.label
        assert field.description == definition.description


def test_current_model_defaults_are_disabled() -> None:
    engine = sa.create_engine("sqlite://")
    try:
        BaseModel.metadata.create_all(engine)
        with Session(engine) as session:
            user = User(username="new-user", password="hash")
            session.add(user)
            session.flush()
            session.refresh(user)
            assert user.is_admin is False
            assert all(getattr(user, permission.value) is False for permission in Permission)
    finally:
        engine.dispose()


@pytest.mark.parametrize("docs", [True, False])
def test_application_routes_have_access_policies(
    app_settings_test: AppSettings, docs: bool
) -> None:
    app_settings_test.api_docs_enabled = docs
    validate_access_policies(make_app(app_settings_test))


@pytest.mark.parametrize("nested", [False, True])
def test_unprotected_routes_fail_coverage(test_app: CodeAgentAPP, nested: bool) -> None:
    if nested:
        unsafe = APIRouter()
        unsafe.add_api_route("/feature", sample_feature)
        parent = APIRouter(prefix="/nested")
        parent.include_router(unsafe)
        test_app.include_router(parent, prefix="/api")
    else:
        test_app.add_api_route("/feature", sample_feature)
    with pytest.raises(ValueError, match="Route without access policy"):
        validate_access_policies(test_app)


@pytest.mark.parametrize("access", [None, WebAccess()])
def test_new_features_cannot_use_public_or_authentication_only_access(
    test_app: CodeAgentAPP,
    access: WebAccess | None,
) -> None:
    router = APIRouter(dependencies=[Depends(access)] if access is not None else [])
    router.add_api_route("/new-feature", sample_feature)
    test_app.include_router(router)
    with pytest.raises(ValueError, match="Unexpected|Route without access policy"):
        validate_access_policies(test_app)


def test_nested_feature_router_enforces_access_with_effective_prefix(
    test_app: CodeAgentAPP,
) -> None:
    feature = APIRouter(dependencies=[Depends(APIAccess(Permission.LLM))])
    feature.add_api_route("/new-feature", sample_feature)
    parent = APIRouter(prefix="/nested")
    parent.include_router(feature)
    test_app.include_router(parent, prefix="/api")
    validate_access_policies(test_app)
    route = next(
        route
        for route in iter_application_routes(test_app)
        if route.path == "/api/nested/new-feature"
    )
    assert any(
        isinstance(policy, APIAccess) and policy.permission == Permission.LLM
        for policy in route_access_policies(route)
    )
    client = TestClient(test_app)
    try:
        assert client.get("/api/nested/new-feature").status_code == 401
    finally:
        client.close()


def test_unknown_mount_fails_coverage(test_app: CodeAgentAPP) -> None:
    test_app.mount("/new-feature", Starlette())
    with pytest.raises(ValueError, match="Mount without access policy"):
        validate_access_policies(test_app)


def test_plain_starlette_routes_cannot_bypass_policy(test_app: CodeAgentAPP) -> None:
    async def endpoint(request: object) -> Response:
        return Response()

    test_app.add_route("/feature", endpoint)
    with pytest.raises(ValueError, match="Route without access policy"):
        validate_access_policies(test_app)


def test_all_registered_feature_routes_deny_users_without_permissions(
    test_app: CodeAgentAPP,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = User(id=1, username="member", is_active=True, is_admin=False)
    monkeypatch.setattr("src.modules.web.auth.get_current_web_user", AsyncMock(return_value=user))
    test_app.dependency_overrides[authenticate_api_token] = lambda: AuthenticatedAPIToken(
        "test", user
    )
    client = TestClient(test_app)
    try:
        for route in iter_application_routes(test_app):
            if not any(
                isinstance(policy, APIAccess)
                or isinstance(policy, WebAccess)
                and policy.permission is not None
                for policy in route_access_policies(route)
            ):
                continue
            assert route.path is not None
            path = re.sub(r"\{[^}]+\}", "1", route.path)
            for method in (route.methods or set()) - {"OPTIONS", "HEAD"}:
                response = client.request(
                    method, path, json={"model": "example", "messages": []}, follow_redirects=False
                )
                assert response.status_code == 403, f"{method} {path}: {response.status_code}"
    finally:
        client.close()


def test_feature_navigation_declares_matching_permission(test_app: CodeAgentAPP) -> None:
    routes = {route.path: route for route in iter_application_routes(test_app)}
    for item in NAVIGATION:
        if item.path == "/":
            continue
        assert isinstance(item.permission, Permission)
        assert any(
            isinstance(policy, WebAccess) and policy.permission == item.permission
            for policy in route_access_policies(routes[item.path])
        )


def test_existing_admin_views_declare_their_management_policy() -> None:
    assert all(
        view.__dict__.get("required_permission") == Permission.ADMIN_PANEL for view in ADMIN_VIEWS
    )


async def test_startup_rejects_routes_added_after_app_construction(
    test_app: CodeAgentAPP,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("src.main.initialize_database", AsyncMock())
    monkeypatch.setattr("src.main.make_admin", lambda app: None)
    test_app.add_api_route("/forgotten", sample_feature)
    with pytest.raises(ValueError, match="Route without access policy"):
        with TestClient(test_app):
            pass
