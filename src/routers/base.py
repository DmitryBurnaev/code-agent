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


class CORSBaseRoute(ErrorHandlingBaseRoute):
    """
    Base class for routes that need CORS headers
    """

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        """
        Get the route handler and add CORS headers to the response
        """
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request) -> Response:
            response = await original_route_handler(request)

            # Add CORS headers
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            response.headers["Access-Control-Max-Age"] = "86400"

            return response

        return custom_route_handler
