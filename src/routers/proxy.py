import logging
from typing import Any

from fastapi import APIRouter, Request, Response

from src.dependencies import SettingsDep
from src.models import ChatRequest, AIModel
from src.services.providers import ProviderService
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


@router.get(
    "/models",
    description="List available models from all configured providers",
    response_model=list[AIModel],
)
async def list_models(settings: SettingsDep) -> list[AIModel]:
    """
    Get a list of available models from all configured providers.
    The response will be aggregated and models will be prefixed with provider names.
    """
    service = ProviderService(settings)
    return await service.get_list_models()


@router.post(
    "/chat/completions",
    description="Send a chat completion request to the AI provider specified by model name",
    # response_class=Response,
)
async def create_chat_completion(
    request: Request,
    chat_request: ChatRequest,
    settings: SettingsDep,
) -> Any:
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
    async with ProxyService(settings) as service:
        return await service.handle_request(request_data, ProxyEndpoint.CHAT_COMPLETION)
        # Ensure we return StreamingResponse
        # if isinstance(response, StreamingResponse):
        #     return response
        # # Convert regular response to streaming if needed
        # return StreamingResponse(
        #     content=iter([response.body]),
        #     status_code=response.status_code,
        #     headers=dict(response.headers),
        # )


@router.delete(
    "/chat/completions/{completion_id}",
    description="Cancel an ongoing chat completion request",
    response_class=Response,
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
    async with ProxyService(settings) as service:
        return await service.handle_request(request_data, ProxyEndpoint.CANCEL_CHAT_COMPLETION)
