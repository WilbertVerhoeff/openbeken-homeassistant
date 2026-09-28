"""Exercise framing, handshake deadlines, commands and reconnect lifecycle."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.openbeken.const import DOMAIN
from custom_components.openbeken.coordinator import (
    MAX_LINE,
    OpenBekenCoordinator,
    _read_json_line,
    async_probe_device,
)

from .conftest import DEVICE_ID, ENTITIES, HELLO, DeviceEmulator
from .helpers import has_state, wait_until


def stream(*messages: dict) -> asyncio.StreamReader:
    reader = asyncio.StreamReader()
    for message in messages:
        reader.feed_data(json.dumps(message).encode() + b"\n")
    reader.feed_eof()
    return reader


def writer_mock() -> MagicMock:
    writer = MagicMock(spec=asyncio.StreamWriter)
    writer.drain = AsyncMock()
    writer.wait_closed = AsyncMock()
    writer.is_closing.return_value = False
    return writer


@pytest.fixture
def coordinator(hass: HomeAssistant, entry: MockConfigEntry) -> OpenBekenCoordinator:
    return OpenBekenCoordinator(
        hass, entry, "127.0.0.1", entry.data["port"], "Test device", DEVICE_ID
    )


@pytest.mark.parametrize(
    "raw,error",
    [
        (b"", ConnectionError),
        (b"{}", ValueError),
        (b"[]\n", ValueError),
        (b"null\n", ValueError),
        (b"42\n", ValueError),
        (b"broken\n", ValueError),
        (b" " * MAX_LINE + b"\n", ValueError),
    ],
)
async def test_invalid_frame(raw: bytes, error: type[Exception]) -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(raw)
    reader.feed_eof()
    with pytest.raises(error):
        await _read_json_line(reader)


async def test_frame_boundary_and_multiple_frames() -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(b" " * (MAX_LINE - 3) + b"{}\n" + b'{"next":true}\n')
    assert await _read_json_line(reader) == {}
    assert await _read_json_line(reader) == {"next": True}


async def test_incomplete_frame_timeout() -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(b'{"type":')
    with pytest.raises(TimeoutError):
        await _read_json_line(reader, timeout=0.01)


@pytest.mark.parametrize(
    "changes", [{"type": "ping"}, {"protocol": 2}, {"device_id": ""}]
)
async def test_probe_rejects_bad_hello(changes: dict) -> None:
    writer = writer_mock()
    with patch(
        "custom_components.openbeken.coordinator.asyncio.open_connection",
        AsyncMock(return_value=(stream(HELLO | changes), writer)),
    ):
        with pytest.raises(ValueError, match="protocol 1"):
            await async_probe_device("host", 6054)
    writer.close.assert_called_once()
    writer.wait_closed.assert_awaited_once()
    writer.write.assert_not_called()


async def test_probe_success() -> None:
    writer = writer_mock()
    with patch(
        "custom_components.openbeken.coordinator.asyncio.open_connection",
        AsyncMock(return_value=(stream(HELLO), writer)),
    ):
        assert await async_probe_device("host", 6054) == HELLO
    assert json.loads(writer.write.call_args.args[0]) == {
        "type": "hello",
        "protocol": 1,
        "client": "home-assistant",
    }
    writer.close.assert_called_once()


@pytest.mark.parametrize("error", [OSError("offline"), TimeoutError()])
async def test_probe_open_failure(error: Exception) -> None:
    with patch(
        "custom_components.openbeken.coordinator.asyncio.open_connection",
        AsyncMock(side_effect=error),
    ):
        with pytest.raises(type(error)):
            await async_probe_device("host", 6054)


@pytest.mark.parametrize(
    "changes", [{"type": "ping"}, {"protocol": 2}, {"device_id": "other"}]
)
async def test_handshake_rejects_identity(
    coordinator: OpenBekenCoordinator, changes: dict
) -> None:
    writer = writer_mock()
    with patch(
        "custom_components.openbeken.coordinator.asyncio.open_connection",
        AsyncMock(return_value=(stream(HELLO | changes), writer)),
    ):
        with pytest.raises(UpdateFailed, match="identity or protocol changed"):
            await coordinator._connect_once()
    assert not coordinator.connected
    assert coordinator._writer is None
    writer.close.assert_called_once()


async def test_handshake_requires_entities_and_full_snapshot(
    coordinator: OpenBekenCoordinator,
) -> None:
    reader = stream(
        HELLO | {"device_id": "aa-bb-cc-dd-ee-ff"},
        {"type": "state", "full": True, "entities": {}},
        {"type": "entities", "entities": ENTITIES},
        {"type": "state", "full": False, "entities": {}},
        {
            "type": "state",
            "full": True,
            "seq": 3,
            "entities": {"temp_2": {"value": 22}},
        },
    )
    writer = writer_mock()
    with patch(
        "custom_components.openbeken.coordinator.asyncio.open_connection",
        AsyncMock(return_value=(reader, writer)),
    ):
        await coordinator._handshake()
    assert coordinator.states == {"temp_2": {"value": 22}}
    assert coordinator._seq == 3
    assert coordinator.firmware == HELLO["firmware"]
    assert set(coordinator.entities) == {item["id"] for item in ENTITIES}
    await coordinator.async_shutdown()


async def test_handshake_has_overall_deadline(
    coordinator: OpenBekenCoordinator,
) -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(json.dumps(HELLO).encode() + b"\n")
    writer = writer_mock()
    with (
        patch("custom_components.openbeken.coordinator.CONNECT_TIMEOUT", 0.02),
        patch(
            "custom_components.openbeken.coordinator.asyncio.open_connection",
            AsyncMock(return_value=(reader, writer)),
        ),
    ):
        with pytest.raises(UpdateFailed):
            await coordinator._connect_once()
    writer.close.assert_called_once()
    assert not coordinator.connected


async def test_cancelled_handshake_cleans_socket(
    coordinator: OpenBekenCoordinator,
) -> None:
    reader = asyncio.StreamReader()
    writer = writer_mock()
    with patch(
        "custom_components.openbeken.coordinator.asyncio.open_connection",
        AsyncMock(return_value=(reader, writer)),
    ):
        task = asyncio.create_task(coordinator._connect_once())
        await wait_until(lambda: coordinator._writer is writer)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    writer.close.assert_called_once()
    assert coordinator._reader is None


@pytest.mark.parametrize("method", ["async_set_state", "async_restart"])
async def test_send_failure_cleans_pending(
    coordinator: OpenBekenCoordinator, method: str
) -> None:
    args = ("relay_1", {"on": True}) if method == "async_set_state" else ()
    with pytest.raises(ConnectionError):
        await getattr(coordinator, method)(*args)
    assert coordinator._pending == {}


@pytest.mark.parametrize("method", ["async_set_state", "async_restart"])
async def test_command_rejected(
    hass: HomeAssistant,
    setup_entry: MockConfigEntry,
    device: DeviceEmulator,
    method: str,
) -> None:
    device.command_success = False
    coordinator = hass.data[DOMAIN][setup_entry.entry_id]
    args = ("relay_1", {"on": True}) if method == "async_set_state" else ()
    with pytest.raises(ValueError, match="rejected"):
        await getattr(coordinator, method)(*args)
    assert coordinator._pending == {}


@pytest.mark.parametrize("method", ["async_set_state", "async_restart"])
async def test_command_timeout_cleans_pending(
    coordinator: OpenBekenCoordinator, method: str
) -> None:
    args = ("relay_1", {"on": True}) if method == "async_set_state" else ()

    async def cancel_wait(future, *, timeout):
        assert timeout == 5
        future.cancel()
        raise TimeoutError

    with (
        patch.object(coordinator, "_send", AsyncMock()),
        patch("custom_components.openbeken.coordinator.asyncio.wait_for", cancel_wait),
    ):
        with pytest.raises(TimeoutError):
            await getattr(coordinator, method)(*args)
    assert coordinator._pending == {}


@pytest.mark.parametrize("closing", [True, False])
async def test_send_requires_live_writer(
    coordinator: OpenBekenCoordinator, closing: bool
) -> None:
    if closing:
        coordinator._writer = writer_mock()
        coordinator._writer.is_closing.return_value = True
    with pytest.raises(ConnectionError):
        await coordinator._send({"type": "ping"})


async def test_close_fails_pending_and_is_idempotent(
    coordinator: OpenBekenCoordinator, hass: HomeAssistant
) -> None:
    future = hass.loop.create_future()
    completed = hass.loop.create_future()
    completed.set_result({})
    coordinator._pending = {1: future, 2: completed}
    coordinator._writer = writer_mock()
    coordinator._writer.wait_closed.side_effect = OSError("closed")
    coordinator._connected = True
    await coordinator.async_shutdown()
    with pytest.raises(ConnectionError, match="disconnected"):
        await future
    assert completed.result() == {}
    assert not coordinator.connected
    assert not coordinator._pending
    await coordinator.async_shutdown()


async def test_message_filtering_and_unknown_results(
    coordinator: OpenBekenCoordinator, hass: HomeAssistant
) -> None:
    coordinator._handle_message(
        {"type": "entities", "entities": [None, {}, {"id": 1}, ENTITIES[2]]}
    )
    assert set(coordinator.entities) == {"temp_2"}
    coordinator._handle_message(
        {"type": "state", "entities": {"temp_2": {"value": 20}, "bad": None}}
    )
    assert coordinator.states == {"temp_2": {"value": 20}}
    for message in [
        {"type": "entities", "entities": None},
        {"type": "state", "entities": []},
        {"type": "state_changed", "state": None},
        {"type": "result", "id": "1"},
        {"type": "result", "id": 99},
        {"type": "unknown"},
    ]:
        coordinator._handle_message(message)
    future = hass.loop.create_future()
    future.cancel()
    coordinator._pending[1] = future
    coordinator._handle_message({"type": "result", "id": 1, "success": True})
    assert not coordinator._pending
    coordinator._handle_message({"type": "state_changed", "entity": None, "state": {}})
    coordinator._handle_message(
        {"type": "state_changed", "entity": "temp_2", "state": {"value": 23}}
    )
    assert coordinator.states["temp_2"] == {"value": 23}


async def test_invalid_device_metadata_ignored(
    coordinator: OpenBekenCoordinator,
) -> None:
    coordinator._handle_message(
        {"type": "entities", "entities": [], "device": {"name": 42, "firmware": ""}}
    )
    assert coordinator.device_name == "Test device"
    assert coordinator.firmware is None


async def test_disconnected_maintenance_sends_nothing(
    coordinator: OpenBekenCoordinator,
) -> None:
    with patch.object(coordinator, "_send", AsyncMock()) as send:
        await coordinator.async_request_state()
        await coordinator.async_send_heartbeat()
    send.assert_not_awaited()


async def test_ping_and_sequence_gap_resync(
    hass: HomeAssistant, setup_entry: MockConfigEntry, device: DeviceEmulator
) -> None:
    await device.push({"type": "ping"})
    assert await device.next_command("ping") == {"type": "ping"}
    device.seq = 7
    device.states["temp_2"] = {"value": 25}
    await device.push(
        {"type": "state_changed", "seq": 7, "entity": "temp_2", "state": {"value": 24}}
    )
    assert await device.next_command("get_state") == {"type": "get_state"}
    await wait_until(lambda: has_state(hass, "sensor.test_device_temperature", "25"))


async def test_reconnect_restores_entities_and_metadata(
    hass: HomeAssistant, setup_entry: MockConfigEntry, device: DeviceEmulator
) -> None:
    coordinator = hass.data[DOMAIN][setup_entry.entry_id]
    await device.next_command("hello")
    device.hello["firmware"] = "2.0"
    device.states["temp_2"]["value"] = 26
    await device.disconnect()
    await device.next_command("hello")
    await wait_until(lambda: has_state(hass, "sensor.test_device_temperature", "26"))
    assert coordinator.connected
    assert coordinator.firmware == "2.0"
    assert len(hass.states.async_all()) == 5


async def test_reconnect_retries_then_succeeds(
    coordinator: OpenBekenCoordinator,
) -> None:
    with (
        patch.object(
            coordinator,
            "_connect_once",
            AsyncMock(side_effect=[UpdateFailed("offline"), None]),
        ) as connect,
        patch(
            "custom_components.openbeken.coordinator.asyncio.sleep", AsyncMock()
        ) as sleep,
    ):
        await coordinator._reconnect_loop()
    assert connect.await_count == 2
    sleep.assert_awaited_once_with(5)
    coordinator._stop.set()
    with patch.object(coordinator, "_connect_once", AsyncMock()) as connect:
        await coordinator._reconnect_loop()
    connect.assert_not_awaited()


async def test_stopped_reader_does_not_reconnect(
    coordinator: OpenBekenCoordinator,
) -> None:
    coordinator._reader = stream()
    coordinator._stop.set()
    await coordinator._reader_loop()
    assert coordinator._runner is None


@pytest.mark.parametrize("error", [OSError("closed"), TimeoutError()])
async def test_probe_close_failure_does_not_mask_result(error: Exception) -> None:
    writer = writer_mock()
    writer.wait_closed.side_effect = error
    with patch(
        "custom_components.openbeken.coordinator.asyncio.open_connection",
        AsyncMock(return_value=(stream(HELLO), writer)),
    ):
        assert await async_probe_device("host", 6054) == HELLO
    writer.close.assert_called_once()


async def test_probe_drain_failure_closes_socket() -> None:
    writer = writer_mock()
    writer.drain.side_effect = TimeoutError()
    with patch(
        "custom_components.openbeken.coordinator.asyncio.open_connection",
        AsyncMock(return_value=(stream(HELLO), writer)),
    ):
        with pytest.raises(TimeoutError):
            await async_probe_device("host", 6054)
    writer.close.assert_called_once()
    writer.wait_closed.assert_awaited_once()


@pytest.mark.parametrize("method", ["async_set_state", "async_restart"])
async def test_cancelled_command_cleans_pending(
    hass: HomeAssistant,
    setup_entry: MockConfigEntry,
    device: DeviceEmulator,
    method: str,
) -> None:
    device.reply_commands = False
    coordinator = hass.data[DOMAIN][setup_entry.entry_id]
    args = ("relay_1", {"on": True}) if method == "async_set_state" else ()
    task = asyncio.create_task(getattr(coordinator, method)(*args))
    await device.next_command("set_state" if args else "restart")
    assert len(coordinator._pending) == 1
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not coordinator._pending


async def test_disconnect_fails_pending_command(
    hass: HomeAssistant, setup_entry: MockConfigEntry, device: DeviceEmulator
) -> None:
    device.reply_commands = False
    coordinator = hass.data[DOMAIN][setup_entry.entry_id]
    task = asyncio.create_task(coordinator.async_set_state("relay_1", {"on": True}))
    await device.next_command("set_state")
    await device.disconnect()
    with pytest.raises(ConnectionError, match="disconnected"):
        await task
    assert not coordinator._pending


async def test_concurrent_commands_match_out_of_order_results(
    hass: HomeAssistant, setup_entry: MockConfigEntry, device: DeviceEmulator
) -> None:
    device.reply_commands = False
    coordinator = hass.data[DOMAIN][setup_entry.entry_id]
    tasks = [
        asyncio.create_task(coordinator.async_set_state("relay_1", {"on": True})),
        asyncio.create_task(coordinator.async_restart()),
    ]
    first = await device.next_command("set_state")
    second = await device.next_command("restart")
    assert first["id"] != second["id"]
    assert len(coordinator._pending) == 2
    await device.push({"type": "result", "id": second["id"], "success": False})
    with pytest.raises(ValueError, match="restart"):
        await tasks[1]
    assert not tasks[0].done()
    await device.push({"type": "result", "id": first["id"], "success": True})
    await tasks[0]
    assert not coordinator._pending


async def test_shutdown_cancels_remaining_runner(
    coordinator: OpenBekenCoordinator,
) -> None:
    # If shutdown is called by the reader itself, close must not cancel it.
    coordinator._runner = asyncio.current_task()
    await coordinator._close_connection()
    assert coordinator._runner is asyncio.current_task()
    runner = MagicMock()
    coordinator._runner = runner
    with patch.object(coordinator, "_close_connection", AsyncMock()):
        await coordinator.async_shutdown()
    runner.cancel.assert_called_once()
    assert coordinator._runner is None


@pytest.mark.parametrize("identity", [None, 123, True, [], {}])
async def test_non_string_identity_is_protocol_error(
    coordinator: OpenBekenCoordinator, identity: object
) -> None:
    writer = writer_mock()
    with patch(
        "custom_components.openbeken.coordinator.asyncio.open_connection",
        AsyncMock(return_value=(stream(HELLO | {"device_id": identity}), writer)),
    ):
        with pytest.raises(ValueError):
            await async_probe_device("host", 6054)
    writer.close.assert_called_once()
    writer = writer_mock()
    with patch(
        "custom_components.openbeken.coordinator.asyncio.open_connection",
        AsyncMock(return_value=(stream(HELLO | {"device_id": identity}), writer)),
    ):
        with pytest.raises(UpdateFailed):
            await coordinator._connect_once()
    assert not coordinator.connected
    writer.close.assert_called_once()


@pytest.mark.parametrize("seq", [None, "3", [], {}])
async def test_invalid_snapshot_sequence_does_not_break_push(
    coordinator: OpenBekenCoordinator, seq: object
) -> None:
    coordinator._handle_message(
        {"type": "state", "seq": seq, "entities": {"temp_2": {"value": 20}}}
    )
    assert coordinator._seq is None
    coordinator._handle_message(
        {"type": "state_changed", "seq": 4, "entity": "temp_2", "state": {"value": 21}}
    )
    assert coordinator._seq == 4
    assert coordinator.states["temp_2"] == {"value": 21}
