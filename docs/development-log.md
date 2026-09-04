# Development Log

## 2026-09-04 — SNMP SET 無聲丟棄（#97）與 OPC UA NodeId 浮動（#98）

### 背景

在為 EnOL 準備各 protocol 斷路器的寫入測試時，實測發現兩件事：
`snmpset` 對 GhostMeter 會 timeout 而不是收到錯誤；OPC UA 的 `breaker_command`
是 `ns=2;i=40` 這種數字 id，重啟後會變。

### 做了什麼

**#97 SNMP SET**
- 根因：`snmp_agent.py` 只註冊 Get / GetNext / GetBulk 三個 responder，沒有
  `SetCommandResponder`，pysnmp 收到 SET PDU 找不到處理者就直接丟掉不回應；
  `write_variables()` 回 `NoSuchObject` 的「拒絕」是從沒被呼叫過的死碼。
- 修法：新增 `_FaultAwareSetCommandResponder`（沿用 mixin，timeout / intermittent /
  delay 行為與 GET 一致）；`write_variables()` 對每個對得到 OID 的 varbind 呼叫
  `write_tracker.record(device_id, "Set", register.address, [value.prettyPrint()],
  register_name)`，之後 `raise smi_error.NotWritableError(idx=0)` → client 收到
  `notWritable`（errorStatus 17）。`exception` 故障下先記錄再回 `genErr`。
  新增 `_oid_addresses` 對照表提供 write-event 的 `address`；remove_device / stop 時
  清掉該裝置的 write events（與其他 adapter 一致）。
- 測試 `test_snmp_write_detection.py`（7）：真的透過 UDP 送 SET — notWritable 且有紀錄、
  字串值以文字記錄、未知 OID notWritable 且不記錄、SET 後 GET 值不變、timeout 故障下
  無回應也無紀錄（PDU 在到 MIB controller 前就被丟）、exception 故障回 genErr 仍記錄、
  remove_device 清事件。

**#98 OPC UA NodeId**
- 根因：`add_object(ns_idx, name)` / `add_variable(ns_idx, name, …)` 只給 namespace
  index，asyncua 用每個 namespace 一個遞增計數器配 `i=N`；resume 查詢沒有 ORDER BY、
  運行中任何 add/remove 都會讓後續 node 位移。
- 修法：`device_object_nodeid()` → `ns=<idx>;s=<slave_id>`、`register_nodeid()` →
  `ns=<idx>;s=<slave_id>.<register_name>`，browse name 以 `ua.QualifiedName(name, ns)`
  維持原樣。slave_id 在同 protocol port 內唯一，裝置名稱可改可重複所以不拿來當鍵。
- 測試（`test_opcua_adapter.py` 新增 3）：id 等於預期字串且 client 可用
  `ns=2;s=10.voltage_l1` 直接讀值、remove 後倒序重加與 server 重啟後 id 完全相同、
  remove 後同 slave_id 可再加（string id 已釋放）。

### 決策

- SNMP SET 回 `notWritable` 而不是像 Modbus / BACnet 一樣「假裝成功」：SNMP 的
  read-only 物件本來就該這樣回；EnOL 端會看到明確錯誤而不是 timeout。
- OPC UA 用 slave_id 而非裝置名稱當 NodeId 鍵，接受一次性的 breaking change；
  CHANGELOG / api-reference 已標示，部署後 EnOL 的 OPC UA 點位 NodeId 要換一次。
- 記錄 SNMP 值用 `prettyPrint()`，Gauge32 等數值得到純數字字串，OctetString 得到文字。

### 驗證

- `ruff` clean；SNMP + OPC UA 相關套件 80 passed（含新測試 10）；完整後端套件 **504 passed**（host venv vs `ghostmeter_test`）。
- 實機（本機 docker 以本分支 rebuild）：`snmpset` 對 ACB-SNMP-01 的 breaker_command 回
  `Reason: notWritable (That object does not support modification)`，之後 `snmpget` 仍是引擎值 0，
  write-events 出現 `('Set', 1, ['2'], 'breaker_command')`；未知 OID 同樣 notWritable 且不記錄。
  OPC UA `ns=2;s=10.breaker_command` / `ns=2;s=10` 直接解析成功、三台 OPCUA-TEST 以
  `ns=2;s=<slave>.voltage_l1` 讀值正常、client write 仍被記錄；兩台裝置停止後倒序啟動 id 不變。

## 2026-09-04 — Aggregate 資料模式：跨裝置 register 聚合（issue #95）

### 做了什麼

新增 `data_mode = "aggregate"`，讓總表的 register 結構性地等於分表的聚合，
取代先前 MVCB / PM-01..09 靠「參數對齊」的暫解：

- **`app/simulation/aggregate.py`（新）**：`DeviceDirectory`（名稱 / UUID →
  device id 解析，重名回 ambiguous）、`find_cycle`（DFS 三色標記，回傳環路徑）、
  DB loader（全裝置目錄、所有 enabled aggregate config 的相依圖）。API 層與
  engine 共用。
- **`data_generator.py`**：`GeneratorContext` 多兩個唯讀 view
  `peer_values`（運行中裝置的即時值）與 `peer_last_known`（停止 / 重啟前的最後值），
  `_generate_aggregate` 實作 `sum / avg / weighted_avg / max / min` 與
  `on_missing = last_known / zero / skip`。
- **`engine.py`**：啟動時把 `sources` 解析成 UUID、`register` 補預設同名，
  然後對全系統相依圖做環偵測（有環丟 `AggregateCycleError`）；新增
  `_last_known_values` 快取（`stop_device` 與 crash-restart 前快照）；
  排序改成 `(aggregate 優先, sort_order)`，讓總表自己的 `computed`
  （如 `total_power = Σ power_lx`）可以依賴 aggregate 結果。
- **`schemas/simulation.py`**：`VALID_DATA_MODES` 加 `aggregate`；
  `model_validator` 擋結構錯誤（op 白名單、sources 非空 / 無重複 / 字串、
  `weighted_avg` 必帶 `weight_register`、其他 op 不可帶、`on_missing` 白名單）並補預設值。
- **`services/simulation_service.py`**：`_validate_aggregate_configs` 查 DB 驗證
  來源存在且唯一、非自己、來源 template 真的有該 register（與 weight_register）、
  以及跨裝置環偵測（PUT 整組取代 / PATCH 單筆 upsert 兩種語意都處理）。
- **`services/device_service.py`**：`register_device_runtime` 對
  `AggregateCycleError` 不再吞掉（設定錯不是暫時性故障），
  `POST /start` 回 409 並把裝置設 `error`，不會出現「running 但沒模擬」。
- **Frontend**：`DataMode` union 加 `aggregate`；`utils/aggregateParams.ts`
  （parse / serialize / 來源選項；重名裝置改用 id）+ 10 個 vitest；
  `AggregateParamsEditor` 在 Simulation 的 Data Mode tab 取代 raw JSON textarea
  （來源多選、op、register、weight_register、on_missing + 用法提示）。

### 決策

- **`sources` 接受「裝置名稱」或 UUID，且照原樣儲存**：system export /
  import 本來就用 `device_name` 識別裝置，手寫 API / 匯入檔用名稱才能跨環境搬。重名時 422 要求改用 id。
  **前端一律送 UUID**（Ken 的決定，2026-09-04）：改名或重名不會改變已存設定的指向；
  編輯器載入時把既有設定裡的名稱對應成 id，對不到的照原樣顯示成 tag 讓後端在存檔時回報。
- **Engine 啟動時解析不到的來源只 warning、不擋啟動**：分表被刪或改名不該讓總表
  在 backend 重啟後 resume 失敗；API 存檔時的 422 才是主要防線。
- **`on_missing` 預設 `last_known`**（issue 建議）：停一顆分表總表不會瞬間掉 1/N。
  `zero` 會算進 `avg` 分母；`skip` 完全排除；全部缺值回 0.0。
- **`weighted_avg` 權重總和為 0 時退化為算術平均**（例如全部分表功率 0 時 PF 仍有意義）。
- 環偵測在 API 與 engine 各做一次：API 是使用者看得到的錯誤，engine 是 import /
  profile 直寫 DB 繞過 API 時的最後防線。
- 不驗證 `sources` 的 template 與總表相同（issue 邊界 4）：只比對 register 名稱存在。
- 沿用 tick 不同步的行為（各裝置獨立 task），只在文件說明滯後 ≤ 1 個 update interval。

### 驗證

- 後端：`ruff` clean；`test_aggregate.py`（13）、`test_data_generator.py` aggregate（12）、
  `test_simulation_engine.py` aggregate（6，無 DB / 無網路，fake adapter）、
  `test_simulation_api.py` aggregate（11）；相關套件 76 passed；完整後端套件 **494 passed**（475 + BACnet adapter 19）（host venv vs `ghostmeter_test`）。
- 前端：`tsc -b` / `eslint .` clean；vitest 48 passed，coverage 高於 ratchet 門檻。
  本機 rebuild 後用 Playwright 開 Simulation → MVCB2：13 列 aggregate 各顯示 10 個來源 tag（名稱 + 模板），
  Save All 後 DB 內 130 個 sources 全為 UUID、MVCB2 維持 running、Modbus 實讀誤差 0.0000%。
- **E2E（host backend 8001 + Modbus 5020、獨立 DB `ghostmeter_e2e`，pymodbus client 實讀）**：
  3 顆分表 + MVCB（sum energy/power、avg voltage、weighted_avg PF by total_power）
  誤差 0.00000%；停 PM-02 時總表維持 last-known 不掉；PM-02 重啟後誤差 0.00006%
  （一個 tick 的滯後）；新增 PM-04 到 sources 後總表自動變大、誤差 0.00000%；
  PM-01 → MVCB → PM-01 環回 422 `Aggregate dependency cycle: PM-01 → MVCB → PM-01`；
  來源打錯字回 422 且被拒的裝置維持 running。

### 部署注意

需 rebuild `ghostmeter-backend` image；與 enol-next 共用 `docker_default` 網段，
rebuild 後容器 IP 可能變動，不要與 enol-next 同時 rebuild，並確認 enol-next 的 Modbus IP。

## 2026-08-24 — 部署文件：環境搬移（Migration）章節

### 做了什麼

`docs/deployment.md` 新增第 7 節「搬移到另一個環境」，涵蓋從本機或 Linode
把整套系統移到新環境的完整流程：

- 釐清資料邊界：唯一需要搬的狀態是 PostgreSQL（`pgdata` volume）；
  程式碼在 GitHub、`.env` 是 git-ignored 要手動帶走、write events 只在
  in-memory ring buffer 不需搬。
- 匯出用 `docker exec ghostmeter-postgres pg_dump -Fc`（直接對容器，
  不受 host port 映射影響）；還原用 `pg_restore --clean --if-exists`。
- **restore 先於 deploy.sh** 的順序約束：dump 帶著 `alembic_version`，
  先還原再跑 migration 只會補跑更新的 revision，app 啟動 seed 檢查
  也會發現內建模板已存在而跳過，不會重複塞資料。
- 版本約束：新環境 checkout 的 code 版本須 ≥ 來源（舊 code 配新 dump 會壞）。
- 搬移後檢查清單：Tailscale 新 node IP（`BIND_IP` 更新 + node sharing
  重新分享 + EMS 端改連線 IP）、Cloudflare Tunnel token 綁 tunnel 不綁
  機器可直接沿用（舊機器要停）、外部 MQTT broker 的來源 IP 限制。

### 決策

- 推薦 `pg_dump` 而非 tar 整個 `pgdata` volume：不用停來源 postgres、
  無 volume 權限問題、輸出乾淨（兩者都可行，PG 16 對 PG 16）。
- 純文件變更，無程式碼異動。

### 做了什麼

依 Delta DPM-C520/C530 的 register map（使用者提供的點表截圖）新增內建模板
`dpm_c530_meter.json` 與預設 profile `dpm_c530_meter_normal.json`：

- **32 個 register**，全部 float32 / Holding Register（FC03），位址照點表
  0x100 區塊（十進位 256–352）：三相＋平均相電壓、三個線電壓＋平均、
  三相＋平均電流、三相＋總 PF、頻率、三相＋總 kW/kVAR/kVA、
  累積 kWh/kVAh/kVARh。
- **Normal Operation profile**（is_default）走物理一致性設計，比照 SDM630：
  - 相電壓 gaussian ~220V；線電壓 computed `(Va+Vb)×0.866`（≈ √3×平均），
    平均值全部 computed
  - 電流 daily_curve（base 40/38/42、14:00 尖峰，三相刻意微幅不平衡）
  - kW = V×I×PF/1000、kVA = V×I/1000、總量為三相相加
  - kVAR 用 `VA × 0.392` 近似（PF 0.92 時 sin(acos(0.92))≈0.392）——
    expression parser 只支援 + - * /，沒有 `**` 可開根號，屬刻意近似
  - 累積電量 accumulator，increment 依平均功率換算（24.3 kW → 0.00675 kWh/s）

### 決策

- 點表的 Start Address 十進位值（256 = 0x100）直接當 0-based protocol
  address 使用，與其他內建模板一致。
- byte_order 用預設 `big_endian`（點表未載明 word order；模擬器兩端一致即可，
  若實際 collector 解出亂數再調）。
- 每個 builtin template 必須有 default profile（`test_seed_profiles` 強制），
  所以 profile 跟模板同 PR 一起進。

### 驗證

- `test_seed.py` builtin 數量 6 → 7 並斷言新模板名稱。
- 加寫一次性 sanity script 驗證：schema 過 `TemplateCreate`、register
  位址無重疊（float32 佔 2 registers）、profile 的 register_name 與模板
  一一對應、所有 computed expression 依序可求值（p_w≈24.3 kW、
  p_va≈26.4、p_var≈10.3、線電壓≈381V，數值合理）。
- 全套 backend pytest 452 passed。

## 2026-07-20 — MQTT broker 斷線自動重連

### 背景（線上事故）

Linode 上兩個 MQTT broker（.49 正式 EnOL VM、.125 Mac 測試 EMQX）的發布同時
掛掉 7+ 小時：每 5 秒噴 `[code:4] The client is not currently connected`，但
API `/system/mqtt/brokers` 卻回報 `connected: true`。追查證據鏈：

- 兩個 broker 是**各自獨立**斷線（.49 連上後 3 分鐘、.125 連上後 1.4 小時），
  斷線後永遠不恢復；容器內到 port 1883 的 established TCP 連線為 0 條
- 兩個 broker 從 Linode 都 TCP 可達 → 網路沒問題，缺的是重連

### 根因

aiomqtt 沒有內建自動重連（設計上連線生命週期 = context manager 範圍），而
adapter 的 `connected` flag 只在 `connect_broker()` 成功時設 True，斷線後既
不偵測也不重連 —— publish loop 在死掉的 client 上每 5 秒失敗一次直到重啟。
追 git history 確認這是 multi-broker 之前就存在的設計缺陷（舊版 `reconnect()`
只在改設定時觸發），不是 PR #88 regression；以前 broker 穩定沒暴露，broker
搬到會睡眠的 Mac 與遠端 VM 後天天踩。

### 修法

連線生命週期補齊，不動 publish task 結構 / fault sim / REST API：

1. **斷線偵測**：`_publish_one` 捕捉 `aiomqtt.MqttError` → `_mark_broker_disconnected()`
   把 flag 翻 False（API 狀態變誠實；publish loop 走既有 guard 跳過發送，
   error log 洪水自動停止）並排程重連。
2. **自動重連**：每個 broker 一個 `_reconnect_loop` task，exponential backoff
   1s → 60s cap，成功後 flag 復 True，publish loop 下一輪自動恢復發布。
   `connect_broker` 失敗（啟動時 broker 就掛）也走同一機制。
3. **生命週期**：`disconnect_broker` / `reconnect_broker`（手動改設定）/ `stop()`
   都會先取消 pending 的重連 task；broker 被移除時重連 loop 自行終止。
   `connect_broker` 現在把 settings 存進 `_broker_settings` 供重連使用。

TDD：先寫 5 個失敗測試（斷線標記、backoff 重試到成功、重複標記不疊 task、
disconnect 取消重連、啟動失敗排程重連）再實作。全套 452 tests 通過。

### 順手修

`test_health_returns_200` 寫死 `version == "0.1.0"`（0.4.x 起就過期，dev 上
本來就 fail），改為對照 `get_settings().APP_VERSION`。

## 2026-07-18 — Multi-broker MQTT publishing（issue #87）

### 背景

