# Phase 5: Simulation Engine — Design Spec

## Overview

GhostMeter Phase 5 implements the core simulation engine that makes virtual devices "come alive" by generating realistic register values and simulating communication faults. This is the most important phase — without it, devices are static shells.

**Scope (Round 1):** Milestone 5.1 (Data Generation Engine) + Milestone 5.3 (Fault Simulation)
**Deferred (Round 2):** Milestone 5.2 (Anomaly Injection) + Milestone 5.4 (Frontend UI)

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Engine architecture | Per-device asyncio.Task | Isolation between devices; natural fit with device start/stop lifecycle; asyncio handles <100 tasks easily |
| Update frequency | Configurable, default 1000ms | Single interval per device (minimum of all register configs); per-register intervals deferred to Round 2 |
| Computed mode expressions | Simple 4-op parser (+-*/) with register variable references | Covers 90% of energy device formulas; safe AST-based parsing, no arbitrary code execution |
| Fault interception layer | Inside ModbusTcpAdapter | pymodbus supports custom request handler; no extra proxy layer needed |
| Simulation config granularity | Per-register | Different registers need different modes (voltage→daily_curve, energy→accumulator, PF→static) |
| Fault config storage | In-memory only (Round 1) | Instant effect via API; persistence deferred to Round 2 with scheduling |

## DB Model: `simulation_configs`

```
simulation_configs
├── id: UUID (PK)
├── device_id: UUID (FK → device_instances, CASCADE DELETE)
├── register_name: str (matches register_definitions.name)
├── data_mode: str (static | random | daily_curve | computed | accumulator)
├── mode_params: JSONB
├── is_enabled: bool (default true)
├── update_interval_ms: int (default 1000)
├── created_at: datetime(tz=UTC)
├── updated_at: datetime(tz=UTC)
└── UNIQUE(device_id, register_name)
```

### mode_params by data_mode

| data_mode | mode_params example |
|-----------|---------------------|
| static | `{"value": 230.0}` |
| random | `{"base": 230.0, "amplitude": 5.0, "distribution": "gaussian"}` |
| daily_curve | `{"base": 230.0, "amplitude": 10.0, "peak_hour": 14, "curve_type": "sine"}` |
| computed | `{"expression": "{voltage_l1} * {current_l1}"}` |
| accumulator | `{"start_value": 0.0, "increment_per_second": 0.5}` |

**Why `register_name` instead of `register_id`:** Register definitions belong to templates, not devices. Using name allows the same logical mapping across multiple devices from the same template, and is more readable in API payloads.

**Validation:** Service layer must validate `register_name` against the device's template registers on create/update. Register names must be URL-safe (alphanumeric + underscore) — enforced at template creation.

**Alembic:** A new migration must be created for this table.

## SimulationEngine Architecture

```
SimulationEngine (module-level instance, like protocol_manager)
├── _device_tasks: dict[UUID, asyncio.Task]
├── _device_configs: dict[UUID, list[SimConfig]]
│
├── async start_device(device_id)
│   → Load simulation_configs from DB
│   → Spawn per-device asyncio.Task
│
├── async stop_device(device_id)
│   → Cancel task, remove from _device_tasks
│
├── async reload_device(device_id)
│   → stop + start (for live config changes)
│
└── async shutdown()
    → Cancel all tasks
```

### Per-device Task Loop

```python
async def _run_device(device_id, configs, register_map, protocol_manager, protocol):
    """
    configs: list of SimulationConfig from DB
    register_map: dict[str, RegisterInfo] built from template's register definitions
    protocol_manager: ProtocolManager instance (not raw adapter)
    protocol: str (e.g. "modbus_tcp")
    """
    state = SimulationState(start_time=utcnow())
    current_values: dict[str, float] = {}
    adapter = protocol_manager.get_adapter(protocol)

    while True:
        try:
            context = GeneratorContext(
                current_values=current_values,
                elapsed_seconds=(utcnow() - state.start_time).total_seconds(),
                tick_count=state.tick_count,
            )

            # Sort by template register sort_order (important for computed mode)
            sorted_configs = sorted(
                configs, key=lambda c: register_map[c.register_name].sort_order
            )
            for config in sorted_configs:
                if not config.is_enabled:
                    continue
                reg = register_map[config.register_name]
                generated_value = data_generator.generate(
                    config.data_mode, config.mode_params, context
                )
                # Apply scale_factor: raw register value = physical value / scale_factor
                raw_value = generated_value / reg.scale_factor if reg.scale_factor != 0 else generated_value
                current_values[config.register_name] = generated_value
                await adapter.update_register(
                    device_id, reg.address, reg.function_code,
                    raw_value, reg.data_type, reg.byte_order
                )

            state.tick_count += 1
        except Exception as e:
            logger.error(f"Simulation tick failed for device {device_id}: {e}")
            state.error_count += 1
            if state.error_count >= 5:
                logger.error(f"Device {device_id} simulation stopped after 5 consecutive errors")
                break  # Engine will set device status to "error"

        await asyncio.sleep(interval_seconds)
```

