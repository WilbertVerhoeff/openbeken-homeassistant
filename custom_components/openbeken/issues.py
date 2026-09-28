"""Repair notices for confirmed configuration or firmware incompatibility."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN
from .errors import DeviceIdentityError, UnsupportedProtocolError, connection_error_key


@callback
def async_report_connection_issue(
    hass: HomeAssistant, entry: ConfigEntry, error: Exception
) -> None:
    """Do not raise repair notices for temporary network outages."""
    if not isinstance(error, (UnsupportedProtocolError, DeviceIdentityError)):
        return
    ir.async_create_issue(
        hass,
        DOMAIN,
        f"connection_{entry.entry_id}",
        is_fixable=False,
        is_persistent=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key=connection_error_key(error),
        translation_placeholders={"name": entry.title},
        learn_more_url="https://github.com/WilbertVerhoeff/openbeken-homeassistant#connection-problems-and-repairs",
    )


@callback
def async_clear_connection_issue(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove the entry's repair notice after recovery or removal."""
    ir.async_delete_issue(hass, DOMAIN, f"connection_{entry.entry_id}")
