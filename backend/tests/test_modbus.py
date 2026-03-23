"""Integration tests for Modbus TCP protocol adapter."""

import struct
import uuid

import pytest
from pymodbus.client import AsyncModbusTcpClient

from app.protocols.base import RegisterInfo
from app.protocols.modbus_tcp import ModbusTcpAdapter, encode_value

TEST_HOST = "127.0.0.1"
TEST_PORT = 5020


@pytest.fixture
async def adapter():
    """Start a ModbusTcpAdapter on test port, yield it, then stop."""
    a = ModbusTcpAdapter(host=TEST_HOST, port=TEST_PORT)
    await a.start()
    yield a
    await a.stop()


@pytest.fixture
async def client(adapter):
    """Connect a pymodbus async client to the test adapter."""
    c = AsyncModbusTcpClient(TEST_HOST, port=TEST_PORT, timeout=3)
    await c.connect()
    assert c.connected
    yield c
    c.close()


SAMPLE_REGISTERS = [
    RegisterInfo(address=0, function_code=4, data_type="float32", byte_order="big_endian"),
    RegisterInfo(address=10, function_code=3, data_type="uint16", byte_order="big_endian"),
]


class TestAdapterLifecycle:
    async def test_start_stop(self) -> None:
        adapter = ModbusTcpAdapter(host=TEST_HOST, port=TEST_PORT)
        await adapter.start()
        status = adapter.get_status()
        assert status["running"] is True
        assert status["port"] == TEST_PORT
        assert status["device_count"] == 0
        await adapter.stop()
        status = adapter.get_status()
        assert status["running"] is False

    async def test_add_device(self, adapter) -> None:
        device_id = uuid.uuid4()
        await adapter.add_device(device_id, slave_id=1, registers=SAMPLE_REGISTERS)
        status = adapter.get_status()
        assert status["device_count"] == 1
        assert 1 in status["slave_ids"]

    async def test_remove_device(self, adapter) -> None:
        device_id = uuid.uuid4()
        await adapter.add_device(device_id, slave_id=1, registers=SAMPLE_REGISTERS)
        await adapter.remove_device(device_id)
        status = adapter.get_status()
        assert status["device_count"] == 0

    async def test_remove_nonexistent_device(self, adapter) -> None:
        """Remove a device that was never added — should be no-op."""
        await adapter.remove_device(uuid.uuid4())

    async def test_duplicate_slave_id_raises(self, adapter) -> None:
        device1 = uuid.uuid4()
        device2 = uuid.uuid4()
        await adapter.add_device(device1, slave_id=1, registers=SAMPLE_REGISTERS)
        with pytest.raises(ValueError, match="already registered"):
            await adapter.add_device(device2, slave_id=1, registers=SAMPLE_REGISTERS)


