"""Service failures carry translated errors rather than raw device replies."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.openbeken.const import DOMAIN


@pytest.mark.parametrize(
    ("platform", "service", "entity_id"),
    [
        ("light", "turn_on", "light.test_device_light"),
        ("light", "turn_off", "light.test_device_light"),
        ("switch", "turn_on", "switch.test_device_relay"),
        ("switch", "turn_off", "switch.test_device_relay"),
        ("button", "press", "button.test_device_restart"),
    ],
)
@pytest.mark.parametrize(
    ("error", "key"),
    [
        (TimeoutError("private details"), "command_timeout"),
        (ConnectionError("private details"), "device_unavailable"),
        (ValueError("private details"), "command_rejected"),
    ],
)
async def test_translated_service_failure(
    hass: HomeAssistant,
    setup_entry: MockConfigEntry,
    platform: str,
    service: str,
    entity_id: str,
    error: Exception,
    key: str,
) -> None:
    coordinator = hass.data[DOMAIN][setup_entry.entry_id]
    method = "async_restart" if platform == "button" else "async_set_state"
    with patch.object(coordinator, method, AsyncMock(side_effect=error)):
        with pytest.raises(HomeAssistantError) as caught:
            await hass.services.async_call(
                platform, service, {"entity_id": entity_id}, blocking=True
            )
    assert caught.value.translation_domain == DOMAIN
    assert caught.value.translation_key == key
    assert "private details" not in str(caught.value)
