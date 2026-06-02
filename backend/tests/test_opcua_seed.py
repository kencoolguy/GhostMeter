"""Validate the OPC UA built-in template and profile seed JSON files."""

import json
from pathlib import Path

SEED = Path(__file__).parent.parent / "app" / "seed"


def test_opcua_template_seed_valid():
    data = json.loads((SEED / "opcua_energy_meter.json").read_text())
    assert data["name"] == "Energy Meter (OPC UA)"
    assert data["protocol"] == "opcua"
    assert len(data["registers"]) == 11
    addrs = set()
    for reg in data["registers"]:
        assert reg["name"]                    # OPC UA needs a real name
        assert reg["oid"] is None             # no OID for OPC UA
        key = (reg["address"], reg["function_code"])
        assert key not in addrs, f"duplicate (address, fc): {key}"
        addrs.add(key)
