# BACnet/IP Adapter — Design Spec

- **Date**: 2026-06-10
- **Status**: Approved (VLAN router topology, no COV, no comm fault in MVP)
- **Milestone**: Phase 9 — BACnet/IP Adapter
- **Author**: Claude (brainstormed with Ken)

## 1. Goal

新增 **BACnet/IP** 作為第五個 protocol adapter（已有 Modbus TCP / MQTT / SNMP / OPC UA）。
EMS BACnet client 能以 Who-Is 探索多台虛擬設備，並用 ReadProperty / ReadPropertyMultiple
讀取即時模擬值。延續 `ProtocolAdapter` 可插拔架構，不改 DB schema。

## 2. Scope

### In scope (MVP)
- **Device discovery**：Who-Is / I-Am（含 directed Who-Is by instance range）。
- **Read**：ReadProperty、ReadPropertyMultiple（read-only，拒絕 write）。
- **VLAN router 拓撲**：單一 UDP port（47808），每個 GhostMeter device
  是獨立的 BACnet device instance，EMS 可探索到 N 台各自獨立的設備。
- Data Mode + Anomaly Injection 自動生效（value-level，經 `update_register` push）。
- **Per-device 通訊統計**：攔截每台虛擬設備 Application 的 ReadProperty /
  ReadPropertyMultiple handler，計 request / success / error / avg_response_ms
  （這點優於 OPC UA adapter——asyncua 無逐請求 hook，BACnet 我們自己控制 handler）。
- 1 個內建 BACnet 模板 + Normal Operation profile。
- 前端 Protocol 下拉新增 BACnet 選項。
- 整合測試、docker-compose 開 UDP port、文件更新。

### Out of scope (future)
- **COV 訂閱**（SubscribeCOV）——EMS 端目前以輪詢為主，COV 等有實際 client 需求再加。
- **WriteProperty**——所有 object read-only。
- **Comm-layer fault simulation**（delay / timeout / reject / intermittent）——
  同 OPC UA 首版策略。bacpypes3 的 service handler（`do_ReadPropertyRequest` 等）
  為可覆寫的 async method，攔截點明確，後續補上的可行性比 asyncua 高。
- **BBMD / Foreign Device registration**（跨子網探索）、MS/TP、Alarms & Events。

## 3. Architecture

### 3.1 Library
新增依賴 **`bacpypes3`**（joelbender，asyncio-native，純 Python，
BACnet Python 生態現役標準；舊版 bacpypes 已停止新功能開發）。
加入 `backend/requirements.txt`。

### 3.2 拓撲 — IPv4 router + VLAN

bacpypes3 內建 VLAN（virtual network）概念，官方 samples 即有
IP-to-VLAN router 範例。GhostMeter 對外是「一台 BACnet router，
後面 network N 掛多台設備」——與真實現場 MS/TP router 後掛一排電表的架構一致。

```
EMS client ──UDP 47808──> [IPv4 Router App]          ← 唯一對外 socket
                               │  (VLAN, network = BACNET_NETWORK)
                  ┌────────────┼────────────┐
            [Device A App]  [Device B App]  ...      ← 每台 = 獨立 bacpypes3 Application
             device,100001   device,100002
             ├ analog-input,0  (voltage_l1)
             ├ analog-input,1  (voltage_l2)
             └ ...
```

- `start()`：建立 IPv4 link layer + router node + VLAN。失敗時 log warning、
  `_running = False`（比照 SNMP / OPC UA 容錯，不擋整個 app 啟動）。
- `stop()`：關閉所有 device app、router、socket，清空內部 dict 與 stats。
- `_do_add_device()`：在 VLAN 上動態建立一個 device Application
  （DeviceObject + 每個 register 一個 object），廣播 I-Am。
  Device instance 衝突時 raise `ConflictException`（比照 SNMP OID conflict）。
- `_do_remove_device()`：關閉並移除該 device Application。

### 3.3 新檔案：`backend/app/protocols/bacnet_agent.py`

`class BacnetAdapter(ProtocolAdapter)`：

| 方法 | 行為 |
|---|---|
| `start()` | 建 router + VLAN，bind UDP `0.0.0.0:BACNET_PORT` |
| `stop()` | 全部關閉、清空狀態 |
| `_do_add_device()` | VLAN 上建 device app + objects，檢查 instance 衝突 |
| `_do_remove_device()` | 拆除 device app |
| `update_register()` | (device_id, address) → object → 寫 `presentValue` |
| `get_status()` | port / network / running / device 數 / object 數 |

內部狀態：
- `_device_apps: dict[UUID, Application]` — device → VLAN 上的 app
- `_objects: dict[tuple[UUID, int], AnalogInputObject]` — (device_id, address) → object
- per-device stats 走基底類別的 `_device_stats`，由覆寫的 ReadProperty handler 累計

### 3.4 編號規則（確定性推導，不需新 DB 欄位）

- **Device instance** = `BACNET_DEVICE_INSTANCE_BASE`（預設 100000）`+ slave_id`。
  BACnet instance 範圍 0–4194302，slave_id 1–247，無溢位疑慮。
- **Object instance** = register `address`。
- **objectName** = register `name`；**description** = register `description`。
- **units** = register `unit` 字串映射 BACnet engineering units：
  `V→volts, A→amperes, W→watts, kW→kilowatts, kWh→kilowatt-hours,
  Hz→hertz, %→percent, °C→degrees-celsius`。映射表外的 unit 直接省略 units 屬性。
- **Object type**：一律 **analog-input**（量測值慣例；所有 data_type 的值
  在 simulation engine 內皆為 float，BACnet presentValue 為 Real，直接相容）。
  實作第一步驗證 `bacpypes3.local` 是否提供 AnalogInputObject；
  若無則退用 AnalogValueObject（docs 已確認存在）。

