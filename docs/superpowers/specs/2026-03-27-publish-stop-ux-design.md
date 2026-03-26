# Publish / Stop UX Unification Design

**Issue**: #11
**Date**: 2026-03-27
**Status**: Approved

## Goal

Unify the start/stop UX across Modbus and MQTT while maintaining the existing separated architecture. The device lifecycle (start/stop) remains tied to Modbus + simulation, and MQTT publishing retains independent control. The changes are purely UX improvements.

## Scope

- Frontend only (except one backend field addition)
- No changes to device state machine or protocol lifecycle
- No changes to API endpoint structure

## Design

### 1. MQTT Card: Edit/Publish Mode Separation

Redesign `MqttPublishConfig.tsx` to enforce a clear edit-then-publish workflow.

**Stopped Mode (editable):**
- All form fields enabled: topic template, payload mode, interval, QoS, retain
- Bottom buttons: `Save` (saves config only) + `Start Publishing` (auto-saves then starts)
- Status badge: gray "Stopped"

**Publishing Mode (read-only):**
- All form fields disabled, showing current config values
- Status badge: green pulsing "Publishing"
- Bottom button: `Stop Publishing` only
- Helper text below fields: "Stop publishing to edit settings"

**State transitions:**
```
[No Config] → Save → [Stopped, config saved]
[Stopped]   → Save → [Stopped, config updated]
[Stopped]   → Start Publishing → auto-save → [Publishing]
[Publishing] → Stop Publishing → [Stopped]
```

### 2. Device List MQTT Status Indicator

Add a small MQTT publishing indicator next to the device status badge in the device list table.

**Display rules:**
- Device running + MQTT publishing → green `MQTT` Tag (Ant Design `<Tag color="green">MQTT</Tag>`)
- Device running + MQTT not publishing → no tag
- Device stopped → no tag

**Backend change:**
- Add `mqtt_publishing: boolean` field to `DeviceResponse` schema
- In device list query, LEFT JOIN `mqtt_publish_configs` to check `enabled` status
- This avoids N+1 frontend requests

### 3. Device Detail Protocol Status Summary

Add MQTT status tag to the Device Detail page header, next to the existing device status badge.

**Display:**
- `[Running] [MQTT Publishing]` — when device is running and MQTT is active
- `[Running]` — when device is running without MQTT publish
- `[Stopped]` — when device is stopped (no MQTT tag)

Uses the same green `MQTT` Tag component as the device list.

### 4. Button Style Unification

Align MQTT button styles with device start/stop conventions:

| Button | Style |
|--------|-------|
| Start Publishing | `type="primary"` with green tone (consistent with device start) |
| Stop Publishing | `danger` style (consistent with device stop) |
| Save | `default` style (neutral) |

No changes to Device List start/stop buttons (already consistent).

## Files to Modify

### Backend
- `backend/app/schemas/device.py` — add `mqtt_publishing: bool` to `DeviceResponse`
- `backend/app/services/device_service.py` — join `mqtt_publish_configs` in list query

### Frontend
- `frontend/src/pages/Devices/MqttPublishConfig.tsx` — edit/publish mode separation
- `frontend/src/pages/Devices/DeviceList.tsx` — MQTT status tag in table
- `frontend/src/pages/Devices/DeviceDetail.tsx` — MQTT status tag in header
- `frontend/src/types/device.ts` — add `mqtt_publishing` field to device type

## Out of Scope

- SNMP start/stop UX (follows device lifecycle, no independent control needed)
- Protocol Dashboard panel (deferred, over-design for current needs)
- Modbus-specific UX changes (already well-designed)
- Backend API endpoint changes (existing endpoints are sufficient)
