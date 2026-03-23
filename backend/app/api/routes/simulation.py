"""API routes for simulation configuration and fault control."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.common import ApiResponse
from app.schemas.simulation import (
    FaultConfigResponse,
    FaultConfigSet,
    SimulationConfigBatchSet,
    SimulationConfigCreate,
    SimulationConfigResponse,
)
from app.services import simulation_service
from app.services.monitor_service import monitor_service
from app.simulation import fault_simulator
from app.simulation.fault_simulator import FaultConfig

router = APIRouter()


# --- Simulation Config Endpoints ---


@router.get(
    "/{device_id}/simulation",
    response_model=ApiResponse[list[SimulationConfigResponse]],
)
async def get_simulation_configs(
    device_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[SimulationConfigResponse]]:
    """List all simulation configs for a device."""
    configs = await simulation_service.get_simulation_configs(session, device_id)
    return ApiResponse(
        data=[SimulationConfigResponse.model_validate(c) for c in configs]
    )


@router.put(
    "/{device_id}/simulation",
    response_model=ApiResponse[list[SimulationConfigResponse]],
)
async def set_simulation_configs(
    device_id: uuid.UUID,
    data: SimulationConfigBatchSet,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[SimulationConfigResponse]]:
    """Batch set (replace) all simulation configs for a device."""
    configs = await simulation_service.set_simulation_configs(session, device_id, data)
    return ApiResponse(
        data=[SimulationConfigResponse.model_validate(c) for c in configs]
    )


@router.patch(
    "/{device_id}/simulation/{register_name}",
    response_model=ApiResponse[SimulationConfigResponse],
)
async def update_simulation_config(
    device_id: uuid.UUID,
    register_name: str,
    data: SimulationConfigCreate,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[SimulationConfigResponse]:
    """Upsert a single register's simulation config."""
    config = await simulation_service.update_simulation_config(
        session, device_id, register_name, data,
    )
    return ApiResponse(data=SimulationConfigResponse.model_validate(config))


@router.delete(
    "/{device_id}/simulation",
    response_model=ApiResponse[None],
)
async def delete_simulation_configs(
    device_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[None]:
    """Delete all simulation configs for a device."""
    await simulation_service.delete_simulation_configs(session, device_id)
    return ApiResponse(message="Simulation configs deleted successfully")


# --- Fault Control Endpoints ---


@router.put(
    "/{device_id}/fault",
    response_model=ApiResponse[FaultConfigResponse],
)
async def set_fault(
    device_id: uuid.UUID,
    data: FaultConfigSet,
) -> ApiResponse[FaultConfigResponse]:
    """Set a communication fault on a device (in-memory)."""
    fault = FaultConfig(fault_type=data.fault_type, params=data.params)
    fault_simulator.set_fault(device_id, fault)
    monitor_service.log_event(
        device_id, str(device_id), "fault_set",
        f"Fault set: {data.fault_type}",
    )
    return ApiResponse(
        data=FaultConfigResponse(
            fault_type=fault.fault_type,
            params=fault.params,
        )
    )


@router.get(
    "/{device_id}/fault",
    response_model=ApiResponse[FaultConfigResponse | None],
)
async def get_fault(
    device_id: uuid.UUID,
) -> ApiResponse[FaultConfigResponse | None]:
    """Get the active fault for a device."""
    fault = fault_simulator.get_fault(device_id)
    if fault is None:
        return ApiResponse(data=None)
    return ApiResponse(
        data=FaultConfigResponse(
            fault_type=fault.fault_type,
            params=fault.params,
        )
    )


@router.delete(
    "/{device_id}/fault",
    response_model=ApiResponse[None],
)
async def clear_fault(
    device_id: uuid.UUID,
) -> ApiResponse[None]:
    """Clear the active fault for a device."""
    fault_simulator.clear_fault(device_id)
    monitor_service.log_event(
        device_id, str(device_id), "fault_clear", "Fault cleared",
    )
    return ApiResponse(message="Fault cleared successfully")
