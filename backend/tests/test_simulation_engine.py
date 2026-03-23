import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.simulation.engine import SimulationEngine


class TestSimulationEngineLifecycle:
    @pytest.mark.asyncio
    async def test_start_device_no_configs(self):
        engine = SimulationEngine()
        device_id = uuid.uuid4()
        with patch.object(engine, '_load_device_data', new_callable=AsyncMock) as mock_load:
            mock_load.return_value = ([], {}, "modbus_tcp")
            await engine.start_device(device_id)
            assert device_id not in engine._device_tasks

    @pytest.mark.asyncio
    async def test_stop_nonexistent_device_noop(self):
        engine = SimulationEngine()
        await engine.stop_device(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_shutdown_empty(self):
        engine = SimulationEngine()
        await engine.shutdown()
        assert len(engine._device_tasks) == 0

    @pytest.mark.asyncio
    async def test_reload_calls_load(self):
        engine = SimulationEngine()
        device_id = uuid.uuid4()
        with patch.object(engine, '_load_device_data', new_callable=AsyncMock) as mock_load:
            mock_load.return_value = ([], {}, "modbus_tcp")
            await engine.reload_device(device_id)
            assert mock_load.call_count == 1
