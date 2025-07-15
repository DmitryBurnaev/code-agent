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


class VendorError(BaseApplicationError):
    """Vendor error"""


class VendorLookupError(VendorError):
    """Vendor lookup error"""

    log_level: int = logging.ERROR
    log_message: str = "Vendor lookup error"
    status_code: int = status.HTTP_404_NOT_FOUND


class VendorProxyError(VendorError):
    """Vendor proxy error"""

    log_level: int = logging.WARNING
    log_message: str = "Vendor proxy error"
    status_code: int = status.HTTP_400_BAD_REQUEST


class VendorRequestError(VendorError):
    """Vendor request error"""

    log_level: int = logging.ERROR
    log_message: str = "Vendor request error"
    status_code: int = status.HTTP_400_BAD_REQUEST


class VendorEncryptionError(VendorError):
    """Vendor encryption error"""

    log_level: int = logging.ERROR
    log_message: str = "Vendor encryption error"
    status_code: int = status.HTTP_503_SERVICE_UNAVAILABLE
