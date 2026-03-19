# Phase 5: Simulation Engine — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the core simulation engine that generates realistic register values for running devices and simulates Modbus communication faults.

**Architecture:** Per-device asyncio.Task architecture. Each running device gets its own simulation loop that reads configs from DB, generates values via DataGenerator, applies scale_factor, and writes to the protocol adapter. FaultSimulator intercepts Modbus requests at the adapter layer with in-memory fault state.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, pymodbus, Alembic, pytest + pytest-asyncio + httpx

**Spec:** `docs/superpowers/specs/2026-03-18-phase5-simulation-engine-design.md`

---

## Task 1: SimulationConfig ORM Model + Alembic Migration

**Files:**
- Create: `backend/app/models/simulation.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/tests/conftest.py`

- [ ] Create `SimulationConfig` model with: id(UUID PK), device_id(FK CASCADE), register_name(str), data_mode(str), mode_params(JSONB), is_enabled(bool), update_interval_ms(int), created_at, updated_at. UniqueConstraint on (device_id, register_name).
- [ ] Add `SimulationConfig` to `models/__init__.py` exports
- [ ] Add `simulation_configs` to TRUNCATE in `tests/conftest.py`
- [ ] Run: `alembic revision --autogenerate -m "add simulation_configs table"` then `alembic upgrade head`
- [ ] Commit: `feat: add simulation_configs ORM model and migration`

## Task 2: Expression Parser (Safe AST-based)

**Files:**
- Create: `backend/app/simulation/expression_parser.py`
- Create: `backend/tests/test_expression_parser.py`

**Security:** Uses `ast.parse()` + manual AST walk. Only allows BinOp(+,-,*,/), UnaryOp, Constant nodes. Rejects function calls, attribute access, etc. Does NOT use `eval()`.

- [ ] Write tests: addition, multiplication, subtraction, division, operator precedence, parentheses, negation, {var} substitution, missing var defaults to 0.0, division by zero returns 0.0, reject function calls, reject attribute access, empty expression error
- [ ] Run tests — verify FAIL (module not found)
- [ ] Implement: `parse_and_evaluate(expression, variables)` with `_safe_ast_eval()` recursive walker. Use `re.compile(r"\{(\w+)\}")` for variable substitution.
- [ ] Run tests — verify all PASS
- [ ] Commit: `feat: add safe AST-based expression parser for computed mode`

## Task 3: DataGenerator Module

**Files:**
- Create: `backend/app/simulation/data_generator.py`
- Create: `backend/tests/test_data_generator.py`

- [ ] Write tests for all 5 modes: static(fixed value), random(uniform range, gaussian range, default distribution), daily_curve(peak at peak_hour, trough 12h later — use `current_hour_utc` override in GeneratorContext for deterministic tests), computed(var multiplication, missing var), accumulator(time-based, zero elapsed), unknown mode raises ValueError
- [ ] Run tests — verify FAIL
- [ ] Implement: `GeneratorContext` dataclass (current_values, elapsed_seconds, tick_count, current_hour_utc optional). `DataGenerator.generate()` dispatches via match/case. Uses `expression_parser.parse_and_evaluate` for computed mode.
- [ ] Run tests — verify all PASS
- [ ] Commit: `feat: add DataGenerator with 5 simulation modes`

## Task 4: FaultSimulator Module

**Files:**
- Create: `backend/app/simulation/fault_simulator.py`
- Create: `backend/tests/test_fault_simulator.py`

- [ ] Write tests: no fault by default, set+get fault, set replaces existing, clear fault, clear nonexistent noop, get with None returns None, multiple devices independent, clear_all
- [ ] Run tests — verify FAIL
- [ ] Implement: `FaultConfig` dataclass (fault_type, params). `FaultSimulator` with `_device_faults: dict[UUID, FaultConfig]` and set/clear/get/clear_all methods.
- [ ] Run tests — verify all PASS
- [ ] Commit: `feat: add FaultSimulator for in-memory fault state management`

## Task 5: ModbusTcpAdapter Reverse Mapping + Fault Integration

**Files:**
- Modify: `backend/app/protocols/modbus_tcp.py`
- Create: `backend/tests/test_modbus_fault.py`

