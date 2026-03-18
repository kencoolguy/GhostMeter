"""Modbus TCP protocol adapter using pymodbus async server."""

import asyncio
import logging
import struct
from uuid import UUID

from pymodbus.datastore import (
    ModbusDeviceContext,
    ModbusSequentialDataBlock,
    ModbusServerContext,
)
from pymodbus.server import ModbusTcpServer

from app.protocols.base import ProtocolAdapter, RegisterInfo

logger = logging.getLogger(__name__)

# Data type → register count
DATA_TYPE_REGISTER_COUNT: dict[str, int] = {
    "int16": 1,
    "uint16": 1,
    "int32": 2,
    "uint32": 2,
    "float32": 2,
    "float64": 4,
}


def encode_value(
    value: float,
    data_type: str,
    byte_order: str,
) -> list[int]:
    """Encode a value into 16-bit register words based on data type and byte order.

    Returns a list of unsigned 16-bit integers.
    """
    if data_type == "int16":
        raw = struct.pack(">h", int(value))
        return [struct.unpack(">H", raw)[0]]
    if data_type == "uint16":
        return [int(value) & 0xFFFF]
    if data_type == "int32":
        raw = struct.pack(">i", int(value))
    elif data_type == "uint32":
        raw = struct.pack(">I", int(value))
    elif data_type == "float32":
        raw = struct.pack(">f", value)
    elif data_type == "float64":
        raw = struct.pack(">d", value)
    else:
        raise ValueError(f"Unsupported data type: {data_type}")

    # Split into 16-bit words (big endian byte order within each word)
    words = []
    for i in range(0, len(raw), 2):
        words.append(struct.unpack(">H", raw[i : i + 2])[0])

    # Apply word/byte order
    if byte_order == "big_endian":
        # AB CD — already in correct order
        return words
    elif byte_order == "little_endian":
        # DC BA — reverse bytes within each word, then reverse word order
        reversed_words = []
        for w in words:
            b = struct.pack(">H", w)
            reversed_words.append(struct.unpack("<H", b)[0])
        reversed_words.reverse()
        return reversed_words
    elif byte_order == "big_endian_word_swap":
        # BA DC — reverse bytes within each word, keep word order
        result = []
        for w in words:
            b = struct.pack(">H", w)
            result.append(struct.unpack("<H", b)[0])
        return result
    elif byte_order == "little_endian_word_swap":
        # CD AB — keep bytes within word, reverse word order
        words.reverse()
        return words
    else:
        raise ValueError(f"Unsupported byte order: {byte_order}")


class ModbusTcpAdapter(ProtocolAdapter):
    """Modbus TCP server adapter using pymodbus."""

    def __init__(self, host: str = "0.0.0.0", port: int = 502) -> None:
        self._host = host
        self._port = port
        self._server: ModbusTcpServer | None = None
        self._server_task: asyncio.Task | None = None
        self._context: ModbusServerContext | None = None
        self._device_to_slave: dict[UUID, int] = {}
        self._slave_to_device: dict[int, UUID] = {}
        self._slave_contexts: dict[int, ModbusDeviceContext] = {}
        self._device_registers: dict[UUID, list[RegisterInfo]] = {}

    async def start(self) -> None:
        """Start the Modbus TCP server."""
        # Start with empty device dict — slaves added dynamically
        self._context = ModbusServerContext(devices={}, single=False)

        self._server = ModbusTcpServer(
            context=self._context,
            address=(self._host, self._port),
            ignore_missing_devices=True,
        )

        self._server_task = asyncio.create_task(self._server.serve_forever())
        # Give server a moment to bind
        await asyncio.sleep(0.1)
        logger.info("Modbus TCP server started on %s:%d", self._host, self._port)

    async def stop(self) -> None:
        """Stop the Modbus TCP server."""
        if self._server:
            await self._server.shutdown()
        if self._server_task:
            self._server_task.cancel()
            try:
                await self._server_task
            except asyncio.CancelledError:
                pass
        self._server = None
        self._server_task = None
        self._context = None
        self._device_to_slave.clear()
        self._slave_contexts.clear()
        self._device_registers.clear()
        self._slave_to_device.clear()
        logger.info("Modbus TCP server stopped")

    async def add_device(
        self,
        device_id: UUID,
        slave_id: int,
        registers: list[RegisterInfo],
    ) -> None:
        """Add a device as a Modbus slave."""
        if self._context is None:
            raise RuntimeError("Modbus server not started")

        if slave_id in self._slave_contexts:
            raise ValueError(f"Slave ID {slave_id} already registered")

        # Calculate required datastore sizes per function code.
        # pymodbus ModbusDeviceContext.getValues/setValues adds +1 to the address
        # internally, so we need size = end_addr + 1 to avoid ILLEGAL_ADDRESS.
        hr_size = 1
        ir_size = 1
        for reg in registers:
            reg_count = DATA_TYPE_REGISTER_COUNT.get(reg.data_type, 1)
            end_addr = reg.address + reg_count + 1
            if reg.function_code == 3:
                hr_size = max(hr_size, end_addr)
            elif reg.function_code == 4:
                ir_size = max(ir_size, end_addr)

        # Create slave context with zero-initialized datastores
        slave_context = ModbusDeviceContext(
            hr=ModbusSequentialDataBlock(0, [0] * hr_size),
            ir=ModbusSequentialDataBlock(0, [0] * ir_size),
        )

        # Register in server context via internal _devices dict
        self._context._devices[slave_id] = slave_context
        self._slave_contexts[slave_id] = slave_context
        self._device_to_slave[device_id] = slave_id
        self._slave_to_device[slave_id] = device_id
        self._device_registers[device_id] = registers
        logger.info("Added device %s as slave %d", device_id, slave_id)

    async def remove_device(self, device_id: UUID) -> None:
        """Remove a device from the server."""
        slave_id = self._device_to_slave.pop(device_id, None)
        if slave_id is None:
            return  # No-op for non-existent device

        self._slave_to_device.pop(slave_id, None)
        self._slave_contexts.pop(slave_id, None)
        self._device_registers.pop(device_id, None)
        if self._context is not None:
            self._context._devices.pop(slave_id, None)
        logger.info("Removed device %s (slave %d)", device_id, slave_id)

    async def update_register(
        self,
        device_id: UUID,
        address: int,
        function_code: int,
        value: float,
        data_type: str,
        byte_order: str,
    ) -> None:
        """Write a value into a device's register datastore."""
        slave_id = self._device_to_slave.get(device_id)
        if slave_id is None:
            raise ValueError(f"Device {device_id} not registered")

        slave_ctx = self._slave_contexts[slave_id]
        words = encode_value(value, data_type, byte_order)

        # function_code 3 → holding registers (fx=3), 4 → input registers (fx=4)
        slave_ctx.setValues(function_code, address, words)

    def get_status(self) -> dict:
        """Return adapter status."""
        return {
            "host": self._host,
            "port": self._port,
            "running": self._server is not None,
            "device_count": len(self._device_to_slave),
            "slave_ids": list(self._slave_contexts.keys()),
        }

    def get_device_id_for_slave(self, slave_id: int) -> UUID | None:
        """Resolve device UUID from Modbus slave ID."""
        return self._slave_to_device.get(slave_id)