2026-07-18 把 Linode GhostMeter 的 MQTT 發布從測試 broker（.125）切到 EnOL 正式
broker（.49）時，`MqttBrokerSettings` 是全域單一設定，兩台裝置只能一起切，原本
接 .125 的 pipeline 直接斷線。Issue #87 記錄了完整的架構調查；這次實作把 MQTT
層全面改成 multi-broker：多筆命名 broker + 裝置 × broker 獨立 publish config。

### 設計決策（已與 Ken 確認）

1. **Adapter 架構**：單一 `MqttAdapter` 內部管理 `dict[broker_id, aiomqtt.Client]`，
   publish task 以 `(device_id, broker_id)` 為 key。`ProtocolManager` 完全不動，
   改動範圍最小。順手修掉舊 bug：以前 `reconnect()` 會取消**所有**裝置的
   publish task，現在 reconnect/斷線都只影響該 broker 自己的 task。
2. **API clean break**：舊的 `GET/PUT /system/mqtt` 直接移除（只有自家前端在用，
   前後端同 PR 一起改），換成 `/system/mqtt/brokers` CRUD。per-device 端點改為
   `PUT/DELETE /devices/{id}/mqtt/{broker_id}`，start/stop 帶 optional
   `broker_id`（不帶 = 全部；部分失敗只回滾該 pair 的 enabled）。
3. **範圍**：後端 + 前端一起做。Settings 頁變 broker 表格（新增/編輯/測試/刪除
   + 連線狀態），裝置頁變 per-broker config 列表，各自獨立 start/stop。

### 實作重點

- **Migration `3830d1a0ba1c`**：`mqtt_broker_settings` 加 unique `name`（現有
  單筆 → `'default'`）；`mqtt_publish_configs` 拿掉 `device_id` unique、加
  `broker_id` FK backfill 到現有 broker，換成 `UNIQUE (device_id, broker_id)`。
  已在本機含資料的 dev DB 驗證 upgrade → downgrade → upgrade 可逆。升級後部署
  環境行為不變（既有 config 全掛在 default broker 上）。
- **刪除保護**：broker 還有 config 引用時回 `409 BROKER_IN_USE`（顯式優於
  cascade surprise）；duplicate name 回 `409 DUPLICATE_NAME`。計畫原寫 400，
  改用專案既有的 `ConflictException`（409）慣例。
- **Export/import**：改為 `mqtt_brokers` 列表，config 以 `broker_name` 參照
  （name 而非 UUID，跨機器 import 才能對上）；舊格式（單一
  `mqtt_broker_settings`）仍可 import，落地為 `default` broker。
  `ImportResult.mqtt_broker_settings_set` → `mqtt_brokers_set`。
- **裝置生命週期**：device start 逐一啟動所有 enabled config（單一 pair 失敗
  log-and-continue）；device list 的 `mqtt_publishing` 從 1:1 join 改成 EXISTS
  subquery（多 config 不會重複列裝置）。

### 驗證

- 後端 447 tests 全綠（`test_health` 需 CI 的 `APP_VERSION=0.1.0` env，本機差異
  與本次無關）；前端 tsc/eslint/vitest 36 tests/build 全綠。
- End-to-end 冒煙（本機 backend + 真 EMQX + 獨立 aiomqtt subscriber）：
  broker A（可連）+ broker B（不通 port）→ start all 部分成功、B 的 enabled
  正確回滾；A 每秒實際發布（subscriber 收到）；把 B 更新成可連 → 只有 B
  reconnect，期間 A 的訊息流不中斷（15 → 18 持續遞增）；單獨 start B 後兩個
  topic 同時進訊息；刪除有 config 的 broker 正確回 409。

## 2026-07-17 — 各協定獨立 slave_id 上限（Modbus/BACnet 247，SNMP/OPC UA/MQTT 不設上限）

### 背景

跟 Ken 討論「GhostMeter 一台能建幾台裝置」時發現一個非預期耦合：`DeviceCreate`/
`DeviceBatchCreate`/`DeviceUpdate` 的 `port` 欄位 default 一律是 `502`，前端
Create Modal 也從來不讓使用者填 port。結果 5 種協定（Modbus/SNMP/OPC UA/
BACnet/MQTT）建立裝置時，`DeviceInstance.port` 全部存成同一個值 `502`，而
`(slave_id, port)` 又是全系統共用的 DB unique constraint（`device_service.py`
的 `_check_slave_id_available`）——即使 SNMP 實際監聽的是 10161、OPC UA 是
4840，跟 Modbus 的 502 毫無關係。

實際後果：`slave_id` 的 1-247 schema validator（原本只是為了符合 Modbus unit
identifier 是 1-byte 欄位的協定限制）被無差別套用到全部協定，且因為 port 全部
共用 502，5 種協定其實是在搶同一個「最多 247」的名額池，而不是各自獨立 247。

### 根因與設計判斷

- **真限制（協定規格本身要求）**：Modbus unit identifier、BACnet 的 VLAN MAC
  都是 1-byte 欄位，1-247 是物理上限，改不掉。
- **假限制（純粹是程式耦合造成）**：SNMP 用 OID 當 key、OPC UA 用 node、MQTT
  用 topic 字串，`slave_id` 在這三個協定裡只是顯示用途的標籤，本來就不需要
  1-247 這個上限；會被卡住純粹是因為 schema validator 跟 `(slave_id, port)`
  constraint 沒有分協定處理。

修法是把 `port` 從「使用者可填的欄位」改成「後端依 `template.protocol` 推導」
（`device_service._resolve_port`），讓每個協定各自拿到自己的 `(slave_id, port)`
命名空間；`slave_id` 的上限檢查則搬到 service 層（`_validate_slave_id_ceiling`），
因為只有拿到 `template.protocol` 之後才知道該套用哪個協定的規則。Modbus/
BACnet 保留 247 上限，SNMP/OPC UA/MQTT 不設上限（純受記憶體/event loop
throughput 限制，非程式碼寫死）。MQTT 沒有真正的監聽 port（devices 是主動
publish 到 broker），給了一個 nominal 值 `1883`（`MQTT_NOMINAL_PORT`）純粹用
來讓它跟其他協定分開命名空間，不代表 broker 的真實 port（那是
`MqttBrokerSettings` 管的）。

### 範圍決策

跟 Ken 確認過，這次**只改後端**：前端 Create/Edit Modal 的 Slave ID 輸入框
仍然寫死 `max={247}`（`EditDeviceModal.tsx`），且 `DeviceSummary` 沒有回傳
`protocol` 欄位可供前端判斷。也就是說 SNMP/OPC UA/MQTT 裝置理論上限已經解除，
但透過現有 UI 仍然建不到 248 台以上——要用的話得直接呼叫 API。`EditDeviceModal`
的 Port 輸入框現在送出的值會被後端忽略（server 一律重新推導），這是刻意保留
前端不動的已知副作用，不是遺漏。

### 做法（TDD）

- 先在 `tests/test_devices.py` 加 8 個測試（BACnet 上限阻擋、SNMP/OPC UA/MQTT
  超過 247 允許、跨協定同 slave_id 共存、`port` 回傳值符合協定、batch 版本的
  上限/放寬），確認全部因現有行為而失敗（RED，6 fail / 2 pass——BACnet 阻擋
  的 2 個因為舊 validator 本來就會擋 248 而先過）。
- `schemas/device.py`：拿掉 `port` 欄位，`slave_id` validator 只留下界
  （`>= 1`），上界判斷移到 service 層。
- `services/device_service.py`：新增 `_PROTOCOL_SLAVE_ID_MAX`（只有
  `modbus_tcp`/`bacnet` 有值）、`_resolve_port()`、`_validate_slave_id_ceiling()`；
  `create_device`/`batch_create_devices`/`update_device` 都先取得
  `template.protocol` 再驗證上限、推導 port（`update_device` 原本沒有 fetch
  template，這次補上）。
- `config.py`：新增 `MQTT_NOMINAL_PORT = 1883`，附註說明用途。

### 驗證

- `tests/test_devices.py` 34 passed（8 新增全綠）。
- 全套 backend `pytest`：423 passed, 1 failed——失敗是既有無關的
  `test_health.py::test_health_returns_200`（硬編版本字串 `0.1.0` vs 目前
  `0.4.3`，跟這次改動無關，未修）。
- `ruff check` 通過（`schemas/device.py`、`services/device_service.py`、
  `config.py`）。
- 全部既有測試中原本明確傳 `port`（`test_opcua_fault.py` 傳 `port: 4840`、
  `test_system_export_import.py`/`test_batch_device_ops.py` 傳 `port: 502`）
  的案例，剛好都跟新的 server-derived 值一致，零改動零破壞。

### 已知後續（未做，等 Ken 要用時再說）

- 前端 Slave ID 上限/協定顯示未同步，若要在 UI 上真的建立 248+ 台 SNMP/OPC
  UA/MQTT 裝置需要另外處理（`DeviceSummary` 加 `protocol`、Modal 動態調整
  `max`）。
- `EditDeviceModal` 的 Port 欄位變成無效輸入（送出會被忽略），沒有拿掉或加
  提示——維持現狀是本次明確決定，非疏漏。

## 2026-07-17 — MQTT 設定即時生效 + publish topic meta 修復（#81、#82）

### 背景

把 Linode GhostMeter 的 MQTT 發布接到 EnOL 的 EMQX broker 時，實地踩到兩個 bug：

1. **#81**：`PUT /api/v1/system/mqtt` 只把 broker 設定寫進 DB，跑著的
   `MqttAdapter` 完全不知情——`MqttAdapter.reconnect()` 從 PR 實作以來就是
   dead code，沒有任何呼叫點。改完設定必須重啟 backend 才生效（實測就是靠
   `docker compose restart backend` 繞過的）。
2. **#82**：`POST /api/v1/system/devices/{id}/mqtt/start` 呼叫
   `start_publishing()` 前沒有先 `set_device_meta()`，publish loop 渲染 topic
   template 時 meta 缺失、fallback 成 `unknown`——實測訊息全部發到
   `gm/unknown`（EMQX topic metrics 證實），batch payload 的 `device` 欄位是
   裸 UUID。唯一會正確設 meta 的路徑是 `device_service.start_device()` 的
   auto-start（設備啟動時已有 enabled config），所以 UI 上「對運行中設備開啟
   publishing」這條主要流程是壞的，workaround 是 stop/start 設備一次。

### 做法（TDD：先寫 5 個失敗測試，再實作）

- `mqtt_service.get_device_meta()`：join device + template 撈 topic 渲染需要的
  (name, slave_id, template_name)；`mqtt/start` 路由在 `start_publishing()` 前
  先 `set_device_meta()`。
- `PUT /system/mqtt` 存檔後對 adapter 呼叫 `reconnect()`（用 service 回傳的
  ORM 物件取「解析後」的密碼——request 可能帶 masked `****`，不能直接用）。
- `reconnect()` 會取消所有 publish task，所以新增
  `mqtt_service.resume_enabled_publishing()`：重連成功後把 enabled config ×
  running device 的 publish task 全部帶 meta 重啟。adapter 未註冊（啟動失敗）
  時設定照存，行為與舊版一致。
- 測試用 `FakeMqttAdapter`（錄呼叫順序）替換 protocol_manager 裡的 mqtt
  adapter，驗證 meta 先於 start_publishing、masked 密碼解析、reconnect 後
  resume、無 adapter 時仍可存檔。

### 追加：#84 startup resume 不恢復 publishing（同日第二個 PR）

部署 #83 時發現第三個 gap：`main.py` lifespan 的 startup resume 只重建設備
runtime，不會恢復 MQTT publish task——config 還是 `enabled=true` 但 loop 已死，
每次重啟/部署 backend 發布就默默斷掉。修法：把 resume 區塊從 lifespan 抽成
`device_service.resume_running_devices()`（可測），結尾呼叫 #83 新增的
`resume_enabled_publishing()`。TDD 兩個測試：running+enabled 會恢復（meta 先於
start_publishing）、stopped+enabled 不會。

### 驗證

- `tests/test_mqtt.py` 27 passed（22 既有 + 5 新增）；#84 後 29 passed；全套
  backend 417 passed。
- `test_health.py::test_health_returns_200` 本機失敗為既有環境問題（測試硬編
  version `0.1.0`，CI 用 workflow env `APP_VERSION: 0.1.0` 釘住，本機無 `.env`
  吃到預設 `0.4.3`）——與本次修改無關，未動。

## 2026-07-04 — Frontend vitest 測試骨架 + CI gate（#62）

### 背景

前端從 Phase 1 至今零測試——`frontend/src` 只有 `npm run build`/`tsc -b` 把關型別，
邏輯層（utils/services/stores/hooks）沒有任何自動化驗證，迴歸只能靠手動點測。CI
`frontend` job 也只跑 typecheck + build，eslint 早在 #63 修乾淨後從沒被 CI 強制執行過。

### 做法

- **測試框架：vitest + jsdom + Testing Library**，不是 Jest——專案已用 Vite 建置
  （`vite build`），vitest 直接吃同一份 `vite.config.ts`/esbuild pipeline，不需要額外
  的 babel/ts-jest 轉譯層，設定成本最低。`jsdom` 提供 DOM 環境給 `useWebSocket` 這類
  依賴 `WebSocket`/`window` 的 hook 測試。
- **範圍限定在 pure-logic 目錄**：`vite.config.ts` 的 `test.coverage.include` 只收
  `src/utils/**`、`src/stores/**`、`src/services/**`、`src/hooks/**`，不含
  `src/pages`、`src/components`——components/pages 需要更重的渲染 + antd mock 成本，
  這次先把邏輯層的安全網建起來，UI 層測試留給後續（見下方 deferred）。
- **36 個測試**：涵蓋 utils（純函式）、services（axios API 封裝，`api.test.ts` 用
  `unknown` cast 存取 axios 內部型別，刻意不用 `any` 以通過 lint gate）、stores
  （zustand store 的 action/selector 行為）、`useWebSocket` hook（連線/重連生命週期）。
- **Ratchet coverage threshold**：實測 baseline 為 statements 24.84 / branches 42.04 /
  functions 20.67 / lines 24.45（`npm run test:coverage` 對上述 4 個目錄的覆蓋率）。
  門檻鎖在略低於實測值的 **20/40/20/20**——ratchet 用意是「不能倒退」而非要求滿分，
  之後每加一批測試，門檻可以跟著提高，但這次先用保守值避免一有小改動就紅。
- **CI 新增兩道 gate**：`.github/workflows/ci.yml` 的 `frontend` job 在 `npm ci` 之後
  依序插入 `Lint`（`npm run lint`）與（typecheck 之後的）`Test with coverage`
  （`npm run test:coverage`），順序為 lint → typecheck → test → build，四步驟皆為
  CI 必要條件（non-zero exit 會讓 job 失敗）。backend job 未變動。

### 已知限制 / Deferred（追蹤於 #62）

- Components/pages 測試（antd 元件渲染、頁面互動）本次不做，覆蓋率門檻刻意只鎖
  pure-logic 目錄。
- Playwright e2e（`frontend/e2e/`，`test:e2e` script 已存在）目前不在 CI 跑，仍是
  本機手動執行；CI 整合留待後續 issue。

## 2026-06-25 — OPC UA 寫入偵測（#72）

### 設計

- **accept + 保留到下一 tick**（read-back friendly）：OPC UA client 常 read-back/subscribe
  驗證，所以不像 Modbus/BACnet 的 strict accept-and-ignore——node 設 `set_writable(True)`、
  寫入實際套用、下一 sim tick 才覆蓋。
- **機制**：`subscribe_server_callback(CallbackType.PreWrite, ...)`（與既有 PreRead fault
  hook 同一套）。`InternalSession.write` 先 dispatch PreWrite 再套用。callback 從
  `event.request_params.NodesToWrite` 取值（`wv.Value.Value.Value`）。
- **只記 external（網路 client）寫入**：`event.is_external` 過濾——PostWrite/PreWrite 對
  「所有」寫入觸發，包括 `update_register()` 每個 tick 的內部 `node.write_value()`；不過濾
  的話每個 tick 都被記成 client 寫入。（review 確認 internal session external=False。）
- **型別 coercion**：asyncua 嚴格型別檢查，loose client 寫 Double 到 Float node 會
  BadTypeMismatch。PreWrite in-place coerce 到 node 型別讓寫入成功。
- **記錄忠實性**（review REQUEST-CHANGES 修正）：原本在 PostWrite 取「coerce 後」的值記錄，
  導致 Double 55.9 寫 Int16 被記成 "55"——誤報 client 意圖。改成單一 PreWrite callback
  **先記 client 原值、再 coerce 套用**。值的審計忠實，套用值仍 read-back friendly。

### 驗證

- 4 個整合測試（真 asyncua client）：寫入記錄+套用、clear-on-remove、internal 更新不記錄
  （is_external）、記錄值是 client 原值非 coerced 值。+ 13 OPC UA fault regression。全 17 passed。

