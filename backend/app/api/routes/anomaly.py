"""API routes for anomaly injection and schedule management."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.anomaly import (
    AnomalyActiveResponse,
    AnomalyInjectRequest,
    AnomalyScheduleBatchSet,
    AnomalyScheduleResponse,
)
from app.schemas.common import ApiResponse
from app.services import anomaly_service

router = APIRouter()


@router.post(
    "/{device_id}/anomaly",
    response_model=ApiResponse[AnomalyActiveResponse],
)
async def inject_anomaly(
    device_id: uuid.UUID,
    data: AnomalyInjectRequest,
) -> ApiResponse[AnomalyActiveResponse]:
    anomaly_service.inject_anomaly(device_id, data)
    return ApiResponse(
        data=AnomalyActiveResponse(
            register_name=data.register_name,
            anomaly_type=data.anomaly_type,
            anomaly_params=data.anomaly_params,
        )
    )


@router.get(
    "/{device_id}/anomaly",
    response_model=ApiResponse[list[AnomalyActiveResponse]],
)
async def get_active_anomalies(
    device_id: uuid.UUID,
) -> ApiResponse[list[AnomalyActiveResponse]]:
    active = anomaly_service.get_active_anomalies(device_id)
    return ApiResponse(
        data=[
            AnomalyActiveResponse(
                register_name=reg,
                anomaly_type=state.anomaly_type,
                anomaly_params=state.params,
            )
            for reg, state in active.items()
        ]
    )


@router.delete(
    "/{device_id}/anomaly",
    response_model=ApiResponse[None],
)
async def clear_anomalies(
    device_id: uuid.UUID,
) -> ApiResponse[None]:
    anomaly_service.clear_anomalies(device_id)
    return ApiResponse(message="All anomalies cleared")


# Schedule routes must be registered before /{register_name} to avoid
# the wildcard matching "schedules" as a register name.

@router.get(
    "/{device_id}/anomaly/schedules",
    response_model=ApiResponse[list[AnomalyScheduleResponse]],
)
async def get_schedules(
    device_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[AnomalyScheduleResponse]]:
    schedules = await anomaly_service.get_schedules(session, device_id)
    return ApiResponse(
        data=[AnomalyScheduleResponse.model_validate(s) for s in schedules]
    )


@router.put(
    "/{device_id}/anomaly/schedules",
    response_model=ApiResponse[list[AnomalyScheduleResponse]],
)
async def set_schedules(
    device_id: uuid.UUID,
    data: AnomalyScheduleBatchSet,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[AnomalyScheduleResponse]]:
    schedules = await anomaly_service.set_schedules(session, device_id, data)
    return ApiResponse(
        data=[AnomalyScheduleResponse.model_validate(s) for s in schedules]
    )


@router.delete(
    "/{device_id}/anomaly/schedules",
    response_model=ApiResponse[None],
)
async def delete_schedules(
    device_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[None]:
    await anomaly_service.delete_schedules(session, device_id)
    return ApiResponse(message="All schedules deleted")


@router.delete(
    "/{device_id}/anomaly/{register_name}",
    response_model=ApiResponse[None],
)
async def remove_anomaly(
    device_id: uuid.UUID,
    register_name: str,
) -> ApiResponse[None]:
    anomaly_service.remove_anomaly(device_id, register_name)
    return ApiResponse(message="Anomaly removed")
