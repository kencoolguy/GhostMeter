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

## 5. 前端對外(Cloudflare Tunnel)

公網埠全鎖,所以用 **Cloudflare Tunnel**(純出站,不開任何入站埠)對外發布前端。在 Zero Trust → Networks → Tunnels 建 tunnel 取得 token,於 VM 加一個 service(可放 `docker-compose.override.yml` 或併入 prod overlay):

```yaml
services:
  cloudflared:
    image: cloudflare/cloudflared:latest
    command: tunnel run
    environment:
      TUNNEL_TOKEN: ${CLOUDFLARE_TUNNEL_TOKEN}
    restart: unless-stopped
    depends_on:
      - frontend
```

在 tunnel 的 Public Hostname 設定你的網域 → service `http://frontend:80`(同 compose network 用服務名),即取得公網 HTTPS 前端,且不暴露任何協議埠。

## 相關檔案

- `docker-compose.prod.yml` — 部署 overlay,把 port 綁到 `BIND_IP`、postgres 不對外
- `deploy.sh` — build + migration + 啟動的一鍵腳本
- `update.sh` — `git pull` 最新 dev + 檢查 `.env` + 呼叫 `deploy.sh` 的更新腳本
- `.env.example` — `BIND_IP` 欄位說明