### 已知限制（#72 follow-up，已與 Ken 確認記錄為限制）

- OPC UA 寫入未 fault-gating（faulted 設備仍接受寫入，但 attempt 仍記錄）。
- 更糟：client 寫入 faulted node 會清掉該 node 的 fault value-callback（asyncua 寫入時
  重設），update_register 不重掛 → 該 node 的 fault 被悄悄停用直到 re-apply。邊緣情境
  （測試時同時寫入又注入 fault）。正解需 gate faulted 寫入或寫後重掛，另案設計。

## 2026-06-25 — BACnet 寫入偵測 + 寫入事件模型一般化（#72）

### 背景

#71 為 Modbus 做了寫入偵測，但它的 `write_tracker` 資料模型其實是 Modbus 形狀的
（`function_code: int`、`values: list[int]`）。接 BACnet 時暴露出來：BACnet 沒有
function code（是 WriteProperty），寫的是 **float** present-value 不是 16-bit words。
所以這次先把模型一般化，再接 BACnet。

### 做法

- **模型一般化**：`WriteEvent.function_code: int` → `operation: str`（人類標籤）、
  `values: list[int]` → `list[str]`（字串化，統一容納 Modbus int 與 BACnet float）。
  Modbus 的 FC→label 對應從前端搬進 Modbus adapter（`_MODBUS_WRITE_OPS`），前端 drawer
  直接顯示 `operation`、移除 `FC_LABELS`。同步更新 #71 的 4 份測試斷言。
- **BACnet 記錄 + accept-and-ignore**：`bacnet_agent.py` 的
  `do_WritePropertyRequest` 原本直接 `raise writeAccessDenied`，改成「取 obj +
  `apdu.propertyValue.cast_out(property_type, ...)` 解出值 → `write_tracker.record(
  device_id, "WriteProperty", instance, [str(value)], obj.objectName)` → 回
  `SimpleAckPDU`」，**不呼叫 `obj.write_property`**（值不持久化，sim engine 仍擁有值）。
  `object instance == register address`、`obj.objectName` 即 register name。記錄包
  try/except，絕不影響 ack。`stop()` / `_do_remove_device` 加 `write_tracker.clear`。
- **行為變更**：BACnet 寫入從「拒絕」變「接受」。既有 `test_write_property_rejected`
  記錄的是舊行為，改名 `test_write_property_accepted_but_not_persisted`，斷言寫入被
  ack 且 sim 值不被覆蓋（client 寫 999 後仍維持 220）。

### 驗證

- 後端：BACnet 整合測試（真 bacpypes3 client write → 斷言 operation/address/value/name
  + 回成功、clear-on-remove）2 passed；BACnet regression 30/30；#71 既有測試（改成
  operation/string）18 passed。ruff clean。
- 前端：tsc + eslint + build 全乾淨。

### 待辦

- #72 續：OPC UA（read-back/subscription 前提要重新 brainstorm）、SNMP（SET，最低優先）、
  MQTT（command topic 需獨立設計 topic/payload）。共用 ring buffer + API + UI 已就位。

## 2026-06-22 — Modbus 寫入偵測（#71）

### 問題

GhostMeter 是唯讀模擬器，EMS 開發者無法驗證自家系統「確實發出了正確的 Modbus 寫入」
（寫 setpoint 等）。寫入 holding register（FC06/16）被 pymodbus 默默接受、下一 tick 被覆蓋，
且完全沒有任何記錄（log / API / WS / UI 都看不到）。

### 設計決策

- **accept-and-ignore + record**：接受寫入（client 收到成功回應），但不持久化寫入值
  （模擬引擎下一 tick 照常覆蓋）。前提已確認 EMS 不做 write-then-read-back 驗證。
  核心價值在「偵測 + 記錄」，讓使用者驗證 EMS 行為。
- **記錄層**：仿 `fault_simulator` 做 `write_tracker` singleton — per-device
  `deque(maxlen=50)` ring buffer + unread 計數，純 in-memory（device stop / server
  restart 即清空），protocol-agnostic 以便 #72 重用。
- **攔截點**：`modbus_tcp.py` 的 `trace_pdu` incoming 分支（與 fault 同一 hook，跑在
  asyncio loop 上、無跨 thread）。FC6/16 從 `pdu.registers` 取值、FC5/15 從 `pdu.bits`
  取值（pymodbus 3.12.1 實測屬性名）。記錄包 try/except，**絕不影響 Modbus 回應**；
  fault 抑制（timeout）的寫入也照記，因為使用者要驗證的是 client 是否發出寫入。
- **投遞**：摘要（unread + latest）搭現有 1Hz monitor snapshot 推前端（不另開 WS channel）。
- **REST 走乾淨語意**：`GET /write-events` 純讀不改狀態；另開 `POST /write-events/ack`
  歸零 unread（UI 開抽屜時呼叫）。捨棄「GET 帶 side effect」的捷徑。
- **UI**：DeviceCard 上 antd `<Tag>` badge（unread>0 金色、已讀過仍可點開灰色），
  點開 `WriteEventsDrawer` 拉清單；drawer 在 portal 內，外層 stopPropagation 避免觸發
  卡片導航。

### 驗證

- 後端：write_tracker 單元測試（ring buffer / unread / mark_read / clear）；
  modbus client 實寫整合測試（FC06/FC16/FC05 coil / 未知 address / read 不記 /
  remove 清空 / timeout-fault 下仍記錄）；snapshot payload 測試；API list/ack 測試。
  全套件 **403 passed**（唯一 fail 是既有 `test_health` 版本 pin，與本次無關）。
- 前端：`tsc --noEmit` + `eslint` + `build` 全乾淨。

### 待辦

- #72：寫入偵測擴展到 OPC UA / BACnet / SNMP / MQTT（共用 ring buffer + API + UI，
  等實際需求再排）。
- 既有 `test_health` 寫死 `version == "0.1.0"` 靠 CI env 覆寫才過，屬 stale pin，另案修。

## 2026-06-12 — 後端依賴 lock + dev/prod 依賴分離（P1）

### 現況盤點

- 前端早已 lock（`package-lock.json` tracked、CI 與 Dockerfile 都用 `npm ci`），無需動作。
- 後端 `requirements.txt` 全是 `>=` 浮動範圍——每次 build/CI 解析到的版本都可能不同。
- 測試依賴（pytest 等）混在唯一一份 requirements 裡 → 進了 prod image；
  `httpx` 確認只有測試在用（app/ 無 import）。CI 另外裸裝未釘版的 `ruff`、`pytest-cov`。

### 做法

採 compile 式 lock（`.in` 寫直接依賴 → 編譯出全 pin 的 `.txt`）：

- `requirements.in`（14 個 runtime 直接依賴）→ `requirements.txt`（45 pinned）
- `requirements-dev.in`（pytest/pytest-asyncio/pytest-cov/httpx/ruff，
  `-c requirements.txt` 約束共用 transitive 與 runtime 一致）→ `requirements-dev.txt`（17 pinned）
- 編譯器選 `uv pip compile --universal`：跨平台 lock（macOS 本機 venv 與
  Linux CI/Docker 共用同一份，靠 environment markers），pip-tools 做不到 universal。
  uv 只是開發機上的編譯工具——CI 與 Dockerfile 仍用純 pip 安裝 lock 檔，專案不依賴 uv。
- Dockerfile 不變（本來就只裝 `requirements.txt`）→ 測試依賴搬走後 prod image 自動排除 pytest。
- CI 改 `pip install -r requirements.txt -r requirements-dev.txt`。

### 驗證

- 乾淨 venv + 純 pip 裝兩份 lock → 完整測試 385 passed；唯一 fail 是
  `test_health` 寫死 `version == "0.1.0"`（CI 靠 workflow env `APP_VERSION: 0.1.0`
  蓋掉真實版本才會過）——**既有問題、與 lock 無關**（同 env 重跑即過），
  屬 PR #54 那類 stale version pin 的殘留，另案處理。
- `docker build` 通過；image 內 `pip list` 無 pytest/httpx/ruff；`import app.main` OK。
- 關鍵版本 sanity:pymodbus 3.12.1（維持已知相容 pin）、fastapi 0.136.3、SQLAlchemy 2.0.50。
## 2026-06-12 — 修復 14 個既存 ESLint 問題（issue #63，P1）

### 重點修復

1. **`useWebSocket` 重寫**（唯一的真 bug 風險）：原本 `connect` useCallback 在
   自己的 closure 裡引用自己（reconnect 的 setTimeout），React Compiler 拒絕
   編譯且有 stale-closure 風險；另外 `onMessage` 在 deps 裡，callback identity
   一變就整個斷線重連。改成：連線生命週期收進單一 effect（local function 自然
   hoist 可自我引用）、`onMessage` 走 ref（handler 更新不再觸發重連）、
   `disposed` flag 防止 unmount 後的 timer 重連。
2. **六處 setState-in-effect** 改為 derived state：
   - DataModeTab / ProfileFormModal：rows = `useMemo` 的 server-derived base +
     user-edit overlay（`edits` keyed by register name），存檔/關閉時清 overlay
   - CreateDeviceModal：default profile 改為 render 期 derive（`??` fallback），
     關閉清理移到 `handleClose` 事件
   - TemplateForm：`fetchTemplate` 改回傳資料，初始化收進 async effect
     （順帶消掉 `_id` unused var）
   - AnomalyTab / DataModeTab 的 register fetch 內聯進 effect（async IIFE +
     cancelled flag）
3. 其他：`UpdateTemplate` 空 interface → type alias；`handleExport` 搬出
   component 檔成 `exportTemplate.ts`（react-refresh）；DeviceDetail 的
   `useMemo` deps 抽出 optional chain；Mqtt 兩處 exhaustive-deps warning
   內聯修正。

### 驗證

- `npm run lint` → **0 error 0 warning**；`npm run build` 通過
- WS 重連 e2e 實測（Playwright + 本機 dev compose）：Monitor 顯示 Live →
  `docker compose stop backend` → Disconnected → `start backend` → 自動恢復
  Live，無需重整
- TemplateForm 編輯頁實測：名稱/registers 正確載入（驗證新的 async 初始化）
- DataModeTab 實測：rows 正確渲染、改 interval 只動該 row、Save All 後
  server 回讀值正確、overlay 清空


## 2026-06-12 — 部署文件補 team member 存取章節

### 背景

Ken 要讓 team member 連 GhostMeter：Web UI 走 Cloudflare、協議埠（502/4840/161）
走 Tailscale。討論釐清兩個常見誤解：

1. **Cloudflare**：不是把對方 email 加成 Cloudflare 帳號成員（那是 dashboard
   管理權限），而是加進 Zero Trust 的 **Access policy**（對方不需要 Cloudflare
   帳號，登入走 email OTP）。
2. **Tailscale**：協議埠只綁 Tailscale IP，對方必須走 tailnet。比較後選
   **node sharing**（只分享 Linode 單機）而非邀請進 tailnet——最小權限、
   不佔免費方案 6 人名額、被分享機器預設隔離不能反連。

### 處置

- `docs/deployment.md` 第 5 節 Access policy 步驟補「加 team member email /
  同網域用 Emails ending in」說明
- 新增第 6 節「協議埠給 team member（Tailscale Node Sharing）」：分享端、
  接收端（含 Windows 安裝）、驗證與收回權限步驟

純文件變更，無程式碼異動。

## 2026-06-12 — 移除 header 假 Live badge

### 問題

Ken 回報右上角 LIVE 格子超出 header 底線，並質疑它的實際功用。查證結果：

1. **跑版根因**：antd `.ant-layout-header` 預設 `line-height: 64px` 被 badge
   內的 `<span>Live</span>` 繼承，inline-flex 子元素高度由 line box 決定，
   加上 badge 自身 `padding: 4px` 後整體約 72px，超過 64px 的 header。
2. **更根本的問題**：這顆 badge 是純靜態裝飾（`MainLayout.tsx`），沒綁任何
   state——WS 斷線、backend 掛掉時照樣亮綠燈，是會誤導的假指示燈。真正的
   連線指示在 Monitor 頁標題旁（綁 WS `connected`，斷線變紅）。

### 處置

Ken 裁示方案 A：直接移除（而非接上 monitorStore 變成真指示燈）。理由：真
指示燈 Monitor 頁已有，header 重複一顆資訊價值低。

- `MainLayout.tsx` 移除 badge JSX
- `global.css` 移除 `.gm-header-live`、`.gm-header-live-dot`、`@keyframes
  gm-pulse`（grep 確認僅此 badge 使用）

驗證：`npm run build` 通過；bundle 內 grep 無 `gm-header-live`/`gm-pulse` 殘留。


## 2026-06-11 — Cloudflare Tunnel 內建支援（opt-in sidecar）

### 做了什麼

Ken 確認理想架構為「公網 → Cloudflare Access → Tunnel → Linode frontend（nginx
proxy /api、/ws）」。盤點確認 Linode 本來就有完整前端（nginx :3002，僅
Tailscale 可達），Pages 那份是 CI 副產品壞殼（issue #21，待 dashboard 停用）。

實作（VM/repo 端；dashboard 端由 Ken 操作）：

- `docker-compose.prod.yml` 新增 `cloudflared` sidecar，掛 compose profile
  `tunnel`——profile 未啟用時 `config --services` 驗證不含該服務，行為不變。
- `deploy.sh` 偵測 `.env` 的 `CLOUDFLARE_TUNNEL_TOKEN` 非空才 export
  `COMPOSE_PROFILES=tunnel`（grep 邏輯以空值/有值兩種 .env 實測過）。
- `.env.example` 新增 `CLOUDFLARE_TUNNEL_TOKEN=`（含安全警語）。
- `docs/deployment.md` 第 5 節改寫為完整流程：dashboard 三步（建 tunnel、
  Public Hostname → `http://frontend:80`、**Access policy 必設**）+ VM 端
  一行 token + `update.sh` + 驗證清單（含無痕打 `/api` 應被 Access 擋）。

### 設計取捨

- 用 compose profile 而非獨立 override 檔：單一檔案、deploy.sh 一個 if、
  token 不存在時零影響（與 BIND_IP 預設 127.0.0.1 的 fail-safe 哲學一致）。
- 認證放 Cloudflare Access 而非應用層 API key：零程式碼、天然涵蓋 `/api` 與
  `/ws` 全路徑、SSO/OTP 現成。應用層認證等真正多用戶需求出現再說。
- WS 經 tunnel 可用的前提是 same-origin（PR #58）已先落地。


## 2026-06-11 — Monitor WS 改 same-origin（P0 安全盤點的修正項）

### 盤點結論（先於修正）

針對「API 無認證但公網可達」的 P0 疑慮做了實地查證：

- Linode 上**沒有** Cloudflare Tunnel（無 cloudflared 容器/程序/token）——
  API 與前端只綁 Tailscale IP，公網不可達，風險不成立。
- `ghostmeter.pages.dev` 是活的（CI 的 Cloudflare Pages 整合每次 push 自動
  部署），但其 `/api` 打回 SPA fallback——是個無後端的壞 UI 殼（= issue #21），
  無資料暴露。處置（停用 Pages 專案或加 Access）需在 Cloudflare dashboard
  操作，記錄於 issue。

### 修正：WS 硬編碼 :8000

`MONITOR_WS_URL` 硬編碼 `ws://<hostname>:8000`，但 vite dev（`/ws` proxy）
與 production nginx（`location /ws/`）其實都早已支援 WS 代理——client 繞過
它們導致：(a) 任何 reverse proxy / tunnel 後面 Monitor 即時值都是死的；
(b) https 頁面上 `ws://` 會被瀏覽器以 mixed content 擋掉。改為 same-origin
（協議依 `location.protocol` 切 wss/ws）。

### 驗證

- `npm run build` 通過。
- 本地 production nginx 容器（:3002）實測 WS upgrade：
  `curl -H "Upgrade: websocket" ... http://localhost:3002/ws/monitor` →
  **HTTP/1.1 101 Switching Protocols**。
- 部署 Linode 後以 Tailscale IP:3002 再驗一次 101。


## 2026-06-11 — 內建 scenario 從未 seed 成功 + .env 版本覆寫（v0.4.1 部署驗證發現）

### 根因

部署 v0.4.1 到 Linode 後驗證時發現兩個問題：

1. **線上 `scenarios` 0 筆**：scenario seed JSON 的 `template_name` 寫的是
   `Solar Inverter (Fronius Symo)` / `Three-Phase Power Meter (SDM630)`——
   這兩個名字從未存在於 template seeds（實際是 `SunSpec Solar Inverter` /
   `SDM630 Three-Phase Meter`）。`seed_builtin_scenarios` 解析不到 template
   只發 WARNING，所以**任何環境都從未種進過內建 scenario**（本地 docker DB
   同樣 0 筆，先前誤判為 image 太舊）。也因此 a7c3e91f4b20 data migration
   在真實環境其實是 no-op——帶 -50 的壞 row 只存在於測試情境。