- [ ] Research pymodbus handler support: `python -c "from pymodbus.server import ModbusTcpServer; import inspect; print(list(inspect.signature(ModbusTcpServer.__init__).parameters.keys()))"`
- [ ] Add `_slave_to_device: dict[int, UUID]` to `__init__`, populate in `add_device`, clear in `remove_device` and `stop`. Add `get_device_id_for_slave()` method.
- [ ] Integrate fault simulation based on pymodbus API findings (custom handler or request_tracer callback)
- [ ] Write tests for reverse mapping (add/remove verification)
- [ ] Run all tests — verify no regressions
- [ ] Commit: `feat: add reverse slave mapping and fault integration to ModbusTcpAdapter`

## Task 6: Pydantic Schemas

**Files:**
- Create: `backend/app/schemas/simulation.py`

- [ ] Create schemas: `SimulationConfigCreate` (with data_mode and interval validators), `SimulationConfigBatchSet`, `SimulationConfigResponse` (from_attributes), `FaultConfigSet` (with fault_type validator), `FaultConfigResponse`
- [ ] Commit: `feat: add Pydantic schemas for simulation config and fault control`

## Task 7: SimulationEngine Core

**Files:**
- Create: `backend/app/simulation/engine.py`
- Modify: `backend/app/simulation/__init__.py`
- Create: `backend/tests/test_simulation_engine.py`

- [ ] Write tests: start_device with mocked _load_device_data, stop nonexistent noop, shutdown empty, reload calls stop+start
- [ ] Run tests — verify FAIL
- [ ] Implement `SimulationEngine`: `_device_tasks` dict, `start_device` (load configs from DB, spawn asyncio.Task), `stop_device` (cancel task), `reload_device` (stop+start), `shutdown` (cancel all). `_run_device` loop: GeneratorContext per tick, sort by register sort_order, generate value, apply scale_factor (raw = physical / scale_factor), call adapter.update_register. Error handling: catch per-tick, 5 consecutive failures sets device to "error". `_load_device_data` uses `async_session_factory` directly. `RegisterMeta` dataclass for register metadata.
- [ ] Update `__init__.py`: export `simulation_engine = SimulationEngine()` and `fault_simulator = FaultSimulator()`
- [ ] Run tests — verify all PASS
- [ ] Run full test suite
- [ ] Commit: `feat: add SimulationEngine with per-device async task loop`

## Task 8: Simulation Service (CRUD)

**Files:**
- Create: `backend/app/services/simulation_service.py`

- [ ] Implement: `get_simulation_configs`, `set_simulation_configs` (validate register names against template, replace all), `update_simulation_config` (upsert single), `delete_simulation_configs`. All validate device exists (404). Running device triggers `simulation_engine.reload_device()` on config change.
- [ ] Commit: `feat: add simulation config CRUD service layer`

## Task 9: API Routes + Integration Tests

**Files:**
- Create: `backend/app/api/routes/simulation.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_simulation_api.py`

- [ ] Create routes: GET/PUT/PATCH/DELETE `/{device_id}/simulation`, PUT/GET/DELETE `/{device_id}/fault`
- [ ] Register router in `main.py`: `api_v1_router.include_router(simulation_router, prefix="/devices", tags=["simulation"])`
- [ ] Write API tests: empty configs, set configs, replace configs, patch single, delete configs, invalid register name (422), invalid data mode (422), device not found (404), fault set/get/clear, invalid fault type (422)
- [ ] Run API tests — verify all PASS
- [ ] Run full test suite
- [ ] Commit: `feat: add simulation config and fault control API routes`

## Task 10: Integrate SimulationEngine into Device Lifecycle

**Files:**
- Modify: `backend/app/services/device_service.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_device_simulation_integration.py`

- [ ] In `device_service.start_device()`: after protocol_manager.add_device, add `simulation_engine.start_device(device.id)` (guarded by `protocol_manager.is_running`)
- [ ] In `device_service.stop_device()`: before protocol_manager.remove_device, add `simulation_engine.stop_device(device.id)`
- [ ] In `main.py` lifespan shutdown: add `simulation_engine.shutdown()` before `protocol_manager.stop_all()`
- [ ] Write integration tests: config set on stopped device persists, fault API roundtrip
- [ ] Run all tests
- [ ] Commit: `feat: integrate simulation engine into device start/stop lifecycle`

## Post-Implementation Checklist

- [ ] Full test suite passes: `python -m pytest -v`
- [ ] Alembic check clean: `alembic check`
- [ ] Update `docs/development-phases.md` — Milestone 5.1 + 5.3 status
- [ ] Update `CHANGELOG.md` with Phase 5 additions
- [ ] Update `docs/api-reference.md` with new endpoints
- [ ] Update `docs/development-log.md`
