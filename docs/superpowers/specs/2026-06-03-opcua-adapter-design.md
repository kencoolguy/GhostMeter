# OPC UA Server Adapter — Design Spec

- **Date**: 2026-06-03
- **Status**: Approved (Approach A)
- **Milestone**: Phase 8.9 — OPC UA Server Adapter
- **Author**: Claude (brainstormed with Ken)

## 1. Goal

新增 **OPC UA** 作為第四個 protocol adapter，讓 EMS / SCADA OPC UA client 能瀏覽位址空間、讀取即時模擬值、訂閱數值變化。延續 `ProtocolAdapter` 既有的可插拔架構（已有 Modbus TCP / MQTT / SNMP）。

## 2. Scope

### In scope (MVP)
- 單一共用 OPC UA server（一個 endpoint，所有設備掛在同一 address space）。
- **Read + Subscribe**：client 可 browse / read / 訂閱 monitored items。
- 安全性：**SecurityPolicy = None + Anonymous**（不加密、免憑證）。
- 值同步走 **push model**：模擬引擎 `update_register` → 寫入對應 variable node，subscription 自動觸發。
- Data Mode + Anomaly Injection 自動生效（皆為 value-level，經由 `update_register` 反映到 node）。
- 1 個內建 OPC UA 模板 + Normal Operation profile。
- 前端 Protocol 下拉新增 OPC UA 選項。
- 整合測試、docker-compose 開 port、文件更新。

### Out of scope (future)
- Writable nodes（client 寫回）、Methods、Alarms & Conditions。
- Username/Password、憑證（Sign / SignAndEncrypt）。
- **通訊層 fault simulation**（delay / timeout / exception / intermittent）——這些在 Modbus 是靠 `trace_pdu` 攔截，asyncua 高階 API 無對等 hook。OPC UA MVP 不支援 comm fault；但 **anomaly injection 仍可用**（value-level）。
- 完整 EngineeringUnits / AnalogItemType（unit 先放進 node Description；正式 EU 與 issue #18 一起處理）。
- 每設備層級的通訊統計（request/success/error count）——asyncua 無逐請求 hook，MVP 的 `get_stats` 回傳全零，僅 `get_status` 提供 server 層級狀態。

## 3. Architecture

### 3.1 Library
新增依賴 **`asyncua`**（FreeOpcUa，async-native，Python OPC UA 事實標準）。加入 `backend/requirements.txt`。

### 3.2 Server topology
單一 `asyncua.Server`，生命週期比照 Modbus：在 FastAPI lifespan `start_all()` 啟動、`stop_all()` 關閉。設備在 `start_device` / `stop_device` 時動態 add / remove 到 address space。

```
opc.tcp://0.0.0.0:4840/ghostmeter/server/
└── Objects
    └── GhostMeter            (folder, ns=idx)
        ├── <Device A>        (Object node, DisplayName = device name)
        │   ├── voltage_l1    (Variable node, Float)
        │   ├── voltage_l2    (Variable node, Float)
        │   └── ...
        └── <Device B>
            └── ...
```

- 一個 custom namespace（`OPCUA_NAMESPACE_URI`），所有自訂 node 掛在此 namespace index 下。
- 每個 device → 一個 Object node；每個 register → 一個 Variable node（read-only，client 不可寫）。

### 3.3 New file: `backend/app/protocols/opcua_agent.py`
`class OpcUaAdapter(ProtocolAdapter)`，實作抽象方法：

| 方法 | 行為 |
|---|---|
| `start()` | `Server()` → `init()` → `set_endpoint` / `set_server_name` → `register_namespace` → `set_security_policy([NoSecurity])` → 建 `GhostMeter` folder → `server.start()`。失敗時 log warning、`_running=False`（比照 SNMP 容錯）。 |
| `stop()` | `server.stop()`，清空所有內部 dict / stats，`_running=False`。 |
| `_do_add_device(device_id, slave_id, registers)` | 建 device Object node（DisplayName 取自 `_device_meta`，fallback `f"Device_{slave_id}"`），逐一建 Variable node，建立映射 `_nodes[(device_id, address, function_code)] = node`。 |
| `_do_remove_device(device_id)` | 從 server 刪除該 device 的 Object node（含子 Variable nodes），清掉映射。 |
| `update_register(device_id, address, function_code, value, data_type, byte_order)` | 用 `(device_id, address, function_code)` 查 node，`await node.write_value(ua.Variant(value, vtype))`。查無對應 node 則 debug log 後略過。`byte_order` 忽略（OPC UA 無 word packing）。 |
| `get_status()` | `{"endpoint", "port", "running", "device_count", "node_count"}`。 |