2. **`/health` 回報 0.1.0**：`.env.example` 含 `APP_VERSION=0.1.0`，Linode
   的 `.env` 由它複製而來，pydantic-settings 的 env 覆寫了程式碼裡的版本。

### 修法

- 三個 scenario seed 的 `template_name` 改為現行 template 名稱（steps 引用的
  register 名稱已逐一比對，兩個 template 全數存在，改名即足夠）。
- 守門測試 ×2：(a) 靜態交叉驗證——scenario seed 的 template_name 必須存在於
  template seeds、每個 step 的 register_name 必須存在於該 template；
  (b) e2e——seed templates + scenarios 後，API 必須回出 3 個內建 scenario。
  **紅燈驗證**：對舊 seed 檔兩個測試都 FAILED，修正後通過。
- `.env.example` 移除 `APP_VERSION`（版本是程式常數，不是部署設定）；Linode
  的 `.env` 同步刪除該行。


## 2026-06-11 — OPC UA delay fault 改非阻塞（async PreRead hook）

### 根因

OPC UA 的 delay fault 在 asyncua 的 value callback 裡 `time.sleep` 最多 10 秒。
這個 callback 是同步的，整個後端又是單一 event loop——只要一個 client 讀一個
delay-faulted 節點，**全部協議 + REST + WS + 模擬 tick 停擺**；client 每秒輪詢
等於持續癱瘓。當初做 OPC UA fault sim 時認為 read path 無法攔截（所以才走
sync callback + 「mirrors Modbus」的 trade-off）。

### 修法（Ken 裁決採 A：攔 async read 層）

重新挖 asyncua 1.1.8 內部後找到正規攔截點：`InternalSession.read` 是 async，
且開頭就 `await callback_service.dispatch(CallbackType.PreRead, ...)`——官方
callback API（`server.subscribe_server_callback`）支援 async listener。因此：

- `start()` 訂閱 `CallbackType.PreRead` → `_pre_read_fault_delay`：從
  `request_params.NodesToRead` 經新的 `_node_device` map（NodeId → device_id）
  找到 delay-faulted 設備，`await asyncio.sleep(delay)`——只暫停該 session 的
  pipeline（每個 client connection 有自己的 processor task）。
- value callback 的 delay 分支改為直接回快取值（exception/timeout/intermittent
  維持原 callback 機制，無行為變化）。
- 無 fault 時 hook 第一行 `if not self._faulted: return`，熱路徑只多一個
  set 檢查。
- Subscription/monitored item 取樣不走 `session.read`，不受 delay 影響
  （與原行為一致）。

### 驗證

- 新 regression test：1.2 s delay 讀取期間，50 ms heartbeat task 必須持續跳動
  （≥10 ticks）。**紅燈驗證**：暫時還原舊的 blocking sleep → 測試 FAILED；
  新實作 → PASSED。
- 既有 delay 測試（elapsed ≥ delay_ms）不變且通過；OPC UA 全套 39 passed。

## 2026-06-11 — Scenario step 參數驗證 + 負值 max_drift seed 修正

### 根因

/simplify 審查時發現 `ScenarioStepCreate` 缺少 anomaly 參數驗證（injection 與
schedule 都有），追查後發現這不只是驗證缺口，而是已造成一個**真 bug**：

`anomaly_injector._apply_anomaly` 的 drift clamp 是
`if abs(drift) > abs(max_drift): drift = max_drift if drift_rate >= 0 else -max_drift`
——`max_drift` 的設計語義是**幅度**（方向由 `drift_per_second` 正負號決定）。
內建 seed「Fault Disconnect」卻寫了 `max_drift: -50`：dc_voltage 以 -5/s 下垂
10 秒到 -50 後，clamp 取 `-max_drift = +50`，**瞬間反向跳 100V**，剩餘 18 秒
掛在基準值上方。schedule 那邊的 `max_drift > 0` 驗證規則一直是對的，scenario
只是漏了驗證才讓壞參數溜進 seed。

### 修法（Ken 裁決採 B：修 seed + 統一驗證）

1. `schemas/anomaly.py` 抽出 `AnomalyParamsBase`（anomaly_type + validate_params），
   `AnomalyInjectRequest` / `AnomalyScheduleCreate` / `ScenarioStepCreate` 三個
   schema 繼承——順便消掉原本 inject/schedule 兩份逐字重複的驗證器。
2. seed 改 `max_drift: 50`（方向已由 `drift_per_second: -5` 表達）。
3. **Alembic data migration `a7c3e91f4b20`**：seed loader 對已存在的 builtin
   scenario 會跳過，所以已部署環境（Linode）的壞 row 要靠 migration 修——
   只動 builtin scenario 的 drift step（`abs()` 修正），使用者自建的 scenario
   不碰（API 層從此會擋新的負值，但既有資料尊重原樣）。
4. 測試：injector 負向 drift 飽和不反轉的 regression test、scenario API 參數
   驗證 422 測試、seed 檔全數通過 `ScenarioStepCreate` 的守門測試。另修兩個
   既有測試（它們用空 params 的 spike/drift 觸發其他 422 路徑，新驗證會搶先
   擋下，補上有效參數讓原本的測試目標仍被覆蓋）。

### 驗證

- Migration 以本地假資料實測：builtin `-50 → 50`、user scenario `-30` 不動、
  非 drift step 不動；`alembic stamp` 後重跑 upgrade 確認可重入。
- `pytest tests/test_scenarios.py tests/test_seed.py tests/test_anomaly_injector.py
  tests/test_anomaly_api.py` → 47 passed；ruff clean。

## 2026-06-11 — Cut release 0.4.0 準備（Milestone 8.7）

### 做了什麼

- **版本號對齊 0.4.0**：原本三處版本各自為政——README badge 0.3.0、backend
  `APP_VERSION` 0.1.0（從未 bump 過）、frontend `package.json` 0.1.0。
  選 0.4.0 是因為自 0.3.0 後是大量向後相容的功能新增（SNMP/OPC UA/BACnet 三個
  協議、5 協議 fault parity、Scenario mode、Monitor 改版），尚未到 1.0。
- **CHANGELOG cut**：`[Unreleased]` 整段移入 `[0.4.0] - 2026-06-11`，並把歷次
  push 累積的重複章節標題（兩個 Previously Added、多個 Changed/Fixed）依
  keep-a-changelog 慣例機械式合併（條目逐字保留，僅重新分組），留下空的
  `[Unreleased]`。
- README features 補上 Scenario mode（0.4.0 主打功能漏列）。
- 後端 full suite 健康檢查：**380 passed、0 skipped**。

### 待人工執行

兩個 PR（#47 /simplify 清理、release prep）審查合併進 dev 後，開 dev→main PR
並在 merge 後打 `v0.4.0` tag。

## 2026-06-11 — Pre-release /simplify 清理（Milestone 8.7）

### 做了什麼

Cut release 前對 `main...dev` 全部累積變更（148 檔、~20k 行）跑了一輪 4 角度
（reuse / simplification / efficiency / altitude）的品質審查，去重後共 ~20 項發現，
修掉其中 14 項行為不變的 cleanup。重點：

- **Fault 能力宣告下沉到 adapter**：`ProtocolAdapter.supported_fault_types` class 屬性
  （MQTT 排除 `exception`），`PUT /devices/{id}/fault` 改為泛用能力檢查。選 class-level
  而非 instance-level 是因為 API 測試不跑 lifespan（adapter 不會註冊），capability 必須
  不依賴 running instance 也查得到——`app/protocols/__init__.py` 提供
  `get_supported_fault_types()` 查詢（lazy import 避免拖入整套 protocol stack）。
- **啟動/恢復共用註冊流程**：`main.py` 的 resume 區塊原本手抄 `start_device` 的
  adapter 註冊邏輯，且已經 drift（SNMP name map 的 bug 當初就是這樣產生的）。
  抽出 `device_service.register_device_runtime()` 供兩邊呼叫。同時把 SNMP 的
  OID→name 對照改為 `_do_add_device` 直接從 `RegisterInfo.name` 寫入，整個刪除
  `set_register_names` 兩段式註冊（含兩個 call site 的 type: ignore）。
- **前端 anomaly 中繼資料統一**：AnomalyTab 與 StepPopover 各有一份參數欄位表且
  預設值互相矛盾（spike 2.0/0.1 vs 1.5/0.8——後者其實宣告了從未套用）；timeline
  與 scenario badge 各有一份顏色表且顏色不同。統一到 `constants/anomaly.ts`。
- **Monitor 效能**：registerHistory 只剩 sparkline 一個消費者（Detail panel 已在
  Monitor 改版時刪除），改為只累積 running 設備的 primary register；DeviceDetail
  對 1 Hz broadcast 加 bail-out，值沒變不重繪。
- 其餘：OPC UA fault callback 改用共用 clamp helpers、`get_device_protocol` 單一
  JOIN query、BACnet read handler 合併、engine 死代碼、`/monitor?device=` 補消費端、
  Monitor 色票改 CSS 變數、download/WS URL 共用、測試 free-port/clean_faults 整併。

### 審查後決定不修（留待確認或 follow-up）

1. **OPC UA delay fault 會阻塞整個 event loop**（efficiency 審查發現）：asyncua 的
   value callback 是同步的，`time.sleep` 最長 10 秒會卡住所有協議 + REST + WS。
   這是當初 OPC UA fault sim 的已知 trade-off（註解寫明 mirrors Modbus），要根治
   得攔 asyncua 的 async read service 層，屬設計變更——**需要使用者確認方向**。
2. **Scenario step 缺參數驗證**（reuse 審查發現 `ScenarioStepCreate` 沒套
   `validate_params`）：不能直接補，因為內建 seed scenario 用了 `max_drift: -50`
   （負值），會被 `max_drift > 0` 規則擋下。這是 schedule 與 scenario 兩邊語義
   分歧（負向 drift 該不該允許？），**需要使用者裁決後一起修**。
3. **monitor_service 每秒全量撈 DB**（含 stopped 設備）：正確解法是記憶體快取 +
   device CRUD 失效，屬設計變更，follow-up。
4. **fault 決策樹在 5 個 adapter 各寫一份**：可抽 `resolve_fault_action()` 共用
   resolver，medium 重構，release 前不動。
5. monitor payload 的 MQTT 特例欄位改泛用 `adapter_status`、monitorStore 單例 WS
   連線：都會動到 payload/架構，follow-up。

### 驗證

- 後端 full suite **380 passed**（無 fail / 無 skip，193s；受影響的 13 個檔案先行驗證 184 passed）
- `ruff check` 乾淨；前端 `tsc -b && vite build` 通過；`eslint` 維持原有 14 個
  pre-existing 問題（均在未觸碰檔案，屬 issue #21–23 清理範圍）

## 2026-06-11 — SNMP / MQTT / BACnet 通訊層故障模擬

### 做了什麼

將通訊層故障模擬（`delay` / `timeout` / `exception` / `intermittent`）從 Modbus TCP + OPC UA 擴展到另外三個協議：BACnet、SNMP、MQTT。同時補強了 `fault_simulator.py` 的共用輔助函式。

實作範圍：

- **`fault_simulator.py`**：新增 `get_delay_seconds`（cap 10 s，NaN/inf → default 500 ms）與 `get_failure_rate`（clamp 0–1）兩個共用 helper，供各 adapter 呼叫。
- **BACnet**：在 `_DeviceApplication` 的 `do_ReadPropertyRequest` / `do_ReadPropertyMultipleRequest` 加入 `_drop_for_fault` gate；`exception` 回傳 BACnet Error `device/operationalProblem`；`timeout` / `intermittent` 另外覆寫 `do_WhoIsRequest`，讓設備對 Who-Is 也不回應（完全隱形，如同實際斷電設備）。
- **SNMP**：`exception` 在 `_DynamicMibController.read_variables` 拋出 `GenError` → pysnmp 回傳 `genErr` response；`timeout` / `intermittent` / `delay` 透過 `_FaultAwareResponderMixin` 覆寫各 command responder 的 `process_pdu`——drop 直接 return，delay 用 `loop.call_later` 延後整個 `process_pdu` 呼叫（非同步，不阻塞 event loop）。
- **MQTT**：gate 在 `_publish_loop`——`timeout` 跳過整個 publish 迴圈週期、`intermittent` 以 `failure_rate` 機率隨機跳過、`delay` sleep 後再 publish；跳過的 publish 仍計入 request + error 統計。
- **REST**：`PUT /devices/{id}/fault` 若 protocol 為 MQTT 且 `fault_type` 為 `exception`，返回 `422 VALIDATION_ERROR`，在狀態變更前就拒絕（不會留下孤兒故障）。

### 架構決策：全面採 pull-based

BACnet / SNMP / MQTT 全部採 pull-based（adapter 的 serving path 每次請求時自己讀 `fault_simulator` singleton），與 Modbus `trace_pdu` 相同。

對比 OPC UA 當初被迫採 push-based（asyncua 的 `set_attribute_value_callback` 是在 read 時呼叫的 push hook，而 asyncua 沒有可攔截真正 read 呼叫的點位），pull-based 有三個優勢：
1. Adapter 端無狀態快取——無需在 `apply_fault` / `remove_fault` 掛鉤維護 per-node 狀態。
2. Stop / Start 後故障自動存活——重啟 adapter 不需要重新 apply。
3. 單一資料源——`fault_simulator` 是唯一真相，adapter 不需要自己記錄「目前是否有 fault」。

### 設計決定

1. **MQTT 不支援 `exception`**：MQTT 是 publish-only 協議，無 request/response 通道，沒有地方可以回傳 protocol-level error。REST 層在 `PUT /devices/{id}/fault` 直接以 422 拒絕，API 文件同步說明理由。

2. **BACnet `timeout`/`intermittent` 連 Who-Is 一起裝死**：EMS 用 Who-Is 探索設備；若只有 ReadProperty 不回應但 Who-Is 仍正常，裝死的語意不完整——實際斷電的設備不會回 I-Am。覆寫 `do_WhoIsRequest` 讓整台設備從 discovery 消失，更符合「網路上不存在」的語意。

### 實作亮點 / 踩到的坑

1. **pysnmp v7 responder 全同步**：pysnmp v7 的 command responders（`GetCommandResponder` 等）繼承自 `CommandResponderBase.process_pdu`，全部是同步呼叫。`delay` 不能直接 `await asyncio.sleep`。解法：`_FaultAwareResponderMixin.process_pdu` 拿到 running event loop，把 `super().process_pdu` 包進 `_deferred()` closure（含例外 logging）後用 `loop.call_later(delay_s, _deferred)` 延後整個 PDU 處理，process_pdu 本身立刻 return（不阻塞）。以 heartbeat 測試驗證：delay 期間其他設備仍能正常服務（event loop 未被佔用）。pysnmp state cache 壽命 ~60 s，遠大於 10 s delay cap，不會因快取過期導致亂序回應。

2. **NaN 穿過 `min/max` clamp 的 bug**：review 發現原始 `get_delay_seconds` 實作 `max(0, min(10.0, delay_s))` 對 `float('nan')` 會靜默回傳 NaN（NaN 比較恆 False，min/max 不拒絕它）。修法：在 clamp 前加 `math.isfinite` guard，非有限值 fallback 到 default。對應新增了 NaN/inf 的測試案例。

3. **bacpypes3 async handler 的 early-return 語意**：BACnet read handler 可以直接 `await asyncio.sleep`（handler 本身是 async）；不送回應直接 return，bacpypes3 runtime 不會補發任何預設回應——timeout 語意天然成立，不需要額外取消排隊的 response。執行期驗證：client 等待超時，server 端 log 無異常。

### 測試

| 檔案 | 測試數 | 說明 |
|------|--------|------|
| `tests/test_bacnet_fault.py` | 11 | 含真實 bacpypes3 client 做 REST e2e round-trip |
| `tests/test_snmp_fault.py` | 8 | 含真實 SNMP GET/GETNEXT + heartbeat loop-responsiveness check |
| `tests/test_mqtt_fault.py` | 5 | fake-client publish loop 驗證各 fault gate |
| `tests/test_simulation_api.py` | +1 | MQTT + exception → 422 |
| `tests/test_fault_simulator.py` | +9 | `get_delay_seconds` / `get_failure_rate` helpers（含 NaN/inf case）|

全套 pytest 結果：詳見下方 Verification 段。

### Verification

