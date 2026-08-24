# Deployment — Linode (Tailscale + Cloudflare)

部署到一台公網 Linode VM 的精簡指南。設計目標:**協議埠只走 Tailscale,公網不裸奔;前端走 Cloudflare 對外。**

## 前置概念(兩個雷)

1. **App 啟動時只做 seed,不建表** — 資料表靠 Alembic migration。`deploy.sh` 已把「先 migration 再啟動」包好,照用即可,別直接 `docker compose up`。
2. **Docker 會繞過 ufw** — `ports:` 預設 publish 到 `0.0.0.0`(公網)。本專案用 `docker-compose.prod.yml` 把所有 port 改綁到 `BIND_IP`(= 本機 Tailscale IP),公網完全不 listen,所以**不需要**另外設 ufw / Linode Cloud Firewall 也能不裸奔(設了更保險)。

## 1. 開 VM 與安裝

- Ubuntu 24.04 LTS,**至少 2GB RAM**(前端 build 吃記憶體,1GB 易 OOM)
- 安裝 Docker(`curl -fsSL https://get.docker.com | sh`,需 Compose v2.24+)與 Tailscale:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --ssh
tailscale ip -4              # 記下本機 100.x.x.x
```

## 2. 取得程式碼與設定

```bash
git clone https://github.com/kencoolguy/GhostMeter.git ghostmeter && cd ghostmeter
cp .env.example .env
```

編輯 `.env`,至少設定:

```bash
POSTGRES_PASSWORD=<強密碼，勿用預設>
BIND_IP=<本機的 Tailscale IP，例如 100.x.x.x>
DEBUG=false
```

> `DATABASE_URL` 不必手動設;compose 會用 `POSTGRES_PASSWORD` 自動組出來。
> 前端走相對路徑 `/api/v1`,換網域不必重 build。

## 3. 部署

```bash
./deploy.sh
```

`deploy.sh` 會依序:套用 `docker-compose.prod.yml` overlay → build image → 起 postgres 並等 healthy → 跑 `alembic upgrade head` → 啟動全部服務 → 顯示狀態。

更新版本時直接跑 `./update.sh` —— 它會 `git pull` 最新 `dev`、檢查 `.env` 有 `BIND_IP`,再呼叫 `deploy.sh`(含新 migration)。

## 4. 驗證(在已連 Tailscale 的電腦)

```bash
http http://<BIND_IP>:8000/health                 # ✅ 走 tailnet 應該通
http --timeout=5 http://<公網IP>:8000/health        # ✅ 應 timeout = 沒裸奔
```

協議埠測試:用 EMS / 工具連 `<BIND_IP>` 的 `502`(Modbus)、`4840`(OPC UA)、`161`(SNMP)。

## 5. 前端對外(Cloudflare Tunnel + Access)

公網埠全鎖,所以用 **Cloudflare Tunnel**(純出站,不開任何入站埠)對外發布。
cloudflared sidecar 已內建在 `docker-compose.prod.yml`(profile `tunnel`),
`deploy.sh` 偵測到 `.env` 有 `CLOUDFLARE_TUNNEL_TOKEN` 才會啟動它——沒設 token
的部署完全不受影響。

> ⚠️ **先設 Access 再開 Hostname**。nginx 會把 `/api` 與 `/ws` 一併 proxy 給
> backend,而 API 本身沒有任何認證——Public Hostname 沒有 Access policy 擋著,
> 等於任何知道網址的人都能操控模擬器。

### Dashboard 端(Cloudflare Zero Trust)

1. **建 Tunnel**:Networks → Tunnels → Create a tunnel(connector 選
   cloudflared)→ 複製 token(`eyJ...` 長字串)。
2. **設 Public Hostname**:該 tunnel → Public Hostname → 你的網域/子網域 →
   service 填 `http://frontend:80`(同 compose network,用服務名)。
3. **設 Access policy(必做)**:Access → Applications → Add an application →
   Self-hosted → domain 填同一個 hostname → policy 設 Allow + Include →
   Emails → 你的 email。之後開網址會先看到 Cloudflare 登入頁(email OTP)。
   要讓 team member 用 Web UI,把他們的 email 一併加進這個 policy 即可
   (對方不需要 Cloudflare 帳號;同網域的人可改用 Emails ending in 一條涵蓋)。

### VM 端

```bash
echo 'CLOUDFLARE_TUNNEL_TOKEN=eyJ...' >> ~/ghostmeter/.env
cd ~/ghostmeter && ./update.sh        # deploy.sh 偵測 token → 啟動 cloudflared
docker logs ghostmeter-cloudflared-1 | tail   # 應看到 "Registered tunnel connection"
```

### 驗證

- 開 `https://<你的網域>` → 先被導到 Cloudflare Access 登入,通過後看到 UI
- Monitor 頁即時值正常(WS 走 same-origin `wss://<網域>/ws/monitor`,經 nginx
  proxy;v0.4.2 之後支援)
- 無痕視窗直接打 `https://<網域>/api/v1/templates` → 應被 Access 擋下(302 到
  登入頁),拿不到 JSON

## 6. 協議埠給 team member(Tailscale Node Sharing)

協議埠(`502` Modbus、`4840` OPC UA、`161` SNMP)只綁在 Tailscale IP 上,
team member 要用 EMS / 工具連設備,必須走 tailnet。用 **node sharing**
只分享 Linode 這一台機器,不必把人加進自己的 tailnet:

