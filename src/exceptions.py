class BaseApplicationError(Exception):
    """Base application error"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class AppSettingsError(BaseApplicationError):
    """Settings error"""


class ProviderProxyError(BaseApplicationError):
    """Provider error"""
