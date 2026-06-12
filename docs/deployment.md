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

## 相關檔案

- `docker-compose.prod.yml` — 部署 overlay,把 port 綁到 `BIND_IP`、postgres 不對外
- `deploy.sh` — build + migration + 啟動的一鍵腳本
- `update.sh` — `git pull` 最新 dev + 檢查 `.env` + 呼叫 `deploy.sh` 的更新腳本
- `.env.example` — `BIND_IP` 欄位說明