### Lifecycle Integration

**Device start sequence:**
1. Validate status == "stopped"
2. Load template + registers
3. `protocol_manager.add_device(protocol, device_id, slave_id, registers)`
4. `simulation_engine.start_device(device_id)` ← NEW
5. Set status = "running"

**Device stop sequence:**
1. Validate status != "stopped"
2. `simulation_engine.stop_device(device_id)` ← NEW
3. `protocol_manager.remove_device(protocol, device_id)`
4. Set status = "stopped"

### DB Session Access

The engine runs as background tasks, not within FastAPI request handlers. It imports `async_session_factory` from `app.database` and creates sessions within its own scope (using `async with async_session_factory() as session`).

### State Management

- Accumulator cumulative values live in memory (`SimulationState`), not persisted to DB
- Computed mode reads from `current_values` dict (same tick's already-calculated results)
- Calculation order determined by register `sort_order` from template
- `scale_factor` applied between generator output and register write: `raw_register_value = physical_value / scale_factor`

### Error Handling

- Per-tick exceptions are caught and logged, not propagated
- After 5 consecutive tick failures, the task stops and device status is set to "error"
- Individual register errors within a tick are logged but do not stop the tick

### Computed Mode Edge Cases

- If a referenced register has no config or is disabled, use `0.0` as default with a warning log
- Circular references are not supported and must be prevented by service-layer validation

## DataGenerator Module

Stateless generator — dispatches to mode-specific methods.

### Mode Implementations

**static:** Returns `params["value"]` directly.

**random:** `base +/- amplitude` with uniform or gaussian distribution. Gaussian uses `amplitude / 3` as sigma (99.7% within range).

**daily_curve:** Sinusoidal curve based on UTC hour. `base + amplitude * sin(pi * (hour - peak_hour + 6) / 12)`. Peak at `peak_hour` (default 14), trough 12 hours later.

**computed:** Safe expression evaluation using AST parsing.
1. Replace `{register_name}` placeholders with values from `context.current_values`
2. Parse with Python `ast` module
3. Only allow: `BinOp` (+, -, *, /), `UnaryOp` (-), `Constant`/`Num` nodes
4. Reject function calls, attribute access, all other node types
5. Walk AST and compute manually — no arbitrary code execution

**accumulator:** `start_value + increment_per_second * elapsed_seconds`. Elapsed time from `context.elapsed_seconds`.

### GeneratorContext

```python
@dataclass
class GeneratorContext:
    current_values: dict[str, float]  # Same-tick calculated register values
    elapsed_seconds: float            # Seconds since simulation started
    tick_count: int                   # Tick counter
```

## FaultSimulator Module

Per-device fault state management. Intercepts at the protocol adapter layer.

### Fault Types

| fault_type | params | behavior |
|-----------|--------|----------|
| delay | `{"delay_ms": 500}` | Sleep before responding |
| timeout | `{}` | Never respond (client times out) |
| exception | `{"exception_code": 2}` | Return Modbus exception response |
| intermittent | `{"failure_rate": 0.3}` | Random non-response at given probability |

### ModbusTcpAdapter Integration

Override `ModbusConnectedRequestHandler` with `FaultAwareRequestHandler`.

**Reverse mapping:** `ModbusTcpAdapter` needs a `_slave_to_device: dict[int, UUID]` reverse mapping, maintained alongside `_device_to_slave` in `add_device()`/`remove_device()`.

**FaultSimulator access:** `fault_simulator` is a module-level instance imported directly by the handler.

```python
class FaultAwareRequestHandler(ModbusConnectedRequestHandler):
    async def execute(self, request, *addr):
        device_id = _slave_to_device.get(request.unit_id)  # reverse mapping
        fault = fault_simulator.get_fault(device_id) if device_id else None

        if fault is None:
            return await super().execute(request, *addr)

        match fault.fault_type:
            case "delay":
                await asyncio.sleep(fault.params["delay_ms"] / 1000)
                return await super().execute(request, *addr)
            case "timeout":
                await asyncio.sleep(30)
                return None
            case "exception":
                return ExceptionResponse(
                    request.function_code, fault.params["exception_code"]
                )
            case "intermittent":
                if random.random() < fault.params["failure_rate"]:
                    await asyncio.sleep(30)
                    return None
                return await super().execute(request, *addr)
```

**Fallback:** If pymodbus does not support custom handler class via `StartAsyncTcpServer`, use `request_tracer` callback instead.

### FaultSimulator API

```python
class FaultSimulator:
    _device_faults: dict[UUID, FaultConfig]

    def set_fault(device_id, fault_config) -> None
    def clear_fault(device_id) -> None
    def get_fault(device_id) -> FaultConfig | None
```

In-memory only (Round 1). No DB persistence.

## API Design

### Simulation Config Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/devices/{id}/simulation` | Get all register simulation configs for device |
| PUT | `/api/v1/devices/{id}/simulation` | Batch set/replace all register configs |
| PATCH | `/api/v1/devices/{id}/simulation/{register_name}` | Update single register config |
| DELETE | `/api/v1/devices/{id}/simulation` | Clear all simulation configs |

### Fault Control Endpoints

| Method | Path | Description |
|--------|------|-------------|
| PUT | `/api/v1/devices/{id}/fault` | Set communication fault (idempotent, replaces current) |
| GET | `/api/v1/devices/{id}/fault` | Get current fault state |
| DELETE | `/api/v1/devices/{id}/fault` | Clear fault |

### Request/Response Examples

```json
// PUT /api/v1/devices/{id}/simulation
{
  "configs": [
    {"register_name": "voltage_l1", "data_mode": "daily_curve",
     "mode_params": {"base": 230, "amplitude": 10, "peak_hour": 14}},
    {"register_name": "current_l1", "data_mode": "random",
     "mode_params": {"base": 15, "amplitude": 2, "distribution": "gaussian"}},
    {"register_name": "power_l1", "data_mode": "computed",
     "mode_params": {"expression": "{voltage_l1} * {current_l1}"}}
  ]
}

// Response: standard ApiResponse envelope
{"success": true, "data": [...]}

// POST /api/v1/devices/{id}/fault
{"fault_type": "delay", "params": {"delay_ms": 500}}
```

### Config Change Behavior

- Device **stopped** → write to DB only, applies on next start
- Device **running** → write to DB + call `simulation_engine.reload_device()` for immediate effect

## File Structure

### New Files

```
backend/app/
├── simulation/
│   ├── __init__.py            # export SimulationEngine, simulation_engine
│   ├── engine.py              # SimulationEngine (lifecycle + per-device tasks)
│   ├── data_generator.py      # DataGenerator (stateless, 5 modes)
│   ├── expression_parser.py   # Safe AST-based 4-op expression parser
│   └── fault_simulator.py     # FaultSimulator (in-memory fault state)
├── models/
│   └── simulation.py          # SimulationConfig ORM model
├── schemas/
│   └── simulation.py          # Pydantic request/response schemas
├── services/
│   └── simulation_service.py  # Simulation config CRUD business logic
├── api/routes/
│   └── simulation.py          # API route handlers
```

### Modified Files

- `main.py` — lifespan: init simulation_engine
- `services/device_service.py` — start/stop: call simulation_engine
- `protocols/modbus_tcp.py` — FaultAwareRequestHandler integration + `_slave_to_device` reverse mapping
- `models/__init__.py` — export SimulationConfig
- `api/routes/__init__.py` — register simulation router
- New Alembic migration for `simulation_configs` table

### Module Dependency Direction (unidirectional)

```
routes → simulation_service → SimulationEngine → DataGenerator
                                               → FaultSimulator
                            → protocol_manager (write register values)
         device_service → SimulationEngine (start/stop)
         ModbusTcpAdapter → FaultSimulator (intercept requests)
```

## Out of Scope (Round 2)

- `anomaly_injector.py` — spike, drift, flatline, out_of_range, data_loss
- Frontend simulation settings UI
- Fault config DB persistence
- Anomaly/fault scheduling system
- WebSocket push (Phase 6)