- `ruff check app tests`：clean（All checks passed）。
- `pytest -q`（全套）：**377 passed, 67 warnings in 198.76s**（0 failures；warnings 全為 pysnmp v7 deprecated API 名稱，pre-existing，非新增）。

### Follow-up（同日，PR #45 merge 後）：Modbus fault param 統一

最終 review 發現 Modbus 是五協議中唯一沒有 sanitize fault params 的：`delay_ms` 無 10 s cap（`delay_ms=999999` 會讓 sync 的 `trace_pdu` 卡住 event loop ~17 分鐘），且 malformed `failure_rate`（如字串）會在 `trace_pdu` 內 raise `TypeError`（紅燈測試實證）。修法：`trace_pdu` 改用共用的 `get_delay_seconds` / `get_failure_rate` helpers，並補三個單元測試（cap、NaN fallback、malformed rate 不 crash）。`time.sleep` 本身是 pymodbus sync callback 的既有限制（與 OPC UA value callback 同款 trade-off），cap 後可接受。

---

## 2026-06-10 — BACnet/IP Adapter (5th protocol)

### What was built
BACnet/IP protocol adapter (`backend/app/protocols/bacnet_agent.py`) using bacpypes3 0.0.106. Implements Who-Is/I-Am device discovery, ReadProperty, and ReadPropertyMultiple — read-only for MVP.

Built-in seed template "Energy Meter (BACnet)" (`backend/app/seed/bacnet_energy_meter.json`) + Normal Operation profile. Frontend protocol option added; docker-compose + prod overlay expose UDP 47808; 17 integration tests in `backend/tests/test_bacnet_adapter.py`.

### Topology decision — router + VLAN (virtual network)
One IPv4 router Application binds UDP 47808 and bridges to a `VirtualNetwork` (VLAN, network number `BACNET_NETWORK`=100). Each GhostMeter device runs as an independent BACnet device Application on the VLAN.

- Router reserves VLAN MAC 254 and device instance = `BACNET_DEVICE_INSTANCE_BASE` (100000).
- Each simulated device: instance = base + slave_id; VLAN MAC = slave_id.
- EMS clients see N independent BACnet devices on one UDP socket.

Registers map to read-only analog-input objects: object instance = register address, objectName = register name, EngineeringUnits mapped from unit strings. Per-device read stats (request / success / error / avg ms) tracked via overridden ReadProperty handlers — more granular than OPC UA which has no per-request hooks.

### Notable implementation discoveries

1. **`VirtualNetwork._networks` class-level registry never cleaned** (`bacnet_agent.py` `stop()`): bacpypes3 keeps a class-level dict of all VirtualNetworks, and it's never cleared. On adapter restart the new VLAN can't register (name collision). `stop()` must explicitly pop the old entry — no public API exists; identity check used to guard against removing someone else's entry.

2. **bacpypes3 UDP bind is a silent background retry loop** (`bacnet_agent.py` `start()`): bacpypes3 schedules the UDP bind as a background asyncio task with infinite retry on `OSError`. A port conflict doesn't raise at `start()` — the adapter appears "running" while actually unbound. Fixed: pre-bind probe socket before starting bacpypes3 (failure is caught and logged, leaving the adapter stopped with `running=False`); pending transport tasks are cancelled at teardown.

3. **`Application.close()` does NOT detach VirtualNodes from the VLAN** (`bacnet_agent.py` `_detach_vlan_node()`): `VirtualLinkLayer.close()` is a no-op in bacpypes3. If not explicitly detached, a stopped device's VLAN node keeps answering — its I-Am responses collide with the new node's MAC on re-add (duplicate MAC address). Explicit detach helper used on both device removal and on partial add-failure (zombie node otherwise answers indefinitely).

4. **Router IPv4 network-port needs its own `networkNumber`** (`bacnet_agent.py` `start()`): without it, NPDU SADR construction crashes when routing a request from the IPv4 interface to the VLAN, because bacpypes3 can't compute the source address for the routed reply.

5. **`ProtocolAdapter.add_device` base method leaked stats entry on `_do_add_device` failure** (`backend/app/protocols/base.py`): the base template method inserted into `_device_stats` before calling `_do_add_device`; an exception left an orphan entry. Fixed in `base.py` (affects all adapters).

6. **Test reachability via route-aware addresses** (`backend/tests/test_bacnet_adapter.py`): tests reach VLAN devices on loopback using bacpypes3 route-aware address syntax (`"100:1@127.0.0.1:port"`). No broadcast dependency — CI-safe.

### Known limitation (documented in README)
BACnet discovery (Who-Is) relies on UDP broadcast, which doesn't cross docker bridge or routed subnets (e.g. Tailscale). EMS clients on a different L2 must configure the simulator's IP statically; unicast ReadProperty and directed Who-Is work fine. BBMD / Foreign Device support is deferred.

I-Am announcements are skipped on /31 and /32 binds (no broadcast address).

### Out of scope (deferred)
COV subscriptions, WriteProperty, comm-layer fault simulation, BBMD/Foreign Device registration.

