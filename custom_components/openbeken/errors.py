"""Distinguish user-actionable device errors from network failures."""

from collections.abc import Awaitable

from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN


class UnsupportedProtocolError(ValueError):
    """The endpoint explicitly advertises an unsupported API version."""


class InvalidResponseError(ValueError):
    """The endpoint does not provide a valid OpenBeken greeting."""


class DeviceIdentityError(ValueError):
    """The endpoint belongs to a different device."""


def connection_error_key(error: Exception) -> str:
    """Return a translated, stable error key without exposing raw exceptions."""
    if isinstance(error, UnsupportedProtocolError):
        return "unsupported_protocol"
    if isinstance(error, InvalidResponseError):
        return "invalid_response"
    if isinstance(error, DeviceIdentityError):
        return "wrong_device"
    return "cannot_connect"


async def async_execute_command(command: Awaitable[None]) -> None:
    """Translate command failures at the entity/service boundary."""
    try:
        await command
    except TimeoutError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="command_timeout"
        ) from err
    except OSError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="device_unavailable"
        ) from err
    except ValueError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="command_rejected"
        ) from err
