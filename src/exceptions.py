class BaseApplicationError(Exception):
    """Base application error"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class AppSettingsError(BaseApplicationError):
    """Settings error"""


class ProviderError(BaseApplicationError):
    """Provider error"""


class ProviderLookupError(ProviderError):
    """Provider lookup error"""


class ProviderProxyError(ProviderError):
    """Provider error"""


class ProviderRequestError(ProviderError):
    """Provider error"""