### Verification
- `pytest -q`: 341 passed, 11 warnings — no regressions.
- `ruff check .`: clean.
- `npm run build`: clean (chunk size warning pre-existing, tracked as issue #23).

### Follow-up (same day) — two runtime-verified bugs fixed

1. **Wildcard bind (`0.0.0.0/0`, production default) deadlocked ALL replies on macOS.**
   Root cause (bacpypes3 0.0.106, `ipv4/__init__.py`): `IPv4DatagramServer.__init__`
   creates a SECOND endpoint task to bind the subnet broadcast address. For `/0`
   that is 255.255.255.255, which fails `bind()` on macOS (errno 49) and
   `retrying_create_datagram_endpoint` retries forever. Critically,
   `IPv4DatagramServer.indication()` — the path every outbound reply takes —
   starts with `await asyncio.gather(*self._transport_tasks)`, so every response
   hung. Inbound worked; replies never left. The `/32` test binds skip the second
   endpoint (broadcast == local tuple), which is why all 17 integration tests
   passed. Fix: when the configured prefix has prefixlen 0, `start()` removes the
   doomed broadcast endpoint task (`_disable_broadcast_endpoints`), sets
   `broadcast_address = None`, and logs a warning. I-Am broadcast is also skipped
   on `/0` (extended the existing /31–/32 guard). Regression test
   `test_wildcard_bind_serves_unicast` (fails with a 5 s timeout on macOS before
   the fix; would pass on Linux even unfixed since 255.255.255.255 binds there —
   it is a mac-dev regression guard).

2. **WriteProperty was accepted (spec violation).** The plan assumed bacpypes3
   rejects writes to non-commandable AnalogInputObject presentValue — wrong;
   runtime-verified: wrote 999.0, re-read 999.0. Fix:
   `_DeviceApplication.do_WritePropertyRequest` raises
   `ExecutionError(errorClass="property", errorCode="writeAccessDenied")`;
   bacpypes3's `Application.indication()` converts the raise into a proper BACnet
   Error PDU (verified in `bacpypes3/app.py`). Regression test
   `test_write_property_rejected` (failed with DID NOT RAISE before the fix)
   asserts the error and that the simulated value is unchanged.

Verification: `tests/test_bacnet_adapter.py` 19 passed; full suite
`pytest -q` 343 passed; `ruff check .` clean.

---

## 2026-06-10 — Fix: SNMP never served values + UPS computed-profile crash

### Discovered while seeding SNMP/OPC UA test devices
OPC UA test devices worked immediately. SNMP devices were created and OIDs
registered, but every real `snmpget`/`snmpwalk` returned `noSuchObject`.

### Bug A — SNMP agent not wired to its OID resolver
`SnmpAdapter.start()` created command responders against pysnmp's **default**
`SnmpContext` MIB controller (static, empty). The adapter's `resolve_oid` /
`get_next_oid` / `_oid_map` were never consulted by pysnmp — only the unit tests
called `resolve_oid` directly, so the suite was green while the agent served
nothing over the wire. This affected every environment (local + Linode); SNMP
had never actually worked end-to-end.
- Fix: `_DynamicMibController(AbstractMibInstrumController)` overriding
  `read_variables` / `read_next_variables` / `write_variables` to bridge to the
  adapter; registered on the null context (`register_context_name(b"", ...)`)
  after `unregister_context_name(b"")`. Added `to_snmp_object` (wraps floats as
  `OctetString`). Added an integration test doing a real GET + GETNEXT through
  the running agent — the regression test the suite was missing.

### Bug B — UPS profile computed expression syntax
`snmp_ups_normal.json` `output_power` used `output_voltage * output_current`
(bare names). The expression parser only substitutes `{braced}` variables; bare
identifiers parse as `ast.Name` and raise, so the device stopped after 5
consecutive generation errors. Fixed the seed to `{output_voltage} *
{output_current}`; added a seed assertion that computed expressions are braced.

### Multi-device SNMP note
The SNMP agent keys values by absolute OID, so two devices from the same
template collide (`OID_CONFLICT`). Distinct SNMP devices need distinct OIDs —
for the 3 test devices, two OID-offset clone templates were used.

### Verification
- `pytest -q`: 324 passed (new integration test included), no regressions.
- Live local: SNMP GET on 3 devices returns values (input_voltage ~220V) and
  computed `output_power` (~1045) with no AST errors; OPC UA ×3 still reads live.

## 2026-06-10 — Deployment tooling (Linode / Tailscale / Cloudflare)

### What was done
- Added `docker-compose.prod.yml` overlay: binds backend/frontend ports to `BIND_IP` and removes PostgreSQL's public port, using `!override` to replace (not merge) the base 0.0.0.0 bindings
- Added `deploy.sh`: applies the prod overlay, waits for postgres health, runs `alembic upgrade head`, then starts all services
- Added `docs/deployment.md` (concise Linode guide) and a `BIND_IP` entry in `.env.example`

### Key decisions
- **Prod overlay via explicit `-f`, not `docker-compose.override.yml`**: the auto-loaded override file would also apply during local development, where tests connect to PostgreSQL on `localhost:5434`; removing the postgres port there would break the existing host-test workflow
- **`!override` instead of default list merge**: Compose concatenates `ports` lists across files, which would keep the public 0.0.0.0 bindings alongside the Tailscale ones — defeating the purpose. `!override` (Compose v2.24+) replaces the list outright
- **Bind to Tailscale IP rather than Linode Cloud Firewall**: achieves "not public" with a file in the repo instead of console state; Docker bypasses ufw, so a host-side bind address is the reliable lever. `BIND_IP` defaults to `127.0.0.1` so a missing value fails safe to local-only rather than exposing everything
- **Cloudflare Tunnel for the public frontend**: outbound-only, so no inbound ports need opening and protocol ports stay private

### Notes
- App startup only seeds data; tables come from Alembic — `deploy.sh` runs migrations before bringing the app up so a fresh deploy doesn't fail on missing tables

## 2026-06-10 — Fix: CI 6h timeout root-caused to coverage C-tracer (× asyncua)

### Problem
PR #38's backend CI ran the full 6h job limit and was cancelled at ~64%. Every
OPC UA server test passed but each took ~647s; non-OPC-UA tests were instant.

### Investigation (systematic-debugging)
- Ruled out, by measurement in a `python:3.12-slim` container: asyncua server
  lifecycle (~1s), asyncua client connect/disconnect (~0s), asyncpg-after-asyncua
  on a shared loop (~0s), SQLAlchemy engine-per-loop + asyncua (~0s). None
  reproduced the 647s — so it was not reproducible outside CI.
- Instrumented CI on a throwaway branch with `pytest-timeout --timeout=120
  --timeout-method=thread`. The timeout stack dump landed inside
  `OpcUaAdapter.start()` → `asyncua.Server.init()` → `load_standard_address_space`
  → `fill_address_space` → `add_references`, preceded by thousands of
  `asyncua.server.address_space INFO add_node ...` lines.

### Root cause
`asyncua` emits ~1100 INFO lines per `Server.init()` (standard address space
load). `app/main.py` `logging.basicConfig(level=INFO)` sets the root logger to
INFO; conftest imports `app.main`, so tests inherit it and those INFO records
are written. ~25 server tests × ~1100 lines, each written to GitHub Actions'
slow per-line log sink, ballooned each test to ~11 min. Local/probe runs were
fast because asyncua defaults to WARNING with no app logging config.

This **contradicts issue #37**, which attributed the failure to asyncpg
`InterfaceError` on the shared event loop. The 6h timeout is the logging flood,
not asyncpg.

### First (wrong) hypothesis — logging flood
Initially blamed the ~1100 `asyncua.server.address_space` INFO lines emitted per
`Server.init()` (root logger at INFO via `app/main.py` basicConfig). Quieted the
asyncua logger to WARNING and re-ran CI. **It did not fix the timeout**: with the
flood gone (0 address_space lines confirmed in the CI log), each OPC UA server
test still took ~680s. The logging happened inside `fill_address_space` but was a
coincidence, not the cause.

### Real root cause — coverage C-tracer × asyncua's giant module
CI runs `pytest --cov=app`. Coverage's default C trace function fires per-line on
ALL modules. asyncua's `create_standard_address_space_Services` lives in a
~100k-line generated file and runs on every `Server.init()`; each OPC UA server
test creates a fresh Server, so coverage re-traces the whole address space build.
Reproduced in a `python:3.12-slim` container (no GHA needed): baseline init()
= 0.4s; under `coverage run` (default C core) init() did not finish in 240s;
under `COVERAGE_CORE=sysmon` init() = 0.4s again. The slowness is coverage-
specific — earlier probes were fast only because they ran without `--cov`.

### Fix
`pyproject.toml` `[tool.coverage.run] core = "sysmon"` (PEP 669 sys.monitoring,
Python 3.12+) — coverage disables instrumentation for non-`source` files, so
asyncua is no longer traced. The asyncua logger WARNING line stays as a minor
startup-noise cleanup, but it is NOT the fix.

### Lesson
The stack dump correctly located the time (inside `fill_address_space`) but the
visible symptom there (log flood) was not the cause. Should have varied the one
known difference from the passing local probes — `--cov` — before concluding.

## 2026-06-03 — OPC UA Comm-layer Fault Simulation

### What was done
- Added `apply_fault(device_id)` / `remove_fault(device_id)` no-op hooks to `ProtocolAdapter` base class. Modbus inherits these unchanged (Modbus applies faults via `trace_pdu` polling; no action needed at hook time).
- `OpcUaAdapter` overrides the hooks to attach/detach per-node asyncua value callbacks (`set_attribute_value_callback`). The callback reads `fault_simulator.get_fault(device_id)` live on every client read — same single-source-of-truth model as Modbus trace_pdu polling.
- Added per-node last-value cache (`_last_values`) and faulted-device tracking set (`_faulted`). While a fault is active, `update_register` updates the cache but skips `node.write_value` (which would clear the callback and silently disable the fault). `remove_fault` restores the node by re-writing the cached value, which simultaneously restores the stored value, clears the callback, and resumes OPC UA subscriptions.
- Fault type mapping: `exception` → `BadDeviceFailure` status code, `timeout` → `BadTimeout` status code, `delay` → bounded `time.sleep` (capped 10 s) then returns cached value, `intermittent` → random `BadCommunicationError` by `failure_rate` param.
- Auto-reattach: `_do_add_device` checks `fault_simulator` after registering nodes and re-calls `apply_fault` if a fault is already active, giving parity with Modbus (fault survives device stop/start).
- REST wiring: `PUT/DELETE /api/v1/devices/{id}/fault` now resolves the device's protocol via `device_service.get_device_protocol(session, device_id)` and calls the adapter hook. Modbus uses the inherited no-ops (still pull-based). No request/response schema change.

### Key design decisions
- **Push-based (callback) vs. pull-based:** asyncua clients read directly from the node's stored value; there is no request-intercept hook equivalent to Modbus's `trace_pdu`. The only way to inject a Bad status or a delayed response into every client read is to attach a value callback that overrides what the stored value returns. The callback is called synchronously by asyncua's address space on each `ReadRequest`.
- **asyncua callback constraint:** `set_attribute_value_callback` replaces the node's stored value reads and sets the stored value to `None`. There is no API to clear the callback directly with `None`; the only way to detach is via a `write_value` call, which sets the stored value, clears the callback, and fires subscription change notifications in one atomic operation.
- **Per-node cache necessity:** because the callback returns the last-known value for `delay`/`intermittent`, and `write_value` is suppressed while faulted, the adapter needs its own cache — the asyncua node's stored value is `None` while a callback is active.
- **Single source of truth:** the callback reads `fault_simulator` live. The hook (`apply_fault`/`remove_fault`) is a presence toggle only; the active `FaultConfig` always lives in `fault_simulator`, exactly like Modbus trace_pdu.

### Known caveat / deferred work
- **`delay` blocks the event loop:** the callback is synchronous (asyncua calls it without `await`). A `delay` fault's `time.sleep` briefly blocks the shared asyncio event loop for the sleep duration (capped at 10 s). This mirrors Modbus's synchronous delay approach (trace_pdu runs in a thread context) but is more impactful in a shared single-server setup. Mitigation: cap enforced; out of scope to convert to async for MVP.
- **`timeout` is a Bad status, not a true dropped connection:** the shared single-session server cannot drop an individual device's response at the TCP level. `BadTimeout` conveys the semantic intent; a real dropped connection would require a per-device server instance.
- **Resolved during review — `test_fault_api_roundtrip`:** after Task 4 wired `get_device_protocol` (a DB lookup), `PUT/DELETE /fault` correctly returns 404 for a non-existent device (you can't fault a device that doesn't exist). The old test used a hardcoded fake UUID and broke; it was rewritten to create a real Modbus device, and a `test_set_fault_on_unknown_device_returns_404` was added. `set_fault` was also reordered to resolve the protocol (validate) **before** mutating `fault_simulator`, so a rejected request leaves no orphan fault entry.
- **Resolved during review — fault param validation:** `FaultConfigSet` now validates type-specific params (`delay_ms` int ≥ 0; `failure_rate` float in [0,1]) → clean 422 instead of a `BadInternalError` raised deep in the value callback; the callback also clamps defensively.
- **Deferred follow-up — test-infra flake ([#37](https://github.com/kencoolguy/GhostMeter/issues/37)):** the OPC UA server tests share the asyncio event loop with the per-test asyncpg DB fixture; under load (and the `delay` test's blocking `time.sleep`) the connection can enter a bad state, cascading `asyncpg.InterfaceError` into later tests' fixture setup/teardown (errors only, never assertion failures). Pre-existing since the 8.9 adapter; aggravated here. Excluding the two OPC UA server test files the suite is clean (285 passed). Fix tracked separately.

### Files changed
- `backend/app/protocols/base.py` — `apply_fault`/`remove_fault` no-op hooks on `ProtocolAdapter`
- `backend/app/protocols/opcua_agent.py` — `_last_values` cache, `_faulted` set, `_make_fault_callback`, `apply_fault`, `remove_fault`, `update_register` skip, `_do_add_device` re-attach, `stop` cleanup
- `backend/app/services/device_service.py` — `get_device_protocol` helper
- `backend/app/api/routes/simulation.py` — `set_fault` / `clear_fault` wired to adapter hook via `get_device_protocol`
- `backend/app/schemas/simulation.py` — `FaultConfigSet` param validation (delay_ms / failure_rate)
- `backend/tests/test_opcua_fault.py` — new: adapter-level fault tests + REST wiring e2e test
- `backend/tests/test_modbus_fault.py` — added `TestBaseFaultHooks` to assert Modbus inherits no-op base hooks
- `backend/tests/test_device_simulation_integration.py` — fault roundtrip uses a real device; added 404 + invalid-param (422) tests

### Verification
- Feature suite `test_opcua_fault.py` green every run (real asyncua client round-trips for all 4 fault types, clear→restore+subscription resume, reattach-on-add, live fault-type switch).
- Full backend suite excluding the OPC UA server test files: **285 passed, 0 failures, 0 errors**. The full suite *including* them is nondeterministic due to a pre-existing asyncpg/event-loop teardown flake (errors only, 0 real failures) — tracked as [#37](https://github.com/kencoolguy/GhostMeter/issues/37).
- ruff lint clean.

---

## 2026-06-03 — OPC UA Server Adapter (4th protocol)

### What was done
- Added `OpcUaAdapter` in `backend/app/protocols/opcua_agent.py`: a single shared `asyncua.Server` (endpoint `opc.tcp://0.0.0.0:4840/ghostmeter/server/`, Anonymous + SecurityPolicy None)
- Each device becomes an Object node under a `GhostMeter` folder; each register becomes a read-only Variable node updated on every simulation tick (push model)
- Extended `RegisterInfo` in `protocols/base.py` with `name` and `unit` fields so OPC UA Variable nodes get meaningful browse names
- Added `set_device_meta` hook (mirrors MQTT pattern): device display name is passed to the adapter before `add_device` so the Object node uses the device name rather than its UUID
- Built-in "Energy Meter (OPC UA)" template (11 registers) + Normal Operation profile added to seed
- Bumped builtin template count expectation in `test_seed.py`: 4 → 5
- Frontend OPC UA protocol option added to template selector
- docker-compose port 4840 exposed for OPC UA server access

### Key decisions
- **Single shared asyncua server** (not one server per device): asyncua's server lifecycle is expensive; sharing one server matches pymodbus multi-device pattern
- **Push value-sync** (not pull like SNMP): asyncua subscriptions deliver notifications only when node values actually change; SNMP's pull model (read-on-request from datastore) doesn't apply here — the simulation engine must write into the node on every tick
- **Anonymous + SecurityPolicy None for MVP**: certificates and username/password add significant setup complexity with no benefit for local EMS testing
- **`RegisterInfo` extended with `name`/`unit`**: OPC UA Variable nodes require meaningful browse names for clients to navigate the address space; address integers alone are not useful in OPC UA context
- **`set_device_meta` pre-add hook**: device display name is not available at `OpcUaAdapter.__init__` time; the hook (same pattern as MQTT broker) injects metadata before the node tree is built

### Out of scope (deferred)
- Writable nodes (OPC UA Write service)
- Methods and alarms (OPC UA Method / Event model)
- Certificate-based security and username/password authentication
- OPC UA comm-layer fault injection (connection delay, timeout, exception codes)
- Per-request stats tracking

### Files changed
- `backend/app/protocols/opcua_agent.py` — new OpcUaAdapter
- `backend/app/protocols/base.py` — RegisterInfo name/unit
- `backend/app/config.py` — OPC UA settings
- `.env.example` (repo root) — OPC UA env vars
- `backend/app/main.py` — register adapter + resume-path wiring
- `backend/app/services/device_service.py` — set_device_meta + RegisterInfo name/unit
- `backend/app/seed/opcua_energy_meter.json` — built-in OPC UA template
- `backend/app/seed/profiles/opcua_energy_meter_normal.json` — built-in profile
- `backend/tests/test_opcua_adapter.py` — adapter unit/integration tests
- `backend/tests/test_opcua_seed.py` — seed JSON validation tests
- `backend/tests/test_seed.py` — bumped template count 4 → 5
- `backend/requirements.txt` — added asyncua>=1.1,<2
- `docker-compose.yml` — port 4840
- `frontend/src/pages/Templates/TemplateForm.tsx` — OPC UA protocol option

### Verification
- 299/299 backend tests passed (pytest -q)
- ruff lint clean
- Frontend tsc -b: no errors; npm run build: succeeded

### Post-review hardening (final code review, same day)
- **Out-of-range values bricked nodes (critical):** values outside a register's numeric type range (reachable via anomaly injection — `out_of_range` / `spike` / `drift`) were written into typed Variant nodes without clamping; asyncua stored them but every subsequent client read failed server-side (`BadInternalError` from `struct.error` / `OverflowError`). Fixed with `_coerce_to_range()` clamping in `update_register`; regression-tested across all int/float types. (Modbus is immune — values are masked into 16-bit registers — so this was OPC-UA-specific.)
- **Duplicate-name browse collision:** device `name` is not unique in the DB (only `slave_id`+`port` is), so two same-named devices shared a BrowseName and the second became invisible to browse clients. Fixed with a `(#slave_id)` qualifier on the Object node name.
- **`_device_meta` leak:** not cleaned on device removal; fixed.
- Final verification after hardening: **308/308** backend tests, ruff clean.

### Merge & follow-up (PRs #33–#35)
- **PR #33** — OPC UA adapter merged to `dev`.
- **PR #34** — pinned `pymodbus>=3.12,<3.13`. The unbounded `>=3.12` resolved to 3.13.0 on fresh installs (CI / container rebuild), and 3.13's `ModbusServerContext(devices={})` change broke the Modbus TCP server (it starts empty and adds slaves dynamically) and its tests. Surfaced while building a host venv for the OPC UA work. Verified the pin fresh-resolves to 3.12.1 with the Modbus suite green. **Deferred follow-up:** migrate the Modbus adapter to the 3.13 `ModbusServerContext` API so the cap can be lifted.
- **PR #35** — marked Milestone 8.9 as merged in `development-phases.md`.

---

## 2026-04-17 — Monitor 首頁重做 (issue #29)

### 做了什麼
- 把 `/monitor` 從「卡片 + 點擊展開細節 + 底部 Event log」改成「KPI panel + 卡片網格（點擊跳細節頁） + Toast/Drawer」
- 設為全站首頁、側邊欄第一順位
- 加入 4 主 KPI（Running/Stopped/Errors/DPS）+ 條件式 pills（active anomalies/faults、MQTT broker）
- 卡片包含：mid 密度（主指標大字 + sparkline + 副指標小字）、template name 副標、狀態燈動畫（running 呼吸/error 閃爍）、即時值更新 cyan glow flash、hover 上浮、stopped 淡化 + Start 快捷
- Event 觸發 toast 通知（3 秒自動消失）+ Drawer 累積歷史
- 完全空狀態引導（內建模板 chips + 建立 CTA）
- 後端：移除 monitor snapshot 的 stopped filter；新增 `mqtt_broker_connected` top-level 欄位、每設備 `template_name`
- 重構：`pickPrimary` register 選取邏輯抽出共用模組；`ProtocolManager.get_adapter` Optional 化 + 呼叫端 None check 統一

### 為什麼
- 對應 Phase UI #2（issue #29）— 把 Monitor 升級為視覺焦點
- 解決 stopped 設備不可見導致使用者不知設備存在的問題
- 把 register 細節分析職責還給 `/devices/{id}` 頁，Monitor 專心做 dashboard

### 遇到的問題
- Brainstorm 階段發現 issue #28（theme）的 PR 尚未 merge — 先 push + merge #28 後再 rebase monitor branch
- Code review 發現 `pickPrimary` 在 DeviceCard / DeviceCardGrid 重複定義可能 silently diverge → 抽出共用模組
- Code review 發現 monitorStore toast race（dismiss 後新 tick 可能讓 toast 復活）→ 改用 spread-only-if-newToast pattern

---

## 2026-04-10 — Isolate test database from production

### What was done
- conftest.py now creates a dedicated `ghostmeter_test` database (session-scoped fixture), runs all tests against it, and drops it on teardown
- Replaced module-level `async_session_factory` in all modules that import it directly (`app.database`, `app.seed.loader`, `app.services.monitor_service`, `app.simulation.engine`) so that seed loader and other code using `async_session_factory` also hits the test DB
- Removed `_fresh_session_factory()` workaround from `test_seed_profiles.py` that was creating its own production-pointing session factory

### Why
Running `pytest` inside the backend container executed `TRUNCATE ... CASCADE` on all production tables via conftest's `setup_database` teardown. This was the root cause of the data loss incident on 2026-04-10 — all device instances, templates, simulation configs, and profiles were wiped when tests ran against the production database.

### Decisions
- Chose to create/drop a separate database (`ghostmeter_test`) per test session rather than schema isolation, because alembic migrations and the app code assume the `public` schema
- Patched `async_session_factory` in individual modules rather than switching to a lazy accessor pattern — more explicit and avoids a larger refactor

### Files changed
- `backend/tests/conftest.py` — test DB creation, module-level factory patching
- `backend/tests/test_seed_profiles.py` — removed production DB workaround
- `CHANGELOG.md` — Fixed section
- `docs/development-log.md` — this entry

### Verification
- 278/278 tests passed
- Production DB confirmed intact after full test run (10 devices, 4 templates)
- ruff lint clean

---

## 2026-04-10 — Simulation engine crash recovery and error counting fix

### What was done
- Added `add_done_callback` on each device simulation task to detect unexpected crashes
- Implemented auto-restart with exponential backoff (2s → 4s → 8s → 16s → 32s), max 5 attempts
- After max restart attempts exceeded, device DB status is updated to "error" so the UI reflects reality
- Fixed inner error counting: `adapter.update_register` failures (e.g. pymodbus write errors) now count toward the consecutive error threshold (5 ticks)
- Introduced `_DeviceTaskState` dataclass to track restart count per device, replacing the bare `dict[UUID, Task]`

### Why
When pymodbus lost connectivity (e.g. network disconnection), `adapter.update_register` raised exceptions caught by the inner try-except (line 235). These errors were logged but never counted toward `error_count`, so the outer loop's `error_count` was always reset to 0 — the simulation task kept running but producing no useful output. If the task crashed entirely (unhandled exception), it silently disappeared from `_device_tasks` while the DB still showed `status="running"`. Users saw all register values stuck/null with no indication of a problem.

### Decisions
- Chose exponential backoff (base 2s, max 5 attempts = up to 32s delay) as a balance between quick recovery from transient issues and not hammering a persistently broken adapter
- Kept backward-compatible `_device_tasks` property so existing code (monitor_service, tests) that reads task state doesn't break
- `_on_task_done` callback distinguishes between: cancelled (normal stop), normal return (max errors hit, already handled), and exception (unexpected crash needing restart)

### Files changed
- `backend/app/simulation/engine.py` — crash recovery, error counting, `_DeviceTaskState`
- `CHANGELOG.md` — Fixed section
- `docs/development-log.md` — this entry

### Verification
- `python -m py_compile app/simulation/engine.py` — OK
- `pytest tests/test_simulation_engine.py` — 4/4 passed
- `pytest tests/test_anomaly_*.py tests/test_*simulation*.py` — 45/45 passed
- `ruff check app/simulation/engine.py` — all checks passed

---

## 2026-04-08 — Remove VirtualBox shared-folder path hacks from frontend tooling

### What was done
- Removed `/home/ken/.ghostmeter-frontend-modules/...` absolute paths from `frontend/package.json` scripts. `dev`, `build`, `lint` are now standard `vite` / `tsc -b && vite build` / `eslint .` and work on any machine after `npm install`.
- Deleted `frontend/tsconfig.local.json`, `tsconfig.local.app.json`, `tsconfig.local.node.json` — these pointed at the external `node_modules` directory via `typeRoots` / `paths` and were only useful on the VM.
- Deleted `frontend/.npmrc` (only held a comment describing the workaround).
- Removed the workaround comment block from `frontend/vite.config.ts`.

### Why
These hacks existed because the project lived on a VirtualBox shared folder (`vboxsf`) which does not support the symlinks npm uses in `node_modules`. The workaround was to install `node_modules` in `/home/ken/.ghostmeter-frontend-modules/` (outside the shared folder) and have every script reach into that path explicitly. Current development environment (macOS) no longer needs this, and the hard-coded absolute paths meant nobody else could run `npm run dev` after cloning — first blocker flagged in the consolidation audit.

### Decisions
- Chose full removal over keeping `build:local` as a fallback. The workaround is specific to one obsolete environment; keeping it would force future readers to wonder which script to run. If the VirtualBox setup is ever needed again, the original commit can be reverted from git history.
- `Dockerfile` already used standard `npm run build`, so the container build path was unaffected — verified before deleting.

### Files changed
- `frontend/package.json` — simplified scripts block
- `frontend/vite.config.ts` — removed workaround comment
- `frontend/tsconfig.local.json` — deleted
- `frontend/tsconfig.local.app.json` — deleted
- `frontend/tsconfig.local.node.json` — deleted
- `frontend/.npmrc` — deleted
- `CHANGELOG.md` — Fixed + Removed sections
- `docs/development-log.md` — this entry

### Verification
- Confirmed no remaining references to `ghostmeter-frontend-modules`, `/home/ken`, or `sf_AI_Service_Chatbot` in the repo via grep.
- Dockerfile build path (`RUN npm ci && npm run build`) unaffected since it never touched the removed files.
- `npm run dev` / `npm run build` verification on a clean checkout requires running `npm install` and should be done before merging.

### Next steps
- Consolidation step 4: run a docs-vs-implementation drift check on `api-reference.md` and `database-schema.md`.

---

## 2026-04-08 — Restore GitHub Actions CI pipeline (consolidation step 2)

### What was done
- Recreated `.github/workflows/ci.yml` with the same two-job structure as the original (backend lint/test + frontend typecheck/build).
- Updated two details vs the historical file:
  - Frontend Node version bumped from 20 → 22 to match `frontend/Dockerfile` (`FROM node:22-alpine`)
  - Frontend type check changed from `npx tsc --noEmit` to `npx tsc -b` to match the project-references setup now used by `tsconfig.json`

### Why
The consolidation audit flagged "CI status unknown". Investigation showed:
- Repo had no `.github/workflows/` directory
- `gh run list` returned empty
- But `CLAUDE.md`, `docs/development-log.md`, and `docs/development-phases.md` all claimed "GitHub Actions CI" was in place

This was a docs-vs-reality drift. `git log --all -- '.github/workflows/*'` turned up:
- 655c977 (2026-03-20) `ci: add GitHub Actions pipeline for backend lint/test and frontend build`
- 6d92a2c (2026-03-20, 17 minutes later) `chore: temporarily remove CI workflow (requires workflow scope token)`

The removal was "temporary" pending a PAT with `workflow` scope — never reverted. Restoring it now closes the drift and actually enforces lint/tests on future PRs.

### Decisions
- Restored as a new commit rather than `git revert 6d92a2c` because the file needed the Node 22 / `tsc -b` updates anyway; a revert would have landed stale content.
- Kept the original environment variables hard-coded in the workflow (`POSTGRES_*`, `APP_NAME`, etc.) — these are test-only values, not secrets.
- Did not yet add any new steps (e.g. Playwright e2e smoke) — those belong in a later consolidation task once the baseline is green.

### Files changed
- `.github/workflows/ci.yml` — created (restored + updated)
- `CHANGELOG.md` — CI section
- `docs/development-log.md` — this entry

### Verification
- File content matches the historical 655c977 version character-for-character except for the two documented updates (diffable against `git show 655c977:.github/workflows/ci.yml`).
- YAML structure verified by visual inspection — no Python `yaml` module or `actionlint` available in the local environment to run a formal parse. Will be validated by GitHub itself on first push.
- Pushing this change requires a token/gh auth with `workflow` scope (the same reason it was removed in 6d92a2c). This is a push-time concern, not a commit-time concern.

### Next steps
- Push to remote once the token/auth has `workflow` scope, then verify the pipeline actually runs green on this feature branch's PR.
- Consolidation step 4: docs-vs-implementation drift check on `api-reference.md` and `database-schema.md`.

---

## 2026-04-08 — API reference drift fix (consolidation step 4)

### What was done
Fixed documentation drift found by a systematic comparison of `docs/api-reference.md` against `backend/app/api/routes/` and `backend/app/schemas/`. Added 18 previously undocumented endpoints plus a field and note fix on `RegisterValue`.

Changes to `docs/api-reference.md`:

1. **`RegisterValue` schema block**:
   - Added `oid: string | null` field (used by SNMP templates, `null` for Modbus)
   - Replaced the stale "`Phase 3: always null`" note on `value` with an accurate description: value is the last tick's value (null when stopped / no tick yet) and live clients should subscribe to `/ws/monitor` rather than poll the detail endpoint.

2. **New section: Simulation Configuration** (inserted between Simulation Profiles and MQTT).
   Covers:
   - Schemas: `SimulationConfigCreate`, `SimulationConfigBatchSet`, `SimulationConfigResponse`, `FaultConfigSet`, `FaultConfigResponse` (including fault-type param tables)
   - Endpoints: `GET/PUT/DELETE /devices/{id}/simulation`, `PATCH /devices/{id}/simulation/{register_name}`, `GET/PUT/DELETE /devices/{id}/fault`
   - Documented in-memory-only behaviour of faults (cleared on restart).

3. **New section: Anomaly Injection** (inserted after Simulation Configuration).
   Covers:
   - Both real-time injection and persisted schedules as the two mechanisms
   - Schemas: `AnomalyInjectRequest`, `AnomalyActiveResponse`, `AnomalyScheduleCreate`, `AnomalyScheduleBatchSet`, `AnomalyScheduleResponse`
   - Params tables per anomaly type (`spike`, `drift`, `flatline`, `out_of_range`, `data_loss`)
   - Endpoints: `POST/GET/DELETE /devices/{id}/anomaly`, `DELETE /devices/{id}/anomaly/{register_name}`, `GET/PUT/DELETE /devices/{id}/anomaly/schedules`
   - Noted the route ordering constraint (the `/schedules` routes must come before `/{register_name}` to avoid wildcard collision — this was already done in `anomaly.py` but is worth documenting so future editors don't reorder).

4. **Simulation Profiles section**: added the three missing endpoints.
   - `GET /simulation-profiles/template/{template_id}` — download blank profile JSON (raw file download, not `ApiResponse`)
   - `GET /simulation-profiles/{profile_id}/export` — export profile as JSON file
   - `POST /simulation-profiles/import?template_id=...` — upload profile JSON, with the required `template_id` query param documented explicitly

Changes to `docs/development-phases.md`:

- Added **Milestone 8.6 — Polish & UX Fixes** capturing auto-resume, Device Detail live values (#19), Open in Monitor deep-link, anomaly param form, batch naming fix
- Added **Milestone 8.7 — Consolidation** (in progress) with checked boxes for steps done so far and unchecked boxes for remaining work, including the three audit-surfaced issues (#21 #22 #23)

### Why
The consolidation audit surfaced that `api-reference.md` documented only the core CRUD surface — anomaly, simulation-config, fault, and the profile import/export variants were all completely absent despite being shipped and actively used. The `RegisterValue.value` note still said "Phase 3: always null" even though #19 had closed that behaviour weeks ago. This is the kind of drift that silently erodes trust in the docs and makes external integration impossible.

The phases doc wasn't dangerously wrong but also hadn't captured anything after Scenario Mode (milestone 8.5). Adding 8.6 and 8.7 gives a clean line of sight into what's in flight without rewriting earlier phases.

### Decisions
- **Where to put the new sections**: I chose top-level sections ("Simulation Configuration", "Anomaly Injection") rather than sub-sections of Devices because (a) they have their own pydantic schemas with meaningful surface area, and (b) the existing `Simulation Profiles` section is already a peer, so three "Simulation*" / anomaly sections sit consistently together. The table of contents pattern of the file is one H2 per logical resource group, which I followed.
- **Left Devices section alone**: Not re-touched beyond the `RegisterValue` schema fix. Its CRUD docs are accurate.
- **Did NOT document `/ws/monitor` snapshot shape in this pass**: there's a whole monitor snapshot structure worth documenting, but that's a second drift item and the user asked specifically for the drift report's 18 endpoints + oid. Deferred — will add to consolidation backlog if it matters.
- **Left the "Phase 3" vintage comment on `RegisterValue` docstring in `backend/app/schemas/device.py`**: that's code, not docs. Code comments can drift but this one just says "Phase 3: always None" and the user didn't ask for a code sweep. Leave for now.

### Files changed
- `docs/api-reference.md` — ~320 lines added across four edits
- `docs/development-phases.md` — new Milestones 8.6 and 8.7
- `CHANGELOG.md` — Documentation section under [Unreleased]
- `docs/development-log.md` — this entry

### Verification
- `grep -E '^(### )?#{0,3} ?`[A-Z]+ /api/v1' docs/api-reference.md` — every added endpoint can be located by its method + path.
- Cross-checked each new endpoint path against the actual route decorator in `backend/app/api/routes/{anomaly,simulation,simulation_profiles}.py` to make sure method and path match.
- No code was changed — this is documentation-only, so there is no build/test to rerun.

### Next steps
- Consolidation step 6: run backend `pytest` full suite and confirm no skips / flakies.
- Consolidation step 5: cut a release (the README's `0.3.0` badge vs. the pile of Unreleased entries is its own drift).

---

## 2026-04-08 — Clear accumulated ruff lint debt so CI goes green

### What was done
The first real CI run on PR #24 (after restoring `.github/workflows/ci.yml`) surfaced **91 ruff errors** that had accumulated in `backend/` between 2026-03-20 (when CI was removed) and today. Fixed all of them.

**Breakdown:**
- 31× `I001` unsorted-imports — auto-fixed by `ruff check --fix`
- 12× `F401` unused-import — auto-fixed
- 44× `E501` line-too-long — handled manually; 16 of them live in `alembic/versions/*.py` (see decision below), the other 28 were hand-wrapped
- 2× `F841` unused-variable — dropped the unused `devices = await _setup_devices(...)` binding in `tests/test_batch_device_ops.py` where the return value was never read
- 1× `E402` module-level import not at top — added `# noqa: E402` with an explanatory comment in `app/services/scenario_runner.py`, since the late import exists to break a circular dependency
- 1× `W291` trailing-whitespace — removed trailing space on `Revises: ` line in `alembic/versions/448f2e5c6613_...py`

### Why
CI was off from 2026-03-20 to 2026-04-08. During that window several feature branches landed on dev (MQTT, SNMP, Scenarios, Device Detail live values, anomaly params form) without a lint gate. The 91 errors are the accumulated cost. The consolidation audit called this out as the expected consequence of "step 2: restore CI" — first run is guaranteed to be red.

### Decisions
- **`alembic/versions/*` → `E501` per-file-ignore** instead of hand-wrapping 16 lines in migration files. These files are auto-generated by `alembic revision --autogenerate`; hand-wrapping the `sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False)` lines would just get overwritten on the next regen. Standard Python ecosystem practice. Added one line to `backend/pyproject.toml` under `[tool.ruff.lint.per-file-ignores]`.
- **Did NOT run `ruff format`** even though it would fix some issues. `ruff format` would reformat 71 files and touch far more than the 91 specific errors — that's churn, not cleanup. Kept the diff scoped to exactly what was needed.
- **`# noqa: E402` over restructuring scenario_runner.py**: the late `from app.simulation import anomaly_injector as _anomaly_injector` was added to avoid a real circular import between `services` and `simulation` packages. Moving it to the top would need a restructure that's out of scope. A documented `noqa` is clearer than rearranging the package boundary.
- **Dropped unused `devices =` bindings in test_batch_device_ops.py** rather than converting to `_` or adding `# noqa: F841`. The tests were using the helper for side effects only — the assignment was a leftover from a refactor. Deleting the assignment is the real fix.
- **Used `def _sort_key` instead of an inline `lambda`** in `engine.py:189`. First attempt was a named lambda with `# noqa: E731`; realized that's trading one lint error for another. A real nested function is cleaner.

### Files changed
- `backend/pyproject.toml` — per-file-ignores
- `backend/app/api/routes/devices.py`, `backend/app/api/routes/scenarios.py` — wrapped long f-strings and decorators
- `backend/app/main.py` — wrapped long logger call and `include_router` calls
- `backend/app/services/scenario_runner.py` — `# noqa: E402` + comment; wrapped long condition and logger call
- `backend/app/simulation/engine.py` — replaced long inline lambda with a named `_sort_key`
- `backend/alembic/versions/448f2e5c6613_*.py` — removed trailing whitespace
- 36 auto-fixed files (imports): `alembic/env.py`, 11 migration files, 11 app files, 13 test files (see `git show` for full list)
- 8 manually-wrapped test files: `test_batch_device_ops.py`, `test_modbus.py`, `test_modbus_fault.py`, `test_device_profile_apply.py`, `test_device_simulation_integration.py`, `test_scenarios.py`, `test_seed_profiles.py`, `test_simulation_api.py`

### Verification
- `ruff check .` from `backend/` → `All checks passed!` (exit 0)
- `python3 -m compileall -q app/ alembic/versions/ tests/` → exit 0 (no syntax errors introduced)
- Pytest not runnable locally in this environment (no venv with backend deps), but all 91 errors are pure formatting / unused-binding / line-wrap — none of them change runtime behaviour. CI will be the real test.

### Next steps
- Push this commit, watch PR #24 CI turn from red to green.
- Consolidation step 6: full `pytest` run in CI.
- Consolidation step 5: cut a release.

---

## 2026-04-08 — API reference drift fix (consolidation step 4)

### What was done
- **Live register values in Device Detail**: Connected Device Detail page to the existing `ws/monitor` WebSocket. Register table now overlays real-time values from the monitor broadcast instead of showing `—` (null). When the device is not running, values remain `—`.
- **"Open in Monitor" button**: Added a button on Device Detail that navigates to `/monitor?device=<id>`, auto-selecting the device in the Monitor page. Button is disabled when the device is not running.
- **Connection status badge**: Register Map card title shows a `Live` / `Disconnected` badge when the device is running.
- **Monitor auto-select via query param**: Monitor page reads `?device=` query param on mount, waits for WebSocket data to arrive, then auto-selects the matching device. Query param is cleared after use to avoid stale state.

### Decisions
- Reused the existing `useWebSocket` hook and `ws/monitor` endpoint — no backend changes needed
- Used `useMemo` to merge live values into the register list (keyed by register name), keeping the original register metadata (address, data type, etc.) from the REST API
- Used a `useRef` flag (`autoSelectApplied`) to ensure the query param auto-select fires only once, even if `devices` array updates multiple times
- Disabled the "Open in Monitor" button for non-running devices since the monitor only shows running devices

### Files changed
- `frontend/src/pages/Devices/DeviceDetail.tsx` — WebSocket connection, live value overlay, Open in Monitor button
- `frontend/src/pages/Monitor/index.tsx` — `?device=` query param auto-select logic

---

## 2026-03-29 — Auto-resume & Monitor UX Improvements

### What was done
- **Auto-resume on startup**: Backend lifespan now queries `device_instances` for `status=running`, registers each device in the protocol adapter (Modbus/SNMP), and restarts simulation engine. Previously, a backend restart left all devices in a "running" DB state but with no actual simulation running.
- **Monitor card defaults**: DeviceCard preview changed from voltage_l1/l2 to total_power + total_energy (with fallback for templates without those registers)
- **Monitor chart multi-select**: Chart section now supports multiple selected registers, defaults to total_power + total_energy
- **Batch name prefix fix**: Removed extra space between prefix and slave ID — users control separators in the prefix itself
- **.gitignore**: Added `.mcp.json`
- **README.md**: Added Docker operations quick reference

### Decisions
- Auto-resume runs after protocol adapters are started but before WebSocket broadcast — ensures values start flowing immediately on first client connect
- Monitor register preference uses a hardcoded `["total_power", "total_energy"]` list with fallback to first registers — simple and sufficient for current templates

### Root cause of the "no values" bug
After `docker compose down -v`, DB was wiped. User rebuilt devices and started them via UI (status=running in DB), but when backend later restarted, the lifespan only started protocol adapters — it never re-registered devices or restarted simulation tasks. The simulation engine's in-memory state was empty.

---

## 2026-03-27 — Scenario Mode (Milestone 8.5)

### What was done
- **DB models + migration**: `scenarios` and `scenario_steps` tables with UUID PKs, JSONB anomaly_params, cascade delete from templates
- **Pydantic schemas**: ScenarioCreate, ScenarioUpdate, ScenarioDetail, ScenarioSummary, ScenarioStepCreate, ScenarioExport, ScenarioExecutionStatus, ActiveStepStatus
- **Scenario CRUD service**: Full REST API at `/api/v1/scenarios` — list (with template filter), get, create, update (full replace), delete, export, import
- **ScenarioRunner**: Async executor that schedules anomaly injections on a timeline using asyncio tasks; tracks elapsed time, active steps, and auto-cleans up on completion
- **Execution API**: `POST /devices/{id}/scenario/{id}/start`, `POST /devices/{id}/scenario/stop`, `GET /devices/{id}/scenario/status` — validates device running state, template match, and single-scenario-per-device constraint
- **Built-in seed scenarios**: 3 scenarios for Three-Phase Meter template — Power Outage Recovery (60s), Voltage Instability (90s), Inverter Fault Sequence (120s)
- **Frontend types, API client, store**: `scenario.ts` types, `scenarioApi.ts`, `scenarioStore.ts` following existing patterns
- **ScenarioList page**: Table with template filter dropdown, create/edit/delete actions, clone, export (JSON download), import (JSON upload)
- **TimelineEditor**: Visual drag-and-drop blocks on a register x time grid; StepPopover for editing anomaly params; auto-computes total_duration_seconds
- **ScenarioExecutionCard**: Device Detail component with scenario selector, start/stop buttons, progress bar with real-time polling (1s interval)
- **19 integration tests**: CRUD operations, seed loading, idempotency, built-in protection, export/import round-trip

### Decisions
- Scenarios are template-bound (not device-bound) — reusable across all devices of the same template
- Steps use `register_name` (not register ID) for portability in export/import
- `total_duration_seconds` is computed as `max(trigger_at + duration)` across all steps on create/update
- Built-in scenarios: cannot be updated or deleted (403/409), but can be cloned and exported
- ScenarioRunner is in-memory only — no execution history persisted to DB (sufficient for MVP)
- Timeline editor uses CSS-based positioning (percentage of total duration) rather than a charting library

### Test results
- 278 backend tests passing (19 new for scenarios)
- Frontend TypeScript check + Vite build pass

---

## 2026-03-27 — Publish/Stop UX Unification (#11)

### What was done
- MQTT card redesigned with edit/publish mode separation
  - All form fields disabled during publishing
  - Info alert: "Stop publishing to edit settings"
  - Auto-save on Start Publishing
- Device list: added `mqtt_publishing` boolean to API response (LEFT JOIN mqtt_publish_configs)
- Device list: green MQTT tag shown for devices actively publishing
- Device detail: MQTT Publishing tag shown in status area
- Button style unification (green primary for start, danger for stop)

### Decisions
- Kept Modbus and MQTT architecturally separated (no state machine changes)
- Used LEFT JOIN + boolean field instead of N+1 frontend queries for MQTT status
- MQTT tag only shown when device is running AND mqtt_publishing is true

---

## 2026-03-25 — Frontend Profile Selector (Phase 8.3)

### What was done
- **Profile types, API client, store**: New `profile.ts` types, `profileApi.ts`, `profileStore.ts` following existing patterns
- **ProfilesTab**: Profile list table in template detail with edit/delete/set-default actions, built-in protection
- **ProfileFormModal**: Create/edit modal with per-register config table (reuses DataModeTab pattern)
- **TemplateForm Tabs**: Wrapped Register Map + Profiles in Tabs for edit/view mode
- **CreateDeviceModal profile dropdown**: Fetches profiles on template change, pre-selects default, shared between single/batch tabs
- **Device types**: Added `profile_id` to `CreateDevice` and `BatchCreateDevice`

### Decisions
- Profile dropdown hidden when template has zero profiles (clean UX)
- Shared profile state between single/batch tabs (not per-form)
- Built-in profile configs are read-only in modal; name/description still editable

---

## 2026-03-25 — MQTT Adapter (Phase 8.2)

### What was done
- **MQTT protocol adapter**: `MqttAdapter` class extending `ProtocolAdapter` base, using `aiomqtt` for async MQTT publish
- **DB models + migration**: `mqtt_broker_settings` (global, single-row) and `mqtt_publish_configs` (per-device, one-to-one)
- **MQTT service layer**: CRUD functions for broker settings and per-device publish configs with upsert semantics
- **API routes**: `GET/PUT /system/mqtt` (broker), `GET/PUT/DELETE /system/devices/{id}/mqtt` (publish config), `POST /system/mqtt/test` (connection test), `POST /system/devices/{id}/mqtt/start|stop` (publish control)
- **Frontend UI**: Broker settings form in Settings page, per-device MQTT publish config card in Device Detail page
- **System export/import integration**: Broker settings and publish configs included in export JSON, imported with upsert
- **Docker Compose**: Optional mosquitto service behind `profiles: ["mqtt"]` for dev testing
- **Tests**: 30 new tests (22 MQTT CRUD/adapter + 8 export/import integration)
- **Rebase onto dev**: Resolved conflicts with simulation profiles branch (5 conflict files)

### Decisions
- MQTT adapter reads values from SimulationEngine at publish time (no register sync needed)
- Broker connection is lazy — adapter starts inactive if no settings configured, does not block other adapters
- Password masking: API responses show `****`, PUT with `****` preserves existing password
- Mosquitto in docker-compose is dev-only (profiles flag), production uses external broker
- Export includes unmasked password for portability; import preserves existing password on `****`

### Issues encountered
- MQTT branch diverged from dev before simulation profiles were added — required rebase with 5 conflict resolutions
- Template creation tests initially failed due to wrong `byte_order` value (`"big"` vs `"big_endian"`)

### Test results
- 229 backend tests passing (30 new for MQTT)
- All existing tests unaffected by rebase

---

## 2026-03-25 — Simulation Profiles

### What was done
- **New `simulation_profiles` table**: ORM model, Alembic migration, JSONB configs column storing reusable simulation parameter sets
- **Profile CRUD API**: Full REST endpoints at `/api/v1/simulation-profiles` with list, get, create, update, delete operations
- **Profile auto-apply on device creation**: `profile_id` field added to `DeviceCreate`/`DeviceBatchCreate`. Absent = auto-apply default profile; explicit `null` = skip; UUID = apply specific profile
- **Built-in profiles**: Three seed JSON files (three-phase meter, single-phase meter, solar inverter) loaded at startup with physically consistent simulation parameters
- **Seed loader**: `seed_builtin_profiles()` function added to loader, called from app startup after template seeding
- **Comprehensive tests**: 22 new tests covering CRUD, auto-apply, batch apply, seed loading, idempotency, and built-in protection

### Decisions
- Profile configs are **copied** into `simulation_configs` at apply time — no ongoing reference. This allows users to customize per-device without affecting the profile
- At most one `is_default=true` per template, enforced via PostgreSQL partial unique index
- Built-in profiles: configs are immutable (403 on update), cannot be deleted (403), but name/description can be changed
- `profile_id` absent vs explicit `null` distinguished via `model_fields_set` in Pydantic

### Issues encountered
- Alembic autogenerate produced empty migration when run inside Docker container without volume mount — solved by rebuilding the image after code changes
- Test ordering issue: `seed_builtin_profiles` uses global `async_session_factory` which gets stale connections across event loops — solved by patching with a fresh session factory in tests

---

## 2026-03-22 — Template & Device UX Improvements

### What was done
- **Device edit UI**: Added `EditDeviceModal` component for editing name, description, slave ID, port. Integrated into DeviceList (pen icon) and DeviceDetail (Edit button). Slave ID/port disabled when running.
- **Built-in template read-only view**: Added View button (eye icon) on TemplateList for built-in templates. TemplateForm now detects `is_builtin` and shows read-only mode with "Built-in" tag, disabled inputs, and Back button instead of Save.
- **Template import error feedback**: ImportExportButtons now shows a detailed error modal on import failure, including the specific validation error and a collapsible section with expected JSON format.
- **Port change**: Frontend Docker port changed from 3000 to 3002; CORS updated accordingly.
- **Demo script**: Added `scripts/start-demo.sh` — one-command startup that builds Docker containers, creates a test device, configures simulation, and verifies Modbus TCP reads.
- **Cleanup**: Removed unused imports in AnomalyTab and Simulation index.

### Decisions
- Edit modal reused across both list and detail pages for consistency
- Running devices can still open edit modal (to change name/description), but Slave ID and port fields are disabled — backend also enforces this but frontend gives immediate feedback
- Built-in templates use the same TemplateForm in read-only mode rather than a separate component
- Port 3002 chosen to avoid conflicts with other local services on 3000

### Issues encountered
- Pre-existing TypeScript errors in other pages (antd v6 icon imports, recharts types) — not related to these changes

---

## 2026-03-20 — Phase 7: System Finalization

### What was done
- Implemented system config export API (`GET /api/v1/system/export`) — full snapshot of templates, devices, simulation configs, anomaly schedules as JSON file download
- Implemented system config import API (`POST /api/v1/system/import`) — upsert by name/slave_id, skips built-in templates, all-or-nothing transaction
- Created Pydantic schemas for export/import format (reference by name, not UUID)
- Built frontend Settings page with export button (file download) and import button (file upload with result summary modal)
- Added Settings route and sidebar menu item
- Created GitHub Actions CI pipeline: backend (Python 3.12 + PostgreSQL 16 service + ruff lint + pytest) and frontend (Node 20 + tsc + build)
- Added Playwright smoke tests for all 5 pages (Templates, Devices, Simulation, Monitor, Settings)
- Added `.dockerignore` files for backend and frontend
- Created CONTRIBUTING.md with development setup, conventions, and PR process
- Backend test coverage: 71% (177 tests passing, 14 new tests for export/import)

### Decisions
- Export format uses names (template_name, device_name) instead of UUIDs for cross-machine portability
- Import upserts templates by `name`, devices by `(slave_id, port)` — existing data gets updated, not duplicated
- Built-in templates (`is_builtin=true`) are exported but skipped on import (already seeded)
- Simulation configs and anomaly schedules are replaced per-device on import (delete-then-insert)
- Playwright tests run against built preview server — no backend required for smoke tests
- CI skips Playwright (not installed in CI yet) — frontend job only does typecheck + build

### Issues encountered
- npm install fails on shared folder (VirtualBox) due to symlink permissions — Playwright added to package.json manually
- Pre-existing antd v6 + React 19 TypeScript issues in icon imports — not related to Phase 7 changes

### Test results
- 177 backend tests passing (14 new for export/import)
- Frontend TypeScript check passes (`tsc --noEmit`)
- Overall backend coverage: 71%

---

## 2026-03-19 — Phase 6: Real-time Monitor Dashboard

### What was done
- Implemented WebSocket `/ws/monitor` backend with 1Hz broadcast loop
- Created MonitorService with in-memory event log (deque, max 100) and data aggregation
- Added per-device communication statistics (DeviceStats) to ModbusTcpAdapter
- Wired event logging into device start/stop, anomaly inject/clear, fault set/clear
- Built frontend Monitor Dashboard: DeviceCardGrid, DeviceDetailPanel, RegisterChart (Recharts), StatsPanel, EventLog
- Created useWebSocket hook with exponential backoff reconnect
- Created monitorStore (Zustand) with rolling register history buffer (300 points)

### Decisions
- Used `Flex` instead of `Row`/`Col` for antd v6 compatibility (Col has TypeScript index signature conflict with children)
- Icons imported without `@ant-design/icons` barrel to avoid `verbatimModuleSyntax` TS errors
- MonitorService queries DB for running devices each snapshot cycle — acceptable for MVP, may need caching if >100 devices
- WebSocket broadcast sends all device data to all clients (no per-device subscription) — simple for MVP

### Issues encountered
- Missing `pymodbus` in requirements.txt — was never added, Docker build cached old layer
- Missing `MODBUS_HOST`/`MODBUS_PORT` in Settings config — main.py referenced them but config never had them
- antd v6 + React 19 has widespread TypeScript issues with icon imports and Col component — pre-existing across codebase

### Test results
- 163 backend tests passing (all existing tests unaffected)

---

## 2026-03-18 — Phase 3: Device Instance Module

### What was done
- Implemented full device instance CRUD backend (Milestone 3.1)
- Implemented frontend device management UI (Milestone 3.2)
- 50/50 backend tests passing; frontend TypeScript check and Vite build pass

### Backend highlights
- **ORM model**: `DeviceInstance` with FK RESTRICT to `device_templates`, unique constraint on `(slave_id, port)`
- **Alembic migration**: `d013e48e688a` creates `device_instances` table
- **Pydantic schemas**: `DeviceCreate`, `DeviceBatchCreate`, `DeviceUpdate`, `DeviceSummary`, `DeviceDetail`, `RegisterValue`
- **Service layer** (`device_service.py`): CRUD, batch create (atomic, up to 50), start/stop state machine, register view (value=None in Phase 3)
- **API routes** (`/api/v1/devices`): list, create, batch create, get detail, update, delete, start, stop, get registers
- **ConflictException** (HTTP 409): used for running device protection and invalid state transitions
- **Template deletion protection**: `delete_template` now checks for referencing devices before allowing deletion
- **Tests**: `test_devices.py` (24 cases) + `test_template_protection.py` (2 cases) = 26 new tests

### Frontend highlights
- **Types**: `DeviceSummary`, `DeviceDetail`, `RegisterValue`, `CreateDevice`, `BatchCreateDevice`, `UpdateDevice` in `src/types/device.ts`
- **API service**: `src/services/deviceApi.ts` wraps all device Axios calls
- **Zustand store**: `deviceStore` holds device list, current device, loading state
- **Pages**: `DeviceList` (table with status badges, start/stop toggle, delete), `CreateDeviceModal` (single + batch tabs), `DeviceDetail` (register map table)
- **Routing**: `/devices` → list, `/devices/:id` → detail

### Key decisions
- **Status is pure DB field in Phase 3**: start/stop only toggles the `status` column; actual Modbus server lifecycle will be added in Phase 4
- **FK RESTRICT**: templates cannot be deleted while devices reference them; service layer checks first with friendly error, DB constraint acts as safety net
- **Batch create is atomic**: any slave_id conflict fails the entire batch
- **DeviceUpdate is full replacement**: consistent with Phase 2's `TemplateUpdate` pattern; `template_id` and `status` are excluded from update schema

### Issues encountered
- VirtualBox shared folder still cannot run `npm install` (symlink restriction); used existing external node_modules at `/home/ken/.ghostmeter-frontend-modules/`
- Frontend build requires using the custom `vite.config.ts` from the external modules directory

---

## 2026-03-17 — Phase 2: Device Template Module

### What was done
- Implemented full device template CRUD backend (Tasks 1–11 of Phase 2 plan)
- Implemented frontend template management UI (Tasks 12–17 of Phase 2 plan)
- 24/24 backend tests passing; frontend build passes

### Backend highlights
- **ORM models**: `DeviceTemplate` + `RegisterDefinition` with cascade delete and two uniqueness constraints (name per template, address+FC per template)
- **Alembic migration**: `448f2e5c6613` creates both tables
- **Pydantic schemas**: `TemplateCreate`/`TemplateUpdate`/`TemplateDetail`/`TemplateSummary`/`TemplateClone` + shared `ApiResponse[T]` envelope
- **Service layer** (`template_service.py`): address overlap validation (per FC, per template), `ForbiddenException` guard on built-in templates for update/delete, export strips IDs for portability
- **API routes** (`/api/v1/templates`): list, create, get, update, delete, clone, export, import
- **Seed loader** (`seed/loader.py`): runs at FastAPI startup, idempotent — skips templates that already exist by name; loads three JSON files: `three_phase_meter.json` (SDM630), `single_phase_meter.json` (SDM120), `solar_inverter.json` (Fronius Symo / SunSpec)
- **Tests**: `test_templates.py` (API integration, 20 cases) + `test_seed.py` (4 cases)

### Frontend highlights
- **Types**: `DeviceTemplate`, `RegisterDefinition`, `TemplateSummary`, `TemplateDetail` in `src/types/template.ts`
- **API service**: `src/services/templateApi.ts` wraps all Axios calls
- **Zustand store**: `templateStore` holds list, loading state, and selected template
- **Pages**: `TemplateList` (table with built-in badge), `TemplateForm` (create/edit with register table), `RegisterTable` (editable rows), `ImportExportButtons`
- **Routing**: `/templates` → list, `/templates/new` → create, `/templates/:id` → edit

### Key decisions
- **PUT replaces registers wholesale**: simpler than PATCH + partial register diffs; client always sends the full register list
- **`/import` route must precede `/{template_id}`**: FastAPI path matching would otherwise treat the literal string `"import"` as a UUID, causing 422 errors
- **Seed data is idempotent**: loader checks name existence before insert; safe to run on every startup without duplicating templates
- **Address overlap uses half-open ranges per FC**: `float32` at address 0 occupies registers 0–1; any other register with address 1 in the same FC would overlap and is rejected
- **VirtualBox workaround carries over**: pytest and npm still run from outside the shared folder (`/home/ken/ghostmeter-venv` and `/home/ken/ghostmeter-node`)

### Issues encountered
- FastAPI route ordering: `/import` must be registered before `/{template_id}` to prevent the literal `"import"` being parsed as a UUID path parameter
- `updated_at` `onupdate` does not trigger on relationship mutations (registers replaced via `clear()` + reassign); workaround: the `get_template` re-fetch after commit returns the DB-refreshed value which is sufficient for tests

---

## 2026-03-17 — Phase 1: Project Skeleton & Foundation

### What was done
- Completed all 3 milestones of Phase 1 (Docker, Backend, Frontend)
- Full stack verified: `docker compose up --build` starts all 3 services successfully
- Backend health check returns `{"status":"ok","database":"connected","version":"0.1.0"}`
- Frontend serves Ant Design layout with 4 navigable pages via nginx

### Key decisions
- **Local dev approach**: Docker only for PostgreSQL, backend/frontend run natively for faster iteration
- **Port 5434**: PostgreSQL mapped to host port 5434 instead of 5432 due to port conflict with existing service on dev machine
- **DATABASE_URL construction**: Uses `@computed_field` to auto-build from individual `POSTGRES_*` env vars, allowing `.env` to be shared between docker-compose and backend app
- **Health endpoint at root**: `GET /health` is at root path (not under `/api/v1`) — exempt from standard response wrapper for infrastructure monitoring compatibility
- **Alembic migration deferred**: Only Alembic infrastructure set up in Phase 1; actual table migrations will be created in Phase 2 when ORM models are defined
- **VirtualBox workaround**: Python venv and npm node_modules stored outside shared folder due to symlink restrictions on vboxsf filesystem

### Issues encountered
- VirtualBox shared folder (`vboxsf`) does not support symlinks, which breaks both Python venv and npm node_modules creation. Solved by placing these in native Linux filesystem (`/tmp/` and `/home/ken/`).
- Port 5432 occupied by existing `enol-pgbouncer` container, switched to 5434.
