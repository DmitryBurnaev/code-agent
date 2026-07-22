"""Administration page for importing Toggl time-entry exports."""

from typing import Any

from sqladmin import expose
from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import Response

from src.db.repositories import UserRepository
from src.db.services import SASessionUOW
from src.modules.admin.views.base import BaseAPPView
from src.modules.time_tracker.toggl_import import (
    TogglImportService,
    TogglImportValidationError,
)

__all__ = ("TogglImportAdminView",)

MAX_IMPORT_FILE_SIZE = 10 * 1024 * 1024


class TogglImportAdminView(BaseAPPView):
    """Upload a Toggl CSV export for one local application user."""

    name = "Import Toggl CSV"
    icon = "fa-solid fa-file-import"

    @expose("/toggl-import", methods=["GET", "POST"])
    async def import_toggl_csv(self, request: Request) -> Response:
        """Render the import form or atomically import the uploaded Toggl CSV."""
        if request.method == "GET":
            return await self._render(request)

        form = await request.form()
        uploaded_file = form.get("csv_file")
        if not isinstance(uploaded_file, UploadFile) or not uploaded_file.filename:
            return await self._render(request, error="Choose a Toggl CSV file to import.")

        try:
            user_id = int(str(form.get("user_id") or ""))
        except ValueError:
            return await self._render(request, error="Choose the user who owns these entries.")

        contents = await uploaded_file.read()
        if len(contents) > MAX_IMPORT_FILE_SIZE:
            return await self._render(request, error="The CSV file must be 10 MB or smaller.")

        try:
            async with SASessionUOW() as uow:
                user = await UserRepository(uow.session).first(user_id)
                if user is None:
                    raise TogglImportValidationError("The selected user no longer exists.")
                result = await TogglImportService(uow.session).import_csv(user.id, contents)
                uow.mark_for_commit()
        except TogglImportValidationError as exc:
            return await self._render(request, error=str(exc), selected_user_id=user_id)

        summary = (
            f"Imported {result.imported_entries} entries; skipped {result.skipped_entries} duplicates. "
            f"Created {result.created_clients} clients and {result.created_projects} projects."
        )
        return await self._render(request, message=summary, selected_user_id=user_id)

    async def _render(
        self,
        request: Request,
        *,
        message: str | None = None,
        error: str | None = None,
        selected_user_id: int | None = None,
    ) -> Response:
        """Render the import form with the available local users."""
        async with SASessionUOW() as uow:
            users = await UserRepository(uow.session).all()
        context: dict[str, Any] = {
            "users": users,
            "message": message,
            "import_error": error,
            "selected_user_id": selected_user_id,
        }
        return await self.templates.TemplateResponse(request, "toggl_import.html", context=context)
