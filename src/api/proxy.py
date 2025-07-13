import logging

from fastapi import APIRouter, Request, Response

from src.settings import SettingsDep
from src.models import (
    ChatRequest,
    ModelListResponse,
    ChatCompletionResponse,
    ChatCompletionStreamResponse,
    CancelCompletionResponse,
)
from src.api import CORSBaseRoute
from src.services.vendors import VendorService
from src.services.proxy import ProxyRequestData, ProxyService, ProxyEndpoint

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai-proxy", tags=["ai-proxy"], route_class=CORSBaseRoute)


@router.options(
    "/models",
    description="Handle CORS preflight request for models endpoint",
    responses={204: {"description": "CORS preflight request successful"}},
)
async def options_models() -> Response:
    """Handle OPTIONS request for models endpoint"""
    return Response(status_code=204)


@router.get(
    "/models",
    description="List available models from all configured vendors",
    response_model=ModelListResponse,
)
async def list_models(settings: SettingsDep) -> ModelListResponse:
    """Get a list of available models from all configured vendors"""
    service = VendorService(settings)
    models = await service.get_list_models()
    return ModelListResponse(data=models)


@router.options(
    "/chat/completions",
    description="Handle CORS preflight request for chat completions endpoint",
    responses={204: {"description": "CORS preflight request successful"}},
)
async def options_chat_completion() -> Response:
    """Handle OPTIONS request for chat completions endpoint"""
    return Response(status_code=204)


@router.post(
    "/chat/completions",
    description="Send a chat completion request to the AI vendor specified by model name",
    response_model=ChatCompletionResponse | ChatCompletionStreamResponse,
    responses={
        200: {
            "description": "Chat completion response",
            "model": ChatCompletionResponse,
        },
        201: {
            "description": "Streaming chat completion response",
            "model": ChatCompletionStreamResponse,
        },
    },
)
async def create_chat_completion(
    request: Request,
    chat_request: ChatRequest,
    settings: SettingsDep,
) -> Response:
    """Create a chat completion using the vendor specified in the model name"""
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
    response_model=CancelCompletionResponse,
    responses={
        200: {
            "description": "Chat completion cancelled successfully",
            "model": CancelCompletionResponse,
        },
    },
)
async def cancel_chat_completion(
    request: Request,
    completion_id: str,
    settings: SettingsDep,
) -> Response:
    """
    Cancel an ongoing chat completion request.
    Requires the original model name to determine the vendor.
    Not all vendors support this functionality.
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
