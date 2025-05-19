import logging
from typing import Any

from fastapi import APIRouter, Request, Response

from src.dependencies import SettingsDep
from src.models import ChatRequest, ModelListResponse
from src.routers import ErrorHandlingBaseRoute
from src.services.providers import ProviderService
from src.services.proxy import ProxyRequestData, ProxyService, ProxyEndpoint

logger = logging.getLogger(__name__)


# Create a separate router for CORS endpoints without auth
cors_router = APIRouter(
    prefix="/ai-proxy",
    tags=["ai-proxy"],
    responses={
        404: {"description": "Provider or model not found"},
        500: {"description": "Error communicating with AI provider"},
    },
    route_class=ErrorHandlingBaseRoute,
)


@cors_router.options("/chat/completions")
async def options_chat_completion() -> Response:
    """Handle OPTIONS request for chat completions endpoint"""
    return Response(status_code=204)


@cors_router.options("/models")
async def options_models() -> Response:
    """Handle OPTIONS request for models endpoint"""
    return Response(status_code=204)


router = APIRouter(
    prefix="/ai-proxy",
    tags=["ai-proxy"],
    responses={
        404: {"description": "Provider or model not found"},
        500: {"description": "Error communicating with AI provider"},
    },
    route_class=ErrorHandlingBaseRoute,
)


@router.get(
    "/models",
    description="List available models from all configured providers",
    response_model=ModelListResponse,
)
async def list_models(settings: SettingsDep) -> ModelListResponse:
    """Get a list of available models from all configured providers"""
    service = ProviderService(settings)
    models = await service.get_list_models()
    return ModelListResponse(data=models)


@router.post(
    "/chat/completions",
    description="Send a chat completion request to the AI provider specified by model name",
)
async def create_chat_completion(
    request: Request,
    chat_request: ChatRequest,
    settings: SettingsDep,
) -> Any:
    """Create a chat completion using the provider specified in the model name"""
    request_data = ProxyRequestData(
        method=request.method,
        headers=dict(request.headers),
        query_params=dict(request.query_params),
        body=chat_request,
    )

    service = ProxyService(settings)
    async with service:
        return await service.handle_request(request_data, ProxyEndpoint.CHAT_COMPLETION)


@router.delete(
    "/chat/completions/{completion_id}",
    description="Cancel an ongoing chat completion request",
)
async def cancel_chat_completion(
    request: Request,
    completion_id: str,
    settings: SettingsDep,
) -> Response:
    """
    Cancel an ongoing chat completion request.
    Requires the original model name to determine the provider.
    Not all providers support this functionality.
    """
    request_data = ProxyRequestData(
        method=request.method,
        headers=dict(request.headers),
        query_params=dict(request.query_params),
        completion_id=completion_id,
    )

    service = ProxyService(settings)
    async with service:
        return await service.handle_request(request_data, ProxyEndpoint.CANCEL_CHAT_COMPLETION)
