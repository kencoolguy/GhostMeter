#!/usr/bin/env bash
# GhostMeter Demo Startup Script
# 啟動 Docker containers + 建立虛擬電表 + 設定模擬數據 + 驗證 Modbus 讀取
#
# Usage: bash scripts/start-demo.sh
# Prerequisites: docker compose, python3.12, pymodbus (pip3.12 install pymodbus)

set -euo pipefail
cd "$(dirname "$0")/.."

API="http://localhost:8000/api/v1"
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ──────────────────────────────────────────────
# Step 1: Start Docker containers
# ──────────────────────────────────────────────
info "Step 1: Starting Docker containers..."
docker compose up -d --build 2>&1 | tail -5

info "Waiting for backend to become healthy..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        info "Backend is healthy!"
        break
    fi
    if [ "$i" -eq 30 ]; then
        error "Backend failed to start within 30 seconds"
        docker logs ghostmeter-backend --tail 20
        exit 1
    fi
    sleep 1
done

echo ""
info "Running containers:"
docker ps --filter "name=ghostmeter" --format "  {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""

# ──────────────────────────────────────────────
# Step 2: Check existing devices or create one
# ──────────────────────────────────────────────
info "Step 2: Checking existing devices..."
DEVICES=$(curl -sf "${API}/devices")
DEVICE_COUNT=$(echo "$DEVICES" | python3.12 -c "import sys,json; print(len(json.load(sys.stdin)['data']))")

if [ "$DEVICE_COUNT" -gt 0 ]; then
    info "Found ${DEVICE_COUNT} existing device(s):"
    echo "$DEVICES" | python3.12 -c "
import sys, json
for d in json.load(sys.stdin)['data']:
    print(f\"  - {d['name']} (slave={d['slave_id']}, status={d['status']}, id={d['id']})\")
"
    # Use first device
    DEVICE_ID=$(echo "$DEVICES" | python3.12 -c "import sys,json; print(json.load(sys.stdin)['data'][0]['id'])")
    DEVICE_STATUS=$(echo "$DEVICES" | python3.12 -c "import sys,json; print(json.load(sys.stdin)['data'][0]['status'])")
else
    info "No devices found. Creating a virtual meter (SDM120, slave_id=1)..."

    # Get SDM120 template ID
    TEMPLATE_ID=$(curl -sf "${API}/templates" | python3.12 -c "
import sys, json
for t in json.load(sys.stdin)['data']:
    if 'SDM120' in t['name']:
        print(t['id'])
        break
")

    if [ -z "$TEMPLATE_ID" ]; then
        error "SDM120 template not found!"
        exit 1
    fi

    RESULT=$(curl -sf -X POST "${API}/devices" \
        -H "Content-Type: application/json" \
        -d "{\"name\": \"Test Meter 1\", \"template_id\": \"${TEMPLATE_ID}\", \"slave_id\": 1}")

    DEVICE_ID=$(echo "$RESULT" | python3.12 -c "import sys,json; print(json.load(sys.stdin)['data']['id'])")
    DEVICE_STATUS="stopped"
    info "Created device: ${DEVICE_ID}"
fi

# ──────────────────────────────────────────────
# Step 3: Configure simulation (random mode)
# ──────────────────────────────────────────────
info "Step 3: Configuring simulation parameters..."
curl -sf -X PUT "${API}/devices/${DEVICE_ID}/simulation" \
    -H "Content-Type: application/json" \
    -d '{
    "configs": [
        {"register_name": "voltage",      "data_mode": "random", "mode_params": {"base": 220, "amplitude": 5}},
        {"register_name": "current",      "data_mode": "random", "mode_params": {"base": 10,  "amplitude": 5}},
        {"register_name": "active_power", "data_mode": "random", "mode_params": {"base": 2000, "amplitude": 500}},
        {"register_name": "frequency",    "data_mode": "random", "mode_params": {"base": 60,  "amplitude": 0.1}},
        {"register_name": "power_factor", "data_mode": "random", "mode_params": {"base": 0.95, "amplitude": 0.05}}
    ]
}' > /dev/null

info "Simulation configured (random mode)"

# ──────────────────────────────────────────────
# Step 4: Start device simulation
# ──────────────────────────────────────────────
if [ "$DEVICE_STATUS" = "running" ]; then
    info "Step 4: Device already running, restarting to apply new config..."
    curl -sf -X POST "${API}/devices/${DEVICE_ID}/stop" > /dev/null
    sleep 1
fi

info "Step 4: Starting device simulation..."
curl -sf -X POST "${API}/devices/${DEVICE_ID}/start" > /dev/null
info "Device simulation started!"

# ──────────────────────────────────────────────
# Step 5: Verify Modbus TCP read
# ──────────────────────────────────────────────
info "Step 5: Verifying Modbus TCP (waiting 3 seconds for data generation)..."
sleep 3

python3.12 -c "
from pymodbus.client import ModbusTcpClient
import struct

client = ModbusTcpClient('localhost', port=502)
if not client.connect():
    print('  ERROR: Cannot connect to Modbus TCP on port 502')
    exit(1)

registers = [
    (0, 'Voltage', 'V'),
    (6, 'Current', 'A'),
    (12, 'Active Power', 'W'),
    (30, 'Power Factor', ''),
    (70, 'Frequency', 'Hz'),
    (342, 'Total Energy', 'kWh'),
]

all_ok = True
for addr, name, unit in registers:
    result = client.read_input_registers(addr, count=2, device_id=1)
    if not result.isError():
        raw = struct.pack('>HH', result.registers[0], result.registers[1])
        val = struct.unpack('>f', raw)[0]
        status = '✓' if val != 0 else '○'
        if val == 0 and name in ('Voltage', 'Current', 'Active Power'):
            all_ok = False
        print(f'  {status} {name:20s} (addr={addr:3d}): {val:10.2f} {unit}')
    else:
        all_ok = False
        print(f'  ✗ {name:20s} (addr={addr:3d}): READ ERROR')

client.close()

if not all_ok:
    print()
    print('  WARNING: Some registers returned 0 — check backend logs:')
    print('    docker logs ghostmeter-backend --tail 20')
"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
info "GhostMeter is ready!"
echo ""
echo "  Web UI:       http://localhost:3002"
echo "  Backend API:  http://localhost:8000/docs"
echo "  Modbus TCP:   localhost:502 (slave_id=1)"
echo ""
echo "  To test with pymodbus:"
echo "    python3.12 -c \"from pymodbus.client import ModbusTcpClient; import struct"
echo "    c = ModbusTcpClient('localhost', 502); c.connect()"
echo "    r = c.read_input_registers(0, count=2, device_id=1)"
echo "    print(struct.unpack('>f', struct.pack('>HH', *r.registers)))\""
echo ""
echo "  To stop:"
echo "    docker compose down"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
