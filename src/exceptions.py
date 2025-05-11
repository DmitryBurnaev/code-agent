import logging

from fastapi import status


class BaseApplicationError(Exception):
    """Base application error"""

    log_level: int = logging.ERROR
    log_message: str = "Application error"
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class AppSettingsError(BaseApplicationError):
    """Settings error"""


class ProviderError(BaseApplicationError):
    """Provider error"""


class ProviderLookupError(ProviderError):
    """Provider lookup error"""

    log_level: int = logging.ERROR
    log_message: str = "Provider lookup error"
    status_code: int = status.HTTP_404_NOT_FOUND


class ProviderProxyError(ProviderError):
    """Provider proxy error"""

    log_level: int = logging.WARNING
    log_message: str = "Provider proxy error"
    status_code: int = status.HTTP_400_BAD_REQUEST


class ProviderRequestError(ProviderError):
    """Provider request error"""

    log_level: int = logging.ERROR
    log_message: str = "Provider request error"
    status_code: int = status.HTTP_400_BAD_REQUEST