**OPC UA 特有方法**：
- `set_device_meta(device_id: UUID, device_name: str)` — 在 `add_device` **之前**呼叫，存入 `_device_meta`，供建 Object node 時當 DisplayName。比照 MQTT 既有的 `set_device_meta` 模式。

內部狀態：
```python
self._server: Server | None
self._ns_idx: int
self._ghostmeter_folder            # parent folder node
self._device_objects: dict[UUID, Node]              # device_id → Object node
self._nodes: dict[tuple[UUID, int, int], Node]      # (device_id, address, fc) → Variable node
self._device_meta: dict[UUID, str]                  # device_id → display name
```

### 3.4 Value sync — push model
模擬引擎 `engine._run_device` 每 tick 對每個 register `await adapter.update_register(...)`（既有流程，line 314）。OPC UA adapter 把值寫進 node → asyncua subscription 自動推送給訂閱的 client。**不需動 engine**。

> 為何不用 SNMP 的 pull model：asyncua subscription 依賴 node 值「真的變動」。pull（不存 node 值、查詢時才算）會讓 subscription 失效，等於砍掉 OPC UA 核心賣點。

### 3.5 Data type mapping
| template `data_type` | OPC UA `ua.VariantType` |
|---|---|
| int16 | Int16 |
| uint16 | UInt16 |
| int32 | Int32 |
| uint32 | UInt32 |
| float32 | Float |
| float64 | Double |

建 Variable node 時用對應 VariantType 初始化（初值 0），`update_register` 寫值時帶同型別 `ua.Variant`。

### 3.6 `RegisterInfo` extension
`backend/app/protocols/base.py` 的 `RegisterInfo` dataclass 新增兩個**選用、向後相容**欄位：
```python
@dataclass
class RegisterInfo:
    address: int
    function_code: int
    data_type: str
    byte_order: str
    oid: str | None = None
    name: str | None = None   # register name → OPC UA browse/display name
    unit: str | None = None   # → OPC UA node Description（暫代 EngineeringUnits）
```
理由：OPC UA Variable node 必須在建立時就有有意義的名字，而 node 的價值正是「可瀏覽的命名 address space」。現有兩處建構 `RegisterInfo`（`device_service.start_device`、`main.py` resume）改為帶入 `name=reg.name, unit=reg.unit`。對 Modbus/SNMP 無影響（不讀這兩欄）。

> 不在本次重構 SNMP 改用 `name`（避免擴散範圍）；SNMP 維持既有 `set_register_names`。

## 4. Configuration
`backend/app/config.py` 新增（比照 SNMP 用 env，**不建 DB table**——Anonymous/None 無 runtime 設定需持久化）：
```python
OPCUA_HOST: str = "0.0.0.0"
OPCUA_PORT: int = 4840
OPCUA_ENDPOINT_PATH: str = "/ghostmeter/server/"
OPCUA_SERVER_NAME: str = "GhostMeter OPC UA Server"
OPCUA_NAMESPACE_URI: str = "http://ghostmeter.local/opcua/"
```
`.env.example` 同步補上。

## 5. Integration points

### 5.1 `main.py` lifespan
- 建 `OpcUaAdapter(host=..., port=..., ...)` → `register_adapter("opcua", adapter)`（在 `start_all()` 之前）。
- **Resume 區塊**：`RegisterInfo` 建構帶 `name` / `unit`；對 `template.protocol == "opcua"` 的設備，於 `add_device` 前呼叫 `opcua_adapter.set_device_meta(device.id, device.name)`。

### 5.2 `device_service.start_device`
- `RegisterInfo` 建構帶 `name` / `unit`。
- 在 `add_device` **之前**新增 opcua 區塊：若 `template.protocol == "opcua"`，呼叫 `opcua_adapter.set_device_meta(device.id, device.name)`（與既有 SNMP / MQTT 區塊並列的 protocol-specific 處理）。

### 5.3 `monitor_service`
MVP 不額外接 OPC UA 逐請求統計（asyncua 無 hook）。`get_status` 提供 server 層級資訊即可；如監控頁需要可後續再加。**本次不改 monitor_service**（保持範圍）。

## 6. Built-in template + profile (seed)
比照 SNMP UPS 的做法，新增一個內建 OPC UA 模板。`address` / `function_code` 為滿足 NOT NULL + unique 約束的 dummy 連號值（OPC UA 不使用，僅作 `update_register` 的 key），`oid` 為 null。

