"""CRUD service for anomaly schedules + real-time anomaly control."""

import logging
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.exceptions import NotFoundException, ValidationException
from app.models.anomaly import AnomalySchedule
from app.models.device import DeviceInstance
from app.models.template import DeviceTemplate
from app.schemas.anomaly import (
    AnomalyInjectRequest,
    AnomalyScheduleBatchSet,
)
from app.simulation import anomaly_injector

logger = logging.getLogger(__name__)


async def _get_device_or_404(
    session: AsyncSession, device_id: uuid.UUID,
) -> DeviceInstance:
    stmt = select(DeviceInstance).where(DeviceInstance.id == device_id)
    result = await session.execute(stmt)
    device = result.scalar_one_or_none()
    if device is None:
        raise NotFoundException(
            detail="Device not found", error_code="DEVICE_NOT_FOUND"
        )
    return device


async def _get_template_register_names(
    session: AsyncSession, template_id: uuid.UUID,
) -> set[str]:
    stmt = (
        select(DeviceTemplate)
        .options(selectinload(DeviceTemplate.registers))
        .where(DeviceTemplate.id == template_id)
    )
    result = await session.execute(stmt)
    template = result.scalar_one()
    return {reg.name for reg in template.registers}


def _check_overlap(schedules: list, register_name: str) -> None:
    same_reg = [s for s in schedules if s.register_name == register_name]
    for i, a in enumerate(same_reg):
        a_start = a.trigger_after_seconds
        a_end = a_start + a.duration_seconds
        for b in same_reg[i + 1:]:
            b_start = b.trigger_after_seconds
            b_end = b_start + b.duration_seconds
            if a_start < b_end and b_start < a_end:
                raise ValidationException(
                    f"Overlapping schedule for register '{register_name}': "
                    f"[{a_start}s-{a_end}s) and [{b_start}s-{b_end}s)"
                )


def inject_anomaly(device_id: uuid.UUID, data: AnomalyInjectRequest) -> None:
    anomaly_injector.inject(
        device_id, data.register_name, data.anomaly_type, data.anomaly_params,
    )


def get_active_anomalies(device_id: uuid.UUID) -> dict:
    return anomaly_injector.get_active(device_id)


def remove_anomaly(device_id: uuid.UUID, register_name: str) -> None:
    anomaly_injector.remove(device_id, register_name)


def clear_anomalies(device_id: uuid.UUID) -> None:
    anomaly_injector.clear_realtime(device_id)


async def get_schedules(
    session: AsyncSession, device_id: uuid.UUID,
) -> list[AnomalySchedule]:
    await _get_device_or_404(session, device_id)
    stmt = (
        select(AnomalySchedule)
        .where(AnomalySchedule.device_id == device_id)
        .order_by(AnomalySchedule.trigger_after_seconds)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def set_schedules(
    session: AsyncSession,
    device_id: uuid.UUID,
    data: AnomalyScheduleBatchSet,
) -> list[AnomalySchedule]:
    device = await _get_device_or_404(session, device_id)
    valid_names = await _get_template_register_names(session, device.template_id)

    for sched in data.schedules:
        if sched.register_name not in valid_names:
            raise ValidationException(
                f"Register '{sched.register_name}' not found in device template"
            )

    register_names = {s.register_name for s in data.schedules}
    for name in register_names:
        _check_overlap(data.schedules, name)

    await session.execute(
        delete(AnomalySchedule).where(AnomalySchedule.device_id == device_id)
    )

    new_schedules = []
    for sched in data.schedules:
        db_sched = AnomalySchedule(
            device_id=device_id,
            register_name=sched.register_name,
            anomaly_type=sched.anomaly_type,
            anomaly_params=sched.anomaly_params,
            trigger_after_seconds=sched.trigger_after_seconds,
            duration_seconds=sched.duration_seconds,
            is_enabled=sched.is_enabled,
        )
        session.add(db_sched)
        new_schedules.append(db_sched)

    await session.commit()
    for s in new_schedules:
        await session.refresh(s)

    return new_schedules


async def delete_schedules(
    session: AsyncSession, device_id: uuid.UUID,
) -> None:
    await _get_device_or_404(session, device_id)
    await session.execute(
        delete(AnomalySchedule).where(AnomalySchedule.device_id == device_id)
    )
    await session.commit()
