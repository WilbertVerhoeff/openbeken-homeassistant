"""Bounded waits for asynchronous TCP updates in Home Assistant."""

import asyncio
from collections.abc import Callable

from homeassistant.core import HomeAssistant


async def wait_until(predicate: Callable[[], bool]) -> None:
    """Wait for loopback IO to become visible, with a bounded deadline."""
    async with asyncio.timeout(2):
        while not predicate():
            await asyncio.sleep(0.01)


def has_state(hass: HomeAssistant, entity_id: str, value: str) -> bool:
    """Read a public HA state, allowing an entity still being added."""
    return (state := hass.states.get(entity_id)) is not None and state.state == value