### 3.5 Value sync — push model（同 OPC UA）

`update_register(device_id, address, ...)` → `_objects[(device_id, address)]` →
寫 `presentValue`。`RegisterInfo` 現有欄位（address / name / unit）已足夠，
**不需擴充 RegisterInfo、不改 DB schema**。

### 3.6 Read-only 行為

WriteProperty 回 BACnet error（writeAccessDenied）。bacpypes3 local object
預設行為若已拒絕未授權寫入則沿用，否則覆寫 handler。

## 4. Configuration

`backend/app/config.py` 新增：

| 設定 | 預設 | 說明 |
|---|---|---|
| `BACNET_PORT` | `47808` | BACnet/IP 標準 UDP port |
| `BACNET_DEVICE_INSTANCE_BASE` | `100000` | device instance = base + slave_id |
| `BACNET_NETWORK` | `100` | VLAN 虛擬網路號（1–65534） |

docker-compose：backend 服務新增 `"47808:47808/udp"`。

## 5. Integration points

### 5.1 `main.py` lifespan
```python
from app.protocols.bacnet_agent import BacnetAdapter
bacnet_adapter = BacnetAdapter(
    port=settings.BACNET_PORT,
    device_instance_base=settings.BACNET_DEVICE_INSTANCE_BASE,
    network=settings.BACNET_NETWORK,
)
protocol_manager.register_adapter("bacnet", bacnet_adapter)
```

### 5.2 `device_service`
走既有泛用路徑（`protocol_manager.add_device/remove_device`），
**不需** SNMP 式的 `set_register_names` 特殊 wiring，也不需 OPC UA 式的 fault 特例。

### 5.3 `monitor_service`
沿用既有 per-protocol stats 讀取模式（`get_stats("bacnet", device_id)`）。

## 6. Built-in template + profile (seed)

### 6.1 `backend/app/seed/bacnet_energy_meter.json`
- `"name": "Energy Meter (BACnet)"`, `"protocol": "bacnet"`
- Registers 比照 `opcua_energy_meter.json`（voltage_l1–l3, current_l1–l3,
  active_power_total, power_factor, frequency, energy_total, status），
  address 0–10 即 object instance 0–10，`oid: null`。

### 6.2 `backend/app/seed/profiles/bacnet_energy_meter_normal.json`
比照 `opcua_energy_meter_normal.json`：daily_curve / random / accumulator 組合。

## 7. Frontend

`frontend/src/pages/Templates/TemplateForm.tsx` 的 protocol options
新增 `{ value: "bacnet", label: "BACnet/IP" }`。其餘頁面以 protocol 字串
泛用顯示，無需逐頁修改（實作時驗證 Monitor / DeviceList 的 protocol badge）。

## 8. Dependencies

- `bacpypes3`（pin 實作當下最新穩定版）

## 9. Testing

`backend/tests/test_bacnet_adapter.py`，比照 SNMP / OPC UA 整合測試模式：

1. **Adapter lifecycle**：start → status running → stop。
2. **add_device / remove_device**：object 建立與拆除、device instance 衝突
   raise ConflictException。
3. **ReadProperty**：測試 client（bacpypes3 Application，loopback）讀
   presentValue / objectName / units。
4. **ReadPropertyMultiple**：一次讀多 object 多 property。
5. **update_register**：寫入後 ReadProperty 讀到新值。
6. **Discovery**：directed Who-Is（unicast 到 127.0.0.1，避免 CI 環境
   loopback broadcast 限制）收到對應 I-Am。
7. **Stats**：ReadProperty 後 request_count / success_count 遞增。

測試用非標準 port（如 47899）避免與本機其他 BACnet 程式衝突。

## 10. Docs to update (push 前)

- `CHANGELOG.md` — Unreleased: BACnet/IP adapter
- `docs/development-log.md` — 實作日誌
- `docs/development-phases.md` — Phase 9 狀態
- `README.md` — protocols 表新增 BACnet/IP + port 47808/udp
- `docs/api-reference.md` — 無新 endpoint，protocol 枚舉值說明若有列舉則補
- `docs/database-schema.md` — 無 schema 變更，跳過

## 11. Risks / open items

- **Broadcast 探索限制**：BACnet Who-Is 靠 UDP broadcast，docker bridge NAT 與
  跨子網（Tailscale 部署）收不到廣播。EMS 需與 host 同 L2，或在 client 端以
  IP:port 靜態設定（unicast ReadProperty / directed Who-Is 不受影響）。
  寫入 README 已知限制；BBMD 列 future。
- **AnalogInputObject 可用性**：`bacpypes3.local` 是否有 AnalogInputObject
  待實作第一步驗證，fallback = AnalogValueObject（§3.4）。
- **VLAN 動態增刪設備**：`add_object`/`delete_object` 已確認支援 runtime 操作；
  VLAN node 的 runtime attach/detach 以官方 router sample 為基準驗證，
  若有限制則改為「router + 預建 node pool」設計（實作時確認）。
- **I-Am 廣播時機**：add_device 時主動 I-Am 一次屬 BACnet 慣例，
  但在 bridge 網路下廣播出不去——不影響 unicast 功能，僅 best-effort。

## 12. Delivery checklist

- [ ] `bacnet_agent.py` adapter 實作
- [ ] config + main.py 註冊 + docker-compose UDP port
- [ ] seed template + profile
- [ ] frontend protocol option
- [ ] 整合測試（§9 全項）通過
- [ ] 既有測試全綠（`pytest`）
- [ ] 文件更新（§10）
