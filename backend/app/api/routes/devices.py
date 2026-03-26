import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.exceptions import ValidationException
from app.schemas.common import ApiResponse
from app.schemas.device import (
    BatchActionResult,
    DeviceBatchAction,
    DeviceBatchCreate,
    DeviceCreate,
    DeviceDetail,
    DeviceSummary,
    DeviceUpdate,
    RegisterValue,
)
from app.services import device_service

router = APIRouter()


@router.get("", response_model=ApiResponse[list[DeviceSummary]])
async def list_devices(
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[DeviceSummary]]:
    """List all device instances."""
    devices = await device_service.list_devices(session)
    return ApiResponse(data=[DeviceSummary(**d) for d in devices])


@router.post("", response_model=ApiResponse[DeviceSummary], status_code=201)
async def create_device(
    data: DeviceCreate,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[DeviceSummary]:
    """Create a single device instance."""
    device = await device_service.create_device(session, data)
    return ApiResponse(data=DeviceSummary(**device))


# /batch MUST come before /{device_id}
@router.post("/batch", response_model=ApiResponse[list[DeviceSummary]], status_code=201)
async def batch_create_devices(
    data: DeviceBatchCreate,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[DeviceSummary]]:
    """Batch create device instances."""
    devices = await device_service.batch_create_devices(session, data)
    return ApiResponse(data=[DeviceSummary(**d) for d in devices])


@router.post("/batch/start", response_model=ApiResponse[BatchActionResult])
async def batch_start_devices(
    data: DeviceBatchAction,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[BatchActionResult]:
    """Batch start devices. Empty device_ids = start all stopped devices."""
    result = await device_service.batch_start_devices(
        session, data.device_ids if data.device_ids else None,
    )
    return ApiResponse(
        data=BatchActionResult(**result),
        message=f"Started {result['success_count']}, skipped {result['skipped_count']}, errors {result['error_count']}",
    )


@router.post("/batch/stop", response_model=ApiResponse[BatchActionResult])
async def batch_stop_devices(
    data: DeviceBatchAction,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[BatchActionResult]:
    """Batch stop devices. Empty device_ids = stop all running devices."""
    result = await device_service.batch_stop_devices(
        session, data.device_ids if data.device_ids else None,
    )
    return ApiResponse(
        data=BatchActionResult(**result),
        message=f"Stopped {result['success_count']}, skipped {result['skipped_count']}, errors {result['error_count']}",
    )


@router.post("/batch/delete", response_model=ApiResponse[BatchActionResult])
async def batch_delete_devices(
    data: DeviceBatchAction,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[BatchActionResult]:
    """Batch delete devices. Skips running devices. device_ids required."""
    if not data.device_ids:
        raise ValidationException(detail="device_ids is required for batch delete")
    result = await device_service.batch_delete_devices(session, data.device_ids)
    return ApiResponse(
        data=BatchActionResult(**result),
        message=f"Deleted {result['success_count']}, skipped {result['skipped_count']}, errors {result['error_count']}",
    )


@router.get("/{device_id}", response_model=ApiResponse[DeviceDetail])
async def get_device(
    device_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[DeviceDetail]:
    """Get device detail with register definitions."""
    detail = await device_service.get_device_detail(session, device_id)
    return ApiResponse(data=DeviceDetail(**detail))


@router.put("/{device_id}", response_model=ApiResponse[DeviceSummary])
async def update_device(
    device_id: uuid.UUID,
    data: DeviceUpdate,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[DeviceSummary]:
    """Update a device instance."""
    device = await device_service.update_device(session, device_id, data)
    return ApiResponse(data=DeviceSummary(**device))


@router.delete("/{device_id}", response_model=ApiResponse[None])
async def delete_device(
    device_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[None]:
    """Delete a device instance."""
    await device_service.delete_device(session, device_id)
    return ApiResponse(message="Device deleted successfully")


@router.post("/{device_id}/start", response_model=ApiResponse[DeviceSummary])
async def start_device(
    device_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[DeviceSummary]:
    """Start a device (stopped → running)."""
    device = await device_service.start_device(session, device_id)
    return ApiResponse(data=DeviceSummary(**device))


@router.post("/{device_id}/stop", response_model=ApiResponse[DeviceSummary])
async def stop_device(
    device_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[DeviceSummary]:
    """Stop a device (running/error → stopped)."""
    device = await device_service.stop_device(session, device_id)
    return ApiResponse(data=DeviceSummary(**device))


@router.get("/{device_id}/registers", response_model=ApiResponse[list[RegisterValue]])
async def get_device_registers(
    device_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[RegisterValue]]:
    """Get register values for a device (Phase 3: always null)."""
    registers = await device_service.get_device_registers(session, device_id)
    return ApiResponse(data=[RegisterValue(**r) for r in registers])
