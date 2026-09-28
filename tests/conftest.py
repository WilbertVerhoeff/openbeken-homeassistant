"""Real Home Assistant fixtures and a local native API device emulator."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from copy import deepcopy
from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.openbeken.const import DOMAIN

DEVICE_ID = "AA:BB:CC:DD:EE:FF"
NORMALIZED_ID = "aabbccddeeff"
HELLO = {
    "type": "hello",
    "protocol": 1,
    "device_id": DEVICE_ID,
    "name": "Test device",
    "firmware": "1.18.100",
}
ENTITIES = [
    {
        "id": "light_0",
        "platform": "light",
        "name": "Light",
        "features": ["brightness", "rgb", "color_temp", "effects"],
        "min_mireds": 153,
        "max_mireds": 500,
        "effects": ["Rainbow", "Fire"],
    },
    {"id": "relay_1", "platform": "switch", "name": "Relay"},
    {
        "id": "temp_2",
        "platform": "sensor",
        "name": "Temperature",
        "unit": "°C",
        "device_class": "temperature",
        "state_class": "measurement",
    },
    {
        "id": "motion_3",
        "platform": "binary_sensor",
        "name": "Motion",
        "device_class": "motion",
    },
    {"id": "restart_0", "platform": "button", "name": "Restart"},
]
STATES = {
    "light_0": {
        "on": True,
        "brightness": 128,
        "rgb": [255, 0, 0],
        "color_temp": 250,
        "mode": "rgb",
        "effect": "",
    },
    "relay_1": {"on": False},
    "temp_2": {"value": 21.5},
    "motion_3": {"on": True},
}


@pytest.fixture(autouse=True)
def enable_integration(enable_custom_integrations: None) -> None:
    """Enable the actual integration through Home Assistant's loader."""


class DeviceEmulator:
    """Speak protocol 1 over loopback, without firmware or external networking."""

    def __init__(self) -> None:
        self.hello = deepcopy(HELLO)
        self.entities = deepcopy(ENTITIES)
        self.states = deepcopy(STATES)
        self.seq = 0
        self.port = 0
        self.server: asyncio.Server | None = None
        self.writers: set[asyncio.StreamWriter] = set()
        self.tasks: set[asyncio.Task] = set()
        self.commands: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.reply_commands = True
        self.command_success = True

    async def send(self, writer: asyncio.StreamWriter, message: dict[str, Any]) -> None:
        writer.write(json.dumps(message).encode() + b"\n")
        await writer.drain()

    async def handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        task = asyncio.current_task()
        assert task is not None
        self.tasks.add(task)
        self.writers.add(writer)
        try:
            await self.send(writer, self.hello)
            greeting = json.loads(await reader.readline())
            await self.commands.put(greeting)
            await self.send(writer, {"type": "entities", "entities": self.entities})
            await self.send(writer, self.snapshot())
            while raw := await reader.readline():
                command = json.loads(raw)
                await self.commands.put(command)
                if command["type"] == "get_state":
                    await self.send(writer, self.snapshot())
                elif (
                    command["type"] in ("set_state", "restart") and self.reply_commands
                ):
                    if command["type"] == "set_state" and self.command_success:
                        self.states[command["entity"]].update(command["state"])
                    await self.send(
                        writer,
                        {
                            "type": "result",
                            "id": command["id"],
                            "success": self.command_success,
                            "error": "rejected",
                        },
                    )
        except OSError, ValueError, json.JSONDecodeError:
            pass
        finally:
            self.writers.discard(writer)
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
            self.tasks.discard(task)

    def snapshot(self) -> dict[str, Any]:
        return {"type": "state", "full": True, "seq": self.seq, "entities": self.states}

    async def push(self, message: dict[str, Any]) -> None:
        for writer in tuple(self.writers):
            await self.send(writer, message)

    async def next_command(self, kind: str) -> dict[str, Any]:
        async with asyncio.timeout(2):
            while True:
                command = await self.commands.get()
                if command["type"] == kind:
                    return command

    async def disconnect(self) -> None:
        writers = tuple(self.writers)
        for writer in writers:
            writer.close()
        await asyncio.gather(*(writer.wait_closed() for writer in writers))


@pytest.fixture
async def device(socket_enabled: None) -> AsyncIterator[DeviceEmulator]:
    """Serve a device on an OS-assigned loopback port and close every socket."""
    emulator = DeviceEmulator()
    server = await asyncio.start_server(emulator.handle, "127.0.0.1", 0)
    emulator.server = server
    assert server.sockets is not None
    emulator.port = server.sockets[0].getsockname()[1]
    try:
        yield emulator
    finally:
        server.close()
        await emulator.disconnect()
        await server.wait_closed()
        await asyncio.gather(*tuple(emulator.tasks), return_exceptions=True)


@pytest.fixture
def entry(device: DeviceEmulator) -> MockConfigEntry:
    """One config entry with a real local API endpoint."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Test device",
        unique_id=NORMALIZED_ID,
        data={
            "host": "127.0.0.1",
            "port": device.port,
            "name": "Test device",
            "device_id": DEVICE_ID,
        },
    )


@pytest.fixture
async def setup_entry(
    hass: HomeAssistant, entry: MockConfigEntry
) -> AsyncIterator[MockConfigEntry]:
    """Set up and unload through the real Home Assistant config-entry API."""
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    try:
        yield entry
    finally:
        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