- 對方**只看得到這一台**,tailnet 裡其他裝置對他不存在
- 不佔免費方案的 user 名額,分享人數不限
- 被分享的機器預設被隔離,不能主動連回對方的網路

> 如果 team member 需要連多台機器或要雙向互連,才考慮改用
> 「邀請加入 tailnet」(免費方案上限 6 人,建議搭配 ACL group 限制權限)。

### 分享端(你)

1. [Admin console](https://login.tailscale.com/admin/machines) → Machines →
   Linode 那台 → ⋯ → **Share** → Copy share link 傳給對方(30 天有效)
2. 把機器的 Tailscale IP(`tailscale ip -4`,100.x.x.x)給對方

### 接收端(team member)

1. 點分享連結 → 用任何 email(Google / Microsoft / GitHub)註冊或登入
   Tailscale → 接受分享
2. 裝 Tailscale client 並登入**同一個帳號**
   (Windows:<https://tailscale.com/download/windows> 或
   `winget install tailscale.tailscale`)
3. EMS / 工具的設備 IP 填 Linode 的 Tailscale IP,例如 Modbus 連
   `<Tailscale IP>:502`

### 驗證與管理

- Windows 連線測試:`Test-NetConnection <Tailscale IP> -Port 502`
- 連不上最常見原因:登入的帳號跟接受邀請的帳號不同
- 收回權限:Machines → 該機器 → ⋯ → Share → 移除該 user,不影響其他人

## 7. 搬移到另一個環境(Migration)

整個系統需要搬的「資料」只有一份 —— PostgreSQL(`pgdata` volume)。
程式碼在 GitHub、設定在 `.env`(git-ignored,**不會**跟著 clone 過來)、
mosquitto 設定在 repo 裡;write events 只存在 in-memory ring buffer,
重啟本來就會清空,無法也不需要搬。所以整個移植 =
**git clone + 複製 `.env` + `pg_dump` / `pg_restore`** 三件事。

### 7.1 在來源機器匯出 DB

```bash
# 在 repo 目錄下,直接對容器 dump(不用管 host port 映射)
docker exec ghostmeter-postgres pg_dump -U ghostmeter -d ghostmeter -Fc > ghostmeter.dump
```

若 `.env` 改過 `POSTGRES_USER` / `POSTGRES_DB`,把參數換成一致的值。
DB 裡包含:templates(含自訂的)、devices、simulation configs、
MQTT broker 設定(Settings 頁存的)等全部狀態。

傳到新機器(走 Tailscale 最省事):

```bash
scp ghostmeter.dump <新機器>:~/
```

### 7.2 在新環境架好基礎環境

照本文件第 1–2 節:裝 Docker(要對外就裝 Tailscale)、clone repo、
`cp .env.example .env` 後設定 `POSTGRES_PASSWORD` / `BIND_IP` / `DEBUG=false`。
**把舊 `.env` 裡的 `CLOUDFLARE_TUNNEL_TOKEN`(若有)一併帶過去。**

注意:checkout 的 code 版本要 ≥ 來源機器的版本(dump 帶有 `alembic_version`,
新版 code 跑 migration 會自動補上;反過來舊 code 配新 dump 會壞)。

### 7.3 先起 postgres、還原、再 deploy

順序很重要:**先 restore 再跑 `deploy.sh`** —— alembic 看到 dump 帶來的
`alembic_version` 只會補跑更新的 migration,app 啟動時的 seed 檢查也會
發現內建模板已存在而跳過:

```bash
cd ~/ghostmeter
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d postgres
until [ "$(docker inspect -f '{{.State.Health.Status}}' ghostmeter-postgres)" = "healthy" ]; do sleep 2; done

# 還原(--clean --if-exists 讓重跑也安全)
docker exec -i ghostmeter-postgres pg_restore -U ghostmeter -d ghostmeter --clean --if-exists < ~/ghostmeter.dump

./deploy.sh
```

本機開發環境一樣,只是不加 `-f docker-compose.prod.yml`、`.env` 不用 `BIND_IP`。

### 7.4 驗證

```bash
http http://<BIND_IP>:8000/health
http http://<BIND_IP>:8000/api/v1/devices   # 舊裝置清單應該都在
```

### 7.5 搬完後要另外處理的事(不在 DB 裡)

- **Tailscale**:新機器是新 node,IP 會變 → `.env` 的 `BIND_IP` 要填新 IP,
  之前 node sharing 分享給 team member 的要重新 Share,EMS 端連線 IP 也要改。
- **Cloudflare Tunnel**:token 綁 tunnel 不綁機器,直接把舊 token 放進新
  `.env` 即可,connector 會在新機器重新註冊;舊機器記得停掉避免兩邊搶。
- **外部 MQTT broker**:broker 設定存在 DB 會跟著過去,但 broker 端若有做
  來源 IP 限制要更新。

> 另一個做法是直接 tar 整個 `pgdata` volume 搬過去(兩邊同為 PG 16 可行),
> 但 `pg_dump` 乾淨、不用停來源的 postgres、也不怕 volume 權限問題,建議用 dump。

## 相關檔案

- `docker-compose.prod.yml` — 部署 overlay,把 port 綁到 `BIND_IP`、postgres 不對外
- `deploy.sh` — build + migration + 啟動的一鍵腳本
- `update.sh` — `git pull` 最新 dev + 檢查 `.env` + 呼叫 `deploy.sh` 的更新腳本
- `.env.example` — `BIND_IP` 欄位說明
