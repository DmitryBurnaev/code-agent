import logging
from typing import Annotated

from fastapi import APIRouter, Request, Response, Depends, HTTPException
from fastapi.responses import StreamingResponse

from src.dependencies import SettingsDep
from src.models import ChatRequest
from src.services.proxy import ProxyRequestData, ProxyService, ProxyEndpoint

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/ai-proxy",
    tags=["ai-proxy"],
    responses={
        404: {"description": "Provider or model not found"},
        500: {"description": "Error communicating with AI provider"},
    },
)


@router.post(
    "/chat/completions",
    response_class=StreamingResponse,
    description="Send a chat completion request to the AI provider specified by model name",
)
async def create_chat_completion(
    request: Request,
    chat_request: ChatRequest,
    settings: SettingsDep,
) -> Response | StreamingResponse:
    """
    Create a chat completion using the provider specified in the model name.

    The model name in the request should be in format "provider__model_name",
    where provider determines which AI service to use. Examples:
    - openai__gpt-4
    - anthropic__claude-3
    - deepseek__chat-v1

    The request body follows a standardized format but allows provider-specific parameters
    to be passed through.
    """
    request_data = ProxyRequestData(
        method=request.method,
        headers=dict(request.headers),
        query_params=dict(request.query_params),
        body=chat_request,
    )

    service = ProxyService(settings)
    return await service.handle_request(request_data, ProxyEndpoint.CHAT_COMPLETION)


@router.get(
    "/models",
    description="List available models from all configured providers",
)
async def list_models(
    request: Request,
    settings: SettingsDep,
) -> Response:
    """
    Get a list of available models from all configured providers.
    The response will be aggregated and models will be prefixed with provider names.
    """
    request_data = ProxyRequestData(
        method=request.method,
        headers=dict(request.headers),
        query_params=dict(request.query_params),
    )

    service = ProxyService(settings)
    return await service.handle_request(request_data, ProxyEndpoint.LIST_MODELS)


@router.delete(
    "/chat/completions/{completion_id}",
    description="Cancel an ongoing chat completion request",
)
async def cancel_chat_completion(
    request: Request,
    completion_id: str,
    chat_request: ChatRequest,
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
        body=chat_request,
        completion_id=completion_id,
    )

    service = ProxyService(settings)
    return await service.handle_request(request_data, ProxyEndpoint.CANCEL_CHAT_COMPLETION)
