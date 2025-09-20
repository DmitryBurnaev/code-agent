"""Comprehensive tests for src/services/vendors.py module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from src.services.vendors import (
    VendorModelResponse,
    VendorDataResponse,
    VendorClient,
    VendorService,
)
from src.models import AIModel
from src.constants import VendorSlug


@pytest.fixture
def mock_logger():
    """Mock logger fixture."""
    with patch("src.services.vendors.logger") as mock:
        # Reset mock state before each test
        mock.reset_mock()
        yield mock


@pytest.fixture
def mock_vendor_http_client():
    """Mock VendorHTTPClient fixture."""
    with patch("src.services.vendors.VendorHTTPClient") as mock:
        yield mock


@pytest.fixture
def mock_session_uow():
    """Mock SASessionUOW fixture."""
    with patch("src.services.vendors.SASessionUOW") as mock:
        yield mock


@pytest.fixture
def mock_llm_vendor_from_vendor():
    """Mock LLMVendor.from_vendor fixture."""
    with patch("src.services.vendors.LLMVendor.from_vendor") as mock:
        yield mock


@pytest.fixture
def mock_settings():
    """Mock settings fixture."""
    settings = MagicMock()
    settings.flags.offline_mode = False
    return settings


@pytest.fixture
def mock_http_client():
    """Mock HTTP client fixture."""
    return MagicMock()


@pytest.fixture
def mock_vendor():
    """Mock vendor fixture."""
    vendor = MagicMock()
    vendor.slug = VendorSlug.OPENAI
    vendor.base_url = "https://api.openai.com/v1/"
    vendor.auth_headers = {"Authorization": "Bearer test"}
    return vendor


@pytest.fixture
def mock_http_response():
    """Mock HTTP response fixture."""
    response = AsyncMock()
    response.status_code = httpx.codes.OK
    response.json.return_value = {"data": [{"id": "gpt-4"}, {"id": "gpt-3.5-turbo"}]}
    return response


@pytest.fixture
def mock_repository():
    """Mock VendorRepository fixture."""
    mock_repo = AsyncMock()
    mock_repo.filter.return_value = []
    return mock_repo


@pytest.fixture
def mock_session_with_repo(mock_repository):
    """Mock session with repository fixture."""
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.session = mock_repository
    return mock_session


class TestVendorModelResponse:
    """Tests for VendorModelResponse class."""

    def test_model_creation(self) -> None:
        """Test VendorModelResponse model creation."""
        data = {"id": "test-model", "object": "model", "created": 1725649008, "owned_by": "system"}
        response = VendorModelResponse.model_validate(data)

        assert response.id == "test-model"

    def test_model_validation(self) -> None:
        """Test VendorModelResponse model validation."""
        # Valid data
        data = {"id": "test-model"}
        response = VendorModelResponse.model_validate(data)
        assert response.id == "test-model"

        # Missing required field
        with pytest.raises(ValueError):
            VendorModelResponse.model_validate({})


class TestVendorDataResponse:
    """Tests for VendorDataResponse class."""

    def test_model_creation(self) -> None:
        """Test VendorDataResponse model creation."""
        data = {"data": [{"id": "model1"}, {"id": "model2"}]}
        response = VendorDataResponse.model_validate(data)

        assert len(response.data) == 2
        assert response.data[0].id == "model1"
        assert response.data[1].id == "model2"

    def test_empty_data(self) -> None:
        """Test VendorDataResponse with empty data."""
        data = {"data": []}
        response = VendorDataResponse.model_validate(data)

        assert len(response.data) == 0


class TestVendorClient:
    """Tests for VendorClient class."""

    def test_init(self, mock_vendor, mock_http_client) -> None:
        """Test VendorClient initialization."""
        client = VendorClient(mock_vendor, mock_http_client)

        assert client._vendor == mock_vendor
        assert client._base_url == mock_vendor.base_url
        assert client._http_client == mock_http_client

    @pytest.mark.asyncio
    async def test_get_list_models_success(self, mock_vendor, mock_logger) -> None:
        """Test successful model listing."""
        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response = MagicMock()
        mock_response.status_code = httpx.codes.OK
        mock_response.json.return_value = {"data": [{"id": "gpt-4"}, {"id": "gpt-3.5-turbo"}]}
        mock_http_client.get.return_value = mock_response

        client = VendorClient(mock_vendor, mock_http_client)

        models = await client.get_list_models()

        # Verify HTTP request
        mock_http_client.get.assert_awaited_once_with(
            "https://api.openai.com/v1/models", headers=mock_vendor.auth_headers
        )

        # Verify models
        assert len(models) == 2
        assert models[0].vendor_id == "gpt-4"
        assert models[1].vendor_id == "gpt-3.5-turbo"
        assert models[0].vendor == "openai"
        assert models[1].vendor == "openai"

    @pytest.mark.asyncio
    async def test_get_list_models_http_error(self, mock_vendor, mock_logger) -> None:
        """Test model listing with HTTP error."""
        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_http_client.get.return_value = mock_response

        client = VendorClient(mock_vendor, mock_http_client)

        models = await client.get_list_models()

        # Verify warning was logged
        mock_logger.warning.assert_called_once()
        assert "Failed to fetch models from vendor" in mock_logger.warning.call_args[0][0]

        # Verify empty result
        assert models == []

    @pytest.mark.asyncio
    async def test_get_list_models_no_data(self, mock_vendor, mock_logger) -> None:
        """Test model listing with no data in response."""
        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response = MagicMock()
        mock_response.status_code = httpx.codes.OK
        mock_response.json.return_value = None
        mock_http_client.get.return_value = mock_response

        client = VendorClient(mock_vendor, mock_http_client)

        models = await client.get_list_models()

        # Verify warning was logged
        mock_logger.warning.assert_called_once()
        assert "No models data in vendor response" in mock_logger.warning.call_args[0][0]

        # Verify empty result
        assert models == []

    @pytest.mark.asyncio
    async def test_get_list_models_exception(self, mock_vendor, mock_logger) -> None:
        """Test model listing with exception."""
        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_http_client.get.side_effect = Exception("Network error")

        client = VendorClient(mock_vendor, mock_http_client)

        models = await client.get_list_models()

        # Verify exception was logged
        mock_logger.exception.assert_called_once()
        assert "Failed to list" in mock_logger.exception.call_args[0][0]

        # Verify empty result
        assert models == []

    def test_is_chat_model_anthropic(self) -> None:
        """Test _is_chat_model for Anthropic-style models."""
        model = {"id": "claude-3", "type": "chat"}
        assert VendorClient._is_chat_model(model) is True

    def test_is_chat_model_openai(self) -> None:
        """Test _is_chat_model for OpenAI-style models."""
        # GPT models
        model = {"id": "gpt-4"}
        assert VendorClient._is_chat_model(model) is True

        # Text models
        model = {"id": "text-davinci-003"}
        assert VendorClient._is_chat_model(model) is True

    def test_is_chat_model_other(self) -> None:
        """Test _is_chat_model for other models."""
        model = {"id": "other-model"}
        assert VendorClient._is_chat_model(model) is False


class TestVendorService:
    """Tests for VendorService class."""

    def test_init(self, mock_settings, mock_vendor_http_client) -> None:
        """Test VendorService initialization."""
        service = VendorService(mock_settings)

        assert service._settings == mock_settings
        assert service._cache is not None
        assert service._vendor_clients == {}
        assert service._http_client is not None

    def test_init_with_http_client(self, mock_settings, mock_http_client) -> None:
        """Test VendorService initialization with custom HTTP client."""
        service = VendorService(mock_settings, http_client=mock_http_client)

        assert service._http_client == mock_http_client

    def test_get_client_new(self, mock_settings, mock_http_client, mock_vendor_http_client) -> None:
        """Test getting a new client."""
        service = VendorService(mock_settings, http_client=mock_http_client)

        vendor = MagicMock()
        vendor.slug = VendorSlug.OPENAI

        client = service.get_client(vendor)

        assert isinstance(client, VendorClient)
        assert service._vendor_clients[vendor.slug] == client

    def test_get_client_existing(
        self, mock_settings, mock_http_client, mock_vendor_http_client
    ) -> None:
        """Test getting an existing client."""
        service = VendorService(mock_settings, http_client=mock_http_client)

        vendor = MagicMock()
        vendor.slug = VendorSlug.OPENAI

        # Get client twice
        client1 = service.get_client(vendor)
        client2 = service.get_client(vendor)

        assert client1 is client2

    @pytest.mark.asyncio
    async def test_get_list_models_no_active_vendors(
        self,
        mock_settings,
        mock_http_client,
        mock_vendor_http_client,
        mock_session_uow,
        mock_logger,
    ) -> None:
        """Test getting models when no active vendors."""
        service = VendorService(mock_settings, http_client=mock_http_client)

        mock_repo = AsyncMock()
        mock_repo.filter.return_value = []
        mock_session_uow.return_value.__aenter__.return_value.session = mock_repo

        with patch("src.services.vendors.VendorRepository") as mock_repo_class:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.filter.return_value = []
            mock_repo_class.return_value = mock_repo_instance

            models = await service.get_list_models()

            # Verify warning was logged
            mock_logger.warning.assert_called_once_with("No active vendors detected.")

            # Verify empty result
            assert models == []

    @pytest.mark.asyncio
    async def test_get_list_models_offline_mode(
        self, mock_http_client, mock_vendor_http_client, mock_session_uow
    ) -> None:
        """Test getting models in offline mode."""
        mock_settings = MagicMock()
        mock_settings.flags.offline_mode = True

        service = VendorService(mock_settings, http_client=mock_http_client)

        mock_repo = AsyncMock()
        mock_repo.filter.return_value = [
            MagicMock(slug=VendorSlug.OPENAI.name),
            MagicMock(slug=VendorSlug.ANTHROPIC.name),
        ]
        mock_session_uow.return_value.__aenter__.return_value.session = mock_repo

        with patch("src.services.vendors.VendorRepository") as mock_repo_class:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.filter.return_value = [
                MagicMock(slug=VendorSlug.OPENAI.name),
                MagicMock(slug=VendorSlug.ANTHROPIC.name),
            ]
            mock_repo_class.return_value = mock_repo_instance

            models = await service.get_list_models()

            # Verify mocked models
            assert len(models) == 3  # 2 OpenAI + 1 Anthropic
            model_vendors = [model.vendor for model in models]
            assert "OPENAI" in model_vendors
            assert "ANTHROPIC" in model_vendors

    @pytest.mark.asyncio
    async def test_get_list_models_with_cache(
        self, mock_settings, mock_http_client, mock_vendor_http_client, mock_session_uow
    ) -> None:
        """Test getting models with cache hit."""
        service = VendorService(mock_settings, http_client=mock_http_client)

        # Mock cached data
        cached_models = [
            AIModel.from_vendor("OPENAI", "gpt-4"),
            AIModel.from_vendor("OPENAI", "gpt-3.5-turbo"),
        ]
        service._cache.set("OPENAI", [model.model_dump() for model in cached_models])

        with patch("src.services.vendors.VendorRepository") as mock_repo_class:
            mock_vendor = MagicMock()
            mock_vendor.slug = VendorSlug.OPENAI.name
            mock_vendor.decrypted_api_key = "test-key"
            mock_vendor.api_url = "https://api.openai.com/v1"
            mock_vendor.timeout = 30

            mock_repo_instance = AsyncMock()
            mock_repo_instance.filter.return_value = [mock_vendor]
            mock_repo_class.return_value = mock_repo_instance

            models = await service.get_list_models()

            # Verify cached models were returned
            assert len(models) == 2
            assert models[0].vendor_id == "gpt-4"
            assert models[1].vendor_id == "gpt-3.5-turbo"

    @pytest.mark.asyncio
    async def test_get_list_models_force_refresh(
        self,
        mock_settings,
        mock_http_client,
        mock_vendor_http_client,
        mock_session_uow,
        mock_llm_vendor_from_vendor,
    ) -> None:
        """Test getting models with force refresh."""
        service = VendorService(mock_settings, http_client=mock_http_client)

        # Mock cached data
        cached_models = [AIModel.from_vendor("openai", "gpt-4")]
        service._cache.set("openai", [model.model_dump() for model in cached_models])

        with patch("src.services.vendors.VendorRepository") as mock_repo_class:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.filter.return_value = [MagicMock(slug=VendorSlug.OPENAI.name)]
            mock_repo_class.return_value = mock_repo_instance

            mock_vendor = MagicMock()
            mock_vendor.slug = VendorSlug.OPENAI
            mock_llm_vendor_from_vendor.return_value = mock_vendor

            with patch.object(service, "get_client") as mock_get_client:
                mock_client = AsyncMock()
                mock_client.get_list_models.return_value = [AIModel.from_vendor("openai", "gpt-5")]
                mock_get_client.return_value = mock_client

                models = await service.get_list_models(force_refresh=True)

                # Verify fresh data was fetched
                mock_client.get_list_models.assert_awaited_once()
                assert len(models) == 1
                assert models[0].vendor_id == "gpt-5"

    @pytest.mark.asyncio
    async def test_get_list_models_vendor_exception(
        self,
        mock_settings,
        mock_http_client,
        mock_vendor_http_client,
        mock_session_uow,
        mock_llm_vendor_from_vendor,
        mock_logger,
    ) -> None:
        """Test getting models when vendor creation fails."""
        service = VendorService(mock_settings, http_client=mock_http_client)

        with patch("src.services.vendors.VendorRepository") as mock_repo_class:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.filter.return_value = [MagicMock(slug=VendorSlug.OPENAI.name)]
            mock_repo_class.return_value = mock_repo_instance

            mock_llm_vendor_from_vendor.side_effect = Exception("Vendor creation failed")

            models = await service.get_list_models()

            # Verify exception was logged
            mock_logger.exception.assert_called_once()
            assert "Failed to fetch vendor models" in mock_logger.exception.call_args[0][0]

            # Verify empty result
            assert models == []

    @pytest.mark.skip(reason="not implemented")
    @pytest.mark.asyncio
    async def test_get_list_models_client_exception(
        self,
        mock_settings,
        mock_http_client,
        mock_vendor_http_client,
        mock_session_uow,
        mock_llm_vendor_from_vendor,
    ) -> None:
        """Test getting models when client fails."""
        service = VendorService(mock_settings, http_client=mock_http_client)

        # Clear cache to ensure fresh data
        service._cache.clear()

        mock_vendor_db = MagicMock()
        mock_vendor_db.slug = VendorSlug.OPENAI.name
        mock_vendor_db.decrypted_api_key = "test-key"
        mock_vendor_db.api_url = "https://api.openai.com/v1"
        mock_vendor_db.timeout = 30

        mock_repo_instance = AsyncMock()
        mock_repo_instance.filter.return_value = [mock_vendor_db]
        mock_session_uow.return_value.__aenter__.return_value.session = mock_repo_instance

        with patch("src.services.vendors.VendorRepository") as mock_repo_class:
            mock_repo_class.return_value = mock_repo_instance

            mock_vendor = MagicMock()
            mock_vendor.slug = VendorSlug.OPENAI
            mock_llm_vendor_from_vendor.return_value = mock_vendor

            with patch.object(service, "get_client") as mock_get_client:
                mock_client = AsyncMock()
                mock_client.get_list_models.side_effect = Exception("Client error")
                mock_get_client.return_value = mock_client

                models = await service.get_list_models()

                # Verify empty result when client fails
                assert models == []

    def test_cache_set_data(self, mock_settings, mock_http_client, mock_vendor_http_client) -> None:
        """Test cache set data method."""
        service = VendorService(mock_settings, http_client=mock_http_client)

        models = [
            AIModel.from_vendor("openai", "gpt-4"),
            AIModel.from_vendor("openai", "gpt-3.5-turbo"),
        ]

        service._cache_set_data("openai", models)

        # Verify data was cached
        cached = service._cache.get("openai")
        assert cached is not None
        assert len(cached) == 2
        assert cached[0]["vendor_id"] == "gpt-4"
        assert cached[1]["vendor_id"] == "gpt-3.5-turbo"

    def test_cache_get_data_hit(
        self, mock_settings, mock_http_client, mock_vendor_http_client
    ) -> None:
        """Test cache get data method with cache hit."""
        service = VendorService(mock_settings, http_client=mock_http_client)

        # Set up cache
        models_data = [
            {"id": "openai::gpt-4", "vendor": "openai", "vendor_id": "gpt-4"},
            {"id": "openai::gpt-3.5-turbo", "vendor": "openai", "vendor_id": "gpt-3.5-turbo"},
        ]
        service._cache.set("openai", models_data)

        models = service._cache_get_data("openai")

        assert models is not None
        assert len(models) == 2
        assert models[0].vendor_id == "gpt-4"
        assert models[1].vendor_id == "gpt-3.5-turbo"

    def test_cache_get_data_miss(
        self, mock_settings, mock_http_client, mock_vendor_http_client, mock_logger
    ) -> None:
        """Test cache get data method with cache miss."""
        service = VendorService(mock_settings, http_client=mock_http_client)

        models = service._cache_get_data("nonexistent")

        # Verify debug was logged
        mock_logger.debug.assert_called_once()
        assert "No cached models for" in mock_logger.debug.call_args[0][0]

        # Verify None result
        assert models is None

    def test_cache_get_data_invalid_data(
        self, mock_settings, mock_http_client, mock_vendor_http_client, mock_logger
    ) -> None:
        """Test cache get data method with invalid cached data."""
        service = VendorService(mock_settings, http_client=mock_http_client)

        # Set invalid cache data
        service._cache.set("openai", "invalid_data")

        models = service._cache_get_data("openai")

        # Verify debug was logged
        mock_logger.debug.assert_called_once()
        assert "No cached models for" in mock_logger.debug.call_args[0][0]

        # Verify None result
        assert models is None

    def test_mocked_models(self) -> None:
        """Test mocked models generation."""
        vendors = [VendorSlug.OPENAI.name, VendorSlug.DEEPSEEK.name]
        models = VendorService._mocked_models(vendors)

        assert len(models) == 4  # 2 OpenAI + 2 DeepSeek
        model_vendors = [model.vendor for model in models]
        assert "OPENAI" in model_vendors
        assert "DEEPSEEK" in model_vendors

        # Check specific models
        model_ids = [model.vendor_id for model in models]
        assert "openai-chat" in model_ids
        assert "o12-macro" in model_ids
        assert "deepseek-chat" in model_ids
        assert "deepseek-think" in model_ids

    def test_mocked_models_unknown_vendor(self) -> None:
        """Test mocked models with unknown vendor."""
        vendors = ["unknown-vendor"]
        models = VendorService._mocked_models(vendors)

        assert len(models) == 0