class TestModbusReadWrite:
    async def test_read_initial_zeros(self, adapter, client) -> None:
        """After adding a device, registers should read as zero."""
        device_id = uuid.uuid4()
        regs = [RegisterInfo(address=0, function_code=3, data_type="uint16", byte_order="big_endian")]
        await adapter.add_device(device_id, slave_id=1, registers=regs)

        result = await client.read_holding_registers(0, count=1, device_id=1)
        assert not result.isError()
        assert result.registers[0] == 0

    async def test_read_input_registers(self, adapter, client) -> None:
        """FC04 (input registers) should also work."""
        device_id = uuid.uuid4()
        regs = [RegisterInfo(address=0, function_code=4, data_type="uint16", byte_order="big_endian")]
        await adapter.add_device(device_id, slave_id=1, registers=regs)

        result = await client.read_input_registers(0, count=1, device_id=1)
        assert not result.isError()
        assert result.registers[0] == 0

    async def test_update_and_read_uint16(self, adapter, client) -> None:
        device_id = uuid.uuid4()
        regs = [RegisterInfo(address=0, function_code=3, data_type="uint16", byte_order="big_endian")]
        await adapter.add_device(device_id, slave_id=1, registers=regs)

        await adapter.update_register(device_id, address=0, function_code=3,
                                       value=12345, data_type="uint16", byte_order="big_endian")

        result = await client.read_holding_registers(0, count=1, device_id=1)
        assert result.registers[0] == 12345

    async def test_update_and_read_float32_big_endian(self, adapter, client) -> None:
        device_id = uuid.uuid4()
        regs = [RegisterInfo(address=0, function_code=4, data_type="float32", byte_order="big_endian")]
        await adapter.add_device(device_id, slave_id=1, registers=regs)

        await adapter.update_register(device_id, address=0, function_code=4,
                                       value=3.14, data_type="float32", byte_order="big_endian")

        result = await client.read_input_registers(0, count=2, device_id=1)
        assert not result.isError()
        # Decode back: big endian float32
        raw = struct.pack(">HH", result.registers[0], result.registers[1])
        decoded = struct.unpack(">f", raw)[0]
        assert abs(decoded - 3.14) < 0.001

    async def test_update_and_read_int32(self, adapter, client) -> None:
        device_id = uuid.uuid4()
        regs = [RegisterInfo(address=0, function_code=3, data_type="int32", byte_order="big_endian")]
        await adapter.add_device(device_id, slave_id=1, registers=regs)

        await adapter.update_register(device_id, address=0, function_code=3,
                                       value=-100000, data_type="int32", byte_order="big_endian")

        result = await client.read_holding_registers(0, count=2, device_id=1)
        raw = struct.pack(">HH", result.registers[0], result.registers[1])
        decoded = struct.unpack(">i", raw)[0]
        assert decoded == -100000


class TestMultiSlave:
    async def test_two_slaves_independent(self, adapter, client) -> None:
        """Two devices with different slave IDs have independent registers."""
        dev1 = uuid.uuid4()
        dev2 = uuid.uuid4()
        regs = [RegisterInfo(address=0, function_code=3, data_type="uint16", byte_order="big_endian")]
        await adapter.add_device(dev1, slave_id=1, registers=regs)
        await adapter.add_device(dev2, slave_id=2, registers=regs)

        await adapter.update_register(dev1, 0, 3, 111, "uint16", "big_endian")
        await adapter.update_register(dev2, 0, 3, 222, "uint16", "big_endian")

        r1 = await client.read_holding_registers(0, count=1, device_id=1)
        r2 = await client.read_holding_registers(0, count=1, device_id=2)
        assert r1.registers[0] == 111
        assert r2.registers[0] == 222

    async def test_removed_slave_returns_error(self, adapter, client) -> None:
        """After removing a slave, reading should fail (timeout or error)."""
        from pymodbus.exceptions import ModbusIOException

        device_id = uuid.uuid4()
        regs = [RegisterInfo(address=0, function_code=3, data_type="uint16", byte_order="big_endian")]
        await adapter.add_device(device_id, slave_id=1, registers=regs)
        await adapter.remove_device(device_id)

        # Server drops requests for missing devices, causing timeout
        with pytest.raises(ModbusIOException):
            await client.read_holding_registers(0, count=1, device_id=1)


class TestEncodeValue:
    def test_uint16(self) -> None:
        assert encode_value(42, "uint16", "big_endian") == [42]

    def test_int16_negative(self) -> None:
        words = encode_value(-1, "int16", "big_endian")
        assert words == [0xFFFF]

    def test_float32_big_endian(self) -> None:
        words = encode_value(1.0, "float32", "big_endian")
        raw = struct.pack(">HH", words[0], words[1])
        assert struct.unpack(">f", raw)[0] == 1.0

    def test_float32_little_endian_word_swap(self) -> None:
        """little_endian_word_swap = CD AB (reversed word order, same byte order)."""
        words_be = encode_value(1.0, "float32", "big_endian")
        words_ws = encode_value(1.0, "float32", "little_endian_word_swap")
        # Words should be reversed
        assert words_ws == list(reversed(words_be))

    def test_int32_big_endian(self) -> None:
        words = encode_value(100000, "int32", "big_endian")
        raw = struct.pack(">HH", words[0], words[1])
        assert struct.unpack(">i", raw)[0] == 100000


