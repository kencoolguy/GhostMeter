"""API routes for Modbus client write-event detection."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.common import ApiResponse
from app.schemas.write_event import WriteEventResponse, WriteEventsAckResponse
from app.services import device_service
from app.simulation import write_tracker

router = APIRouter()


@router.get(
    "/{device_id}/write-events",
    response_model=ApiResponse[list[WriteEventResponse]],
)
async def list_write_events(
    device_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[WriteEventResponse]]:
    """List recorded client write attempts (newest first). Pure read — no reset."""
    await device_service.get_device_protocol(session, device_id)  # 404s on unknown
    events = write_tracker.get_events(device_id)
    return ApiResponse(
        data=[
            WriteEventResponse(
                timestamp=e.timestamp,
                function_code=e.function_code,
                address=e.address,
                values=e.values,
                register_name=e.register_name,
            )
            for e in events
        ]
    )


@router.post(
    "/{device_id}/write-events/ack",
    response_model=ApiResponse[WriteEventsAckResponse],
)
async def ack_write_events(
    device_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[WriteEventsAckResponse]:
    """Reset the device's unread write count. The event buffer is retained."""
    await device_service.get_device_protocol(session, device_id)  # 404s on unknown
    write_tracker.mark_read(device_id)
    return ApiResponse(data=WriteEventsAckResponse(unread=0))
