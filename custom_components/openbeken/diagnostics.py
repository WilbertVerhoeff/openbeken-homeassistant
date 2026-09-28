"""Download a bounded snapshot without device addresses, names or readings."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PROTOCOL_VERSION
from .coordinator import OpenBekenCoordinator

_REDACT = {"host", "name", "device_id", "unique_id"}
_CONFIG_FIELDS = {"host", "port", "name", "device_id"}
_ENTITY_FIELDS = {
    "platform",
    "features",
    "unit",
    "device_class",
    "state_class",
    "min_mireds",
    "max_mireds",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Use cached data only; downloading diagnostics never contacts the device."""
    coordinator: OpenBekenCoordinator | None = hass.data.get(DOMAIN, {}).get(
        entry.entry_id
    )
    runtime = None
    if coordinator is not None:
        runtime = {
            "connected": coordinator.connected,
            "last_update_success": coordinator.last_update_success,
            "firmware": coordinator.firmware,
            "protocol": PROTOCOL_VERSION,
            "entity_count": len(coordinator.entities),
            "state_count": len(coordinator.states),
            "entities": [
                {
                    **{
                        key: value
                        for key, value in description.items()
                        if key in _ENTITY_FIELDS
                    },
                    "has_state": entity_id in coordinator.states,
                }
                for entity_id, description in coordinator.entities.items()
            ],
        }
    return async_redact_data(
        deepcopy(
            {
                "config_entry": {
                    "version": entry.version,
                    "unique_id": entry.unique_id,
                    "data": {
                        key: value
                        for key, value in entry.data.items()
                        if key in _CONFIG_FIELDS
                    },
                },
                "runtime": runtime,
            }
        ),
        _REDACT,
    )