# ---------------------------------------------------------------------------
# Device API integration tests — HTTP start/stop creates/removes Modbus slaves
# ---------------------------------------------------------------------------

from httpx import ASGITransport, AsyncClient as HttpClient

from app.main import app as fastapi_app
from app.protocols import protocol_manager

API_TEST_PORT = 5021


class TestDeviceApiIntegration:
    """Test that HTTP API start/stop actually creates Modbus slaves."""

    @pytest.fixture(autouse=True)
    async def setup_protocol(self):
        """Setup protocol manager with test adapter (DB handled by conftest)."""
        test_adapter = ModbusTcpAdapter(host=TEST_HOST, port=API_TEST_PORT)
        protocol_manager.register_adapter("modbus_tcp", test_adapter)
        await protocol_manager.start_all()

        yield

        await protocol_manager.stop_all()
        protocol_manager._adapters.clear()
        protocol_manager._running = False

    @pytest.fixture
    async def http(self):
        """HTTP client for testing FastAPI endpoints."""
        transport = ASGITransport(app=fastapi_app)
        async with HttpClient(transport=transport, base_url="http://test") as ac:
            yield ac

    async def test_start_device_creates_modbus_slave(self, http: HttpClient) -> None:
        # Create template
        resp = await http.post("/api/v1/templates", json={
            "name": "Modbus Test Meter",
            "protocol": "modbus_tcp",
            "registers": [{
                "name": "voltage",
                "address": 0,
                "function_code": 4,
                "data_type": "float32",
                "byte_order": "big_endian",
                "scale_factor": 1.0,
                "unit": "V",
                "sort_order": 0,
            }],
        })
        assert resp.status_code == 201
        template_id = resp.json()["data"]["id"]

        # Create device
        resp = await http.post("/api/v1/devices", json={
            "template_id": template_id,
            "name": "Test Device",
            "slave_id": 10,
        })
        assert resp.status_code == 201
        device_id = resp.json()["data"]["id"]

        # Start device via API
        resp = await http.post(f"/api/v1/devices/{device_id}/start")
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "running"

        # Verify Modbus client can read from slave 10
        modbus_client = AsyncModbusTcpClient(TEST_HOST, port=API_TEST_PORT, timeout=3)
        await modbus_client.connect()
        result = await modbus_client.read_input_registers(0, count=2, device_id=10)
        assert not result.isError()
        modbus_client.close()

    async def test_stop_device_removes_modbus_slave(self, http: HttpClient) -> None:
        from pymodbus.exceptions import ModbusIOException

        # Create + start device
        resp = await http.post("/api/v1/templates", json={
            "name": "Modbus Test Meter 2",
            "protocol": "modbus_tcp",
            "registers": [{
                "name": "current",
                "address": 0,
                "function_code": 3,
                "data_type": "uint16",
                "byte_order": "big_endian",
                "scale_factor": 1.0,
                "unit": "A",
                "sort_order": 0,
            }],
        })
        assert resp.status_code == 201
        template_id = resp.json()["data"]["id"]

        resp = await http.post("/api/v1/devices", json={
            "template_id": template_id,
            "name": "Test Device 2",
            "slave_id": 20,
        })
        assert resp.status_code == 201
        device_id = resp.json()["data"]["id"]

        await http.post(f"/api/v1/devices/{device_id}/start")
        await http.post(f"/api/v1/devices/{device_id}/stop")

        # Verify Modbus slave is gone (timeout = error)
        modbus_client = AsyncModbusTcpClient(TEST_HOST, port=API_TEST_PORT, timeout=3)
        await modbus_client.connect()
        with pytest.raises(ModbusIOException):
            await modbus_client.read_holding_registers(0, count=1, device_id=20)
        modbus_client.close()
