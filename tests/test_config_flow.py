"""Exercise config flows through Home Assistant, including error recovery."""

from collections.abc import Iterator
from copy import deepcopy
from ipaddress import ip_address
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.openbeken.const import DEFAULT_PORT, DOMAIN, SERVICE_TYPE

from .conftest import DEVICE_ID, HELLO, NORMALIZED_ID, DeviceEmulator


def discovery(**overrides: Any) -> ZeroconfServiceInfo:
    """Build the same service-info object supplied by Home Assistant."""
    values = {
        "ip_address": ip_address("127.0.0.1"),
        "ip_addresses": [ip_address("127.0.0.1")],
        "port": 6054,
        "hostname": "openbeken.local.",
        "type": SERVICE_TYPE,
        "name": f"Test device.{SERVICE_TYPE}",
        "properties": {"api": "1", "id": DEVICE_ID, "name": "Test device"},
    }
    values.update(overrides)
    return ZeroconfServiceInfo(**values)


@pytest.fixture
def probe() -> Iterator[AsyncMock]:
    """Control device responses without bypassing config-flow logic."""
    with patch(
        "custom_components.openbeken.config_flow.async_probe_device",
        return_value=deepcopy(HELLO),
    ) as mock:
        yield mock


@pytest.fixture(autouse=True)
def prevent_setup() -> Iterator[AsyncMock]:
    """Test creation separately from setup and platforms."""
    with patch(
        "custom_components.openbeken.async_setup_entry", return_value=True
    ) as mock:
        yield mock


async def test_user(hass: HomeAssistant, probe: AsyncMock) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "device.local", "port": 6054}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Test device"
    assert result["data"] == {
        "host": "device.local",
        "port": 6054,
        "name": "Test device",
        "device_id": DEVICE_ID,
    }
    assert result["result"].unique_id == NORMALIZED_ID
    probe.assert_awaited_once_with("device.local", 6054)


@pytest.mark.parametrize(
    "exception",
    [OSError("offline"), TimeoutError(), ValueError("protocol"), KeyError("device_id")],
)
async def test_user_error_recovery(
    hass: HomeAssistant, probe: AsyncMock, exception: Exception
) -> None:
    probe.side_effect = [exception, deepcopy(HELLO)]
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "127.0.0.1"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "127.0.0.1"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.parametrize("port", [0, -1, 65536, "bad"])
async def test_invalid_port(hass: HomeAssistant, probe: AsyncMock, port: Any) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    with pytest.raises(InvalidData):
        await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": "device.local", "port": port}
        )
    probe.assert_not_awaited()


@pytest.mark.parametrize("identity", [DEVICE_ID, "AA-BB-CC-DD-EE-FF", NORMALIZED_ID])
async def test_duplicate_user(
    hass: HomeAssistant, probe: AsyncMock, identity: str
) -> None:
    existing = MockConfigEntry(
        domain=DOMAIN, unique_id=NORMALIZED_ID, data={"host": "old.local", "port": 1000}
    )
    existing.add_to_hass(hass)
    probe.return_value["device_id"] = identity
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "new.local", "port": 6054}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert existing.data == {"host": "new.local", "port": 6054}
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_missing_name(hass: HomeAssistant, probe: AsyncMock) -> None:
    probe.return_value.pop("name")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "device.local"}
    )
    assert result["title"] == "OpenBeken"
    assert result["data"]["port"] == DEFAULT_PORT


async def test_empty_name(hass: HomeAssistant, probe: AsyncMock) -> None:
    probe.return_value["name"] = ""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "device.local"}
    )
    assert result["title"] == DEVICE_ID
    assert result["data"]["name"] == DEVICE_ID


@pytest.mark.parametrize("port", [6054, 7654, None])
async def test_discovery(
    hass: HomeAssistant, probe: AsyncMock, port: int | None
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "zeroconf"}, data=discovery(port=port)
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"
    assert result["description_placeholders"] == {"name": "Test device"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == NORMALIZED_ID
    assert result["data"]["port"] == (port or DEFAULT_PORT)
    probe.assert_awaited_once_with("127.0.0.1", port or DEFAULT_PORT)


@pytest.mark.parametrize(
    ("properties", "reason"),
    [
        ({"api": "2", "id": DEVICE_ID}, "unsupported_protocol"),
        ({"id": DEVICE_ID}, "unsupported_protocol"),
        ({"api": "1"}, "no_device_id"),
    ],
)
async def test_invalid_discovery(
    hass: HomeAssistant, properties: dict[str, str], reason: str
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "zeroconf"}, data=discovery(properties=properties)
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == reason


async def test_discovery_name_fallback(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "zeroconf"},
        data=discovery(properties={"api": "1", "id": DEVICE_ID}),
    )
    assert result["description_placeholders"] == {"name": "Test device"}


async def test_duplicate_discovery_updates_host_and_port(hass: HomeAssistant) -> None:
    existing = MockConfigEntry(
        domain=DOMAIN, unique_id=NORMALIZED_ID, data={"host": "old.local", "port": 6054}
    )
    existing.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "zeroconf"}, data=discovery(port=7654)
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert existing.data["host"] == "127.0.0.1"
    assert existing.data["port"] == 7654


@pytest.mark.parametrize(
    "exception",
    [OSError("offline"), TimeoutError(), ValueError("protocol"), KeyError("device_id")],
)
async def test_discovery_error_recovery(
    hass: HomeAssistant, probe: AsyncMock, exception: Exception
) -> None:
    probe.side_effect = [exception, deepcopy(HELLO)]
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "zeroconf"}, data=discovery()
    )
    probe.assert_not_awaited()
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_discovery_identity_mismatch(
    hass: HomeAssistant, probe: AsyncMock
) -> None:
    probe.return_value["device_id"] = "other"
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "zeroconf"}, data=discovery()
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["errors"] == {"base": "cannot_connect"}
    probe.return_value["device_id"] = "aa-bb-cc-dd-ee-ff"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_duplicate_in_progress(hass: HomeAssistant) -> None:
    first = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "zeroconf"}, data=discovery()
    )
    second = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "zeroconf"}, data=discovery()
    )
    assert first["type"] is FlowResultType.FORM
    assert second["type"] is FlowResultType.ABORT
    assert second["reason"] == "already_in_progress"


async def test_real_device_probe(hass: HomeAssistant, device: DeviceEmulator) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "127.0.0.1", "port": device.port}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == NORMALIZED_ID
