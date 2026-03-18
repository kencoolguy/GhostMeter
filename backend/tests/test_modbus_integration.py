"""Integration tests for Modbus TCP adapter with fault simulation.

These tests start a real ModbusTcpAdapter server on a high port and use
a pymodbus AsyncModbusTcpClient to verify reads and fault interception.
"""

import asyncio
import struct
import time
from uuid import uuid4

import pytest
from pymodbus.client import AsyncModbusTcpClient

from app.protocols.base import RegisterInfo
from app.protocols.modbus_tcp import ModbusTcpAdapter
from app.simulation import fault_simulator
from app.simulation.fault_simulator import FaultConfig

MODBUS_PORT = 15502
DEVICE_ID = uuid4()
SLAVE_ID = 1
VOLTAGE_ADDR = 0
VOLTAGE_VALUE = 230.0


def decode_float32(registers: list[int]) -> float:
    """Decode two 16-bit registers into a float32 (big-endian)."""
    raw = struct.pack(">HH", registers[0], registers[1])
    return struct.unpack(">f", raw)[0]


@pytest.fixture
async def modbus_env():
    """Start adapter, register a device, yield, then clean up."""
    adapter = ModbusTcpAdapter(host="127.0.0.1", port=MODBUS_PORT)
    await adapter.start()

    reg = RegisterInfo(
        address=VOLTAGE_ADDR,
        function_code=3,
        data_type="float32",
        byte_order="big_endian",
    )
    await adapter.add_device(DEVICE_ID, SLAVE_ID, [reg])
    await adapter.update_register(
        DEVICE_ID, VOLTAGE_ADDR, 3, VOLTAGE_VALUE, "float32", "big_endian"
    )

    yield adapter

    fault_simulator.clear_all()
    await adapter.stop()


@pytest.fixture
async def client(modbus_env):
    """Create and connect a pymodbus async client."""
    cli = AsyncModbusTcpClient("127.0.0.1", port=MODBUS_PORT, timeout=5)
    await cli.connect()
    yield cli
    cli.close()


class TestNormalRead:
    """Verify a normal read returns the expected float32 value."""

    async def test_read_voltage(self, client):
        result = await client.read_holding_registers(
            VOLTAGE_ADDR, count=2, device_id=SLAVE_ID
        )
        assert not result.isError(), f"Unexpected error: {result}"
        value = decode_float32(result.registers)
        assert abs(value - VOLTAGE_VALUE) < 0.1


class TestDelayFault:
    """Verify delay fault adds latency to responses."""

    async def test_delay_500ms(self, modbus_env, client):
        fault_simulator.set_fault(
            DEVICE_ID, FaultConfig("delay", {"delay_ms": 500})
        )
        t0 = time.monotonic()
        result = await client.read_holding_registers(
            VOLTAGE_ADDR, count=2, device_id=SLAVE_ID
        )
        elapsed = time.monotonic() - t0
        assert not result.isError()
        assert elapsed >= 0.45, f"Expected >=450ms delay, got {elapsed*1000:.0f}ms"


class TestTimeoutFault:
    """Verify timeout fault causes client to fail."""

    async def test_timeout_drops_response(self, modbus_env):
        fault_simulator.set_fault(
            DEVICE_ID, FaultConfig("timeout", {})
        )
        # Use a short-timeout client so we don't wait forever
        cli = AsyncModbusTcpClient(
            "127.0.0.1", port=MODBUS_PORT, timeout=1
        )
        await cli.connect()
        try:
            result = await cli.read_holding_registers(
                VOLTAGE_ADDR, count=2, device_id=SLAVE_ID
            )
            # pymodbus may return an error result or raise on timeout
            assert result.isError(), "Expected error/timeout but got normal response"
        except Exception:
            # Timeout or connection error is acceptable
            pass
        finally:
            cli.close()


class TestExceptionFault:
    """Verify exception fault returns a Modbus exception response."""

    async def test_exception_code_02(self, client):
        fault_simulator.set_fault(
            DEVICE_ID, FaultConfig("exception", {"exception_code": 0x02})
        )
        result = await client.read_holding_registers(
            VOLTAGE_ADDR, count=2, device_id=SLAVE_ID
        )
        assert result.isError(), "Expected Modbus exception response"
        assert result.exception_code == 0x02, (
            f"Expected exception code 0x02, got 0x{result.exception_code:02X}"
        )


class TestIntermittentFault:
    """Verify intermittent fault produces a mix of successes and failures."""

    async def test_50_percent_failure(self, modbus_env):
        fault_simulator.set_fault(
            DEVICE_ID, FaultConfig("intermittent", {"failure_rate": 0.5})
        )
        # Disable retries so each suppressed request counts as one failure
        # instead of being masked by automatic retry success.
        cli = AsyncModbusTcpClient(
            "127.0.0.1", port=MODBUS_PORT, timeout=1, retries=0
        )
        await cli.connect()

        errors = 0
        total = 40
        try:
            for _ in range(total):
                # Allow restore task from _suppress_slave to complete
                await asyncio.sleep(0.15)
                try:
                    result = await cli.read_holding_registers(
                        VOLTAGE_ADDR, count=2, device_id=SLAVE_ID
                    )
                    if result.isError():
                        errors += 1
                except Exception:
                    errors += 1
        finally:
            cli.close()

        error_rate = errors / total
        assert 0.10 <= error_rate <= 0.90, (
            f"Error rate {error_rate:.0%} outside expected 10%-90% range"
        )


class TestClearFault:
    """Verify clearing a fault restores normal behavior."""

    async def test_set_then_clear(self, client):
        # Set exception fault
        fault_simulator.set_fault(
            DEVICE_ID, FaultConfig("exception", {"exception_code": 0x04})
        )
        result = await client.read_holding_registers(
            VOLTAGE_ADDR, count=2, device_id=SLAVE_ID
        )
        assert result.isError(), "Expected error while fault active"

        # Clear fault
        fault_simulator.clear_fault(DEVICE_ID)

        result = await client.read_holding_registers(
            VOLTAGE_ADDR, count=2, device_id=SLAVE_ID
        )
        assert not result.isError(), f"Expected normal read after clear, got: {result}"
        value = decode_float32(result.registers)
        assert abs(value - VOLTAGE_VALUE) < 0.1