### 6.1 `backend/app/seed/opcua_energy_meter.json`
模板名 `Energy Meter (OPC UA)`，protocol `opcua`，register（float32 / function_code 3 / 連號 address）：

| name | unit | 說明 |
|---|---|---|
| voltage_l1 / l2 / l3 | V | 三相電壓 |
| current_l1 / l2 / l3 | A | 三相電流 |
| active_power_total | W | 總有功功率 |
| power_factor | – | 功率因數 |
| frequency | Hz | 頻率 |
| energy_total | kWh | 累積電能（accumulator） |

### 6.2 `backend/app/seed/profiles/opcua_energy_meter_normal.json`
`template_name = "Energy Meter (OPC UA)"`、`name = "Normal Operation"`、`is_default = true`，physically consistent：電壓 random(gaussian, base 220)、電流 daily_curve（peak 14:00）、功率 computed（V×I×PF×3）、energy accumulator、frequency random(base 50)。格式同既有 profile seed。

> Seed loader 用 `SEED_DIR.glob("*.json")`、`PROFILES_DIR.glob("*.json")` 自動載入，新增 JSON 即生效，**不需改 loader**。

## 7. Frontend
- `frontend/src/pages/Templates/TemplateForm.tsx`：Protocol 下拉新增 `{ value: "opcua", label: "OPC UA" }`。
- OPC UA 模板的 register 不需 OID 欄（`RegisterTable` 的 `isSnmp` 判斷維持原樣；OPC UA 沿用 name/data_type/address 欄即可）。
- 其餘前端沿用既有 template / device / simulation / monitor 流程，無需新頁面。

## 8. Dependencies
- `asyncua`（新增至 `requirements.txt`，釘穩定版本如 `asyncua>=1.1,<2`）。
- Docker：`docker-compose.yml` backend service 暴露 `4840:4840`。

## 9. Testing
新增 `backend/tests/test_opcua_*.py`（比照 SNMP 16 tests 的覆蓋面）：
1. **Template / seed 驗證**：內建 OPC UA 模板載入、register 數量與型別正確、is_builtin 保護、profile 連結正確。
2. **Adapter 單元 / 整合測試**（核心）：
   - `start()` 後 server 起得來；`add_device` 建出對應 node。
   - 用 `asyncua.Client` 連線 → browse 找到 device Object 與 Variable nodes。
   - `update_register` 寫值 → client `read_value` 讀回一致（含各 data_type）。
   - **Subscription**：client 訂閱某 node → `update_register` 改值 → 收到 data change 通知（驗證 push model 的核心賣點）。
   - `remove_device` 後 node 消失；`stop()` 乾淨關閉。
3. 動態 port（避免測試與本機 4840 衝突）。

驗收：`pytest` 全綠、ruff lint 乾淨、`tsc -b` 通過。

## 10. Docs to update (push 前)
- `CHANGELOG.md` — Unreleased 新增 OPC UA adapter 條目。
- `docs/development-log.md` — 本次開發日誌（決策：push model、單一 server、Anonymous/None、RegisterInfo 擴充）。
- `docs/development-phases.md` — 新增 Milestone 8.9（OPC UA Server Adapter）。
- `docs/api-reference.md` — **無新 REST endpoint**（OPC UA 不經 REST，僅靠 template `protocol=opcua`）；如需補一行說明 OPC UA 模板用法。
- `docs/database-schema.md` — **無 schema 變更**（`RegisterInfo` 是 in-memory dataclass，非 DB；`register_definitions` 既有欄位即可承載）；註明 OPC UA 模板沿用現有 table。

## 11. Risks / open items
- asyncua 版本 API 差異（`write_value` vs `set_value`、security policy 設定方式）——實作時以實測為準。
- 測試環境 port 4840 可能被占用 → 測試一律用動態 port。
- `_do_remove_device` 需確保 asyncua 正確刪除 Object 及其子 node（必要時遞迴 `delete_nodes`）。

## 12. Delivery checklist
- [ ] `asyncua` 加入 requirements
- [ ] `RegisterInfo` 擴充 name / unit
- [ ] `OpcUaAdapter` 實作
- [ ] config + .env.example
- [ ] main.py 註冊 + resume 接線
- [ ] device_service set_device_meta 接線
- [ ] 內建模板 + profile seed JSON
- [ ] 前端 Protocol 下拉選項
- [ ] docker-compose port 4840
- [ ] 整合測試（含 subscription）
- [ ] 文件更新（CHANGELOG / dev-log / phases）
