from typing import Callable, Coroutine, Any

from fastapi.routing import APIRoute
from starlette.requests import Request
from starlette.responses import Response

from src.utils import universal_exception_handler


class ErrorHandlingBaseRoute(APIRoute):
    """
    Base class for all API routes that handles all types of exceptions
    """

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        """
        Get the route handler for the route
        """
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request) -> Response:
            try:
                response = await original_route_handler(request)
            except Exception as exc:
                response = await universal_exception_handler(request, exc)

            return response

        return custom_route_handler


# class ValidationErrorLoggingRoute(APIRoute):
#     def get_route_handler(self) -> Callable:
#         original_route_handler = super().get_route_handler()
#
#         async def custom_route_handler(request: Request) -> Response:
#             try:
#                 return await original_route_handler(request)
#             except RequestValidationError as exc:
#                 body = await request.body()
#                 detail = {"errors": exc.errors(), "body": body.decode()}
#                 raise HTTPException(status_code=422, detail=detail)
#
#         return custom_route_handler
