from app.protocols.base import DeviceStats, ProtocolAdapter, RegisterInfo
from app.protocols.manager import ProtocolManager

protocol_manager = ProtocolManager()


def get_supported_fault_types(protocol: str) -> frozenset[str]:
    """Fault types a protocol can simulate (class-level capability lookup).

    Reads the adapter class declarations so it works without a running
    adapter instance (e.g. before lifespan startup, or in API tests).
    Unknown protocols fall back to the base default (all types).
    """
    # Imported lazily: the adapter modules pull in heavy protocol stacks
    # (asyncua, bacpypes3, pysnmp) that not every importer of this package needs.
    from app.protocols.bacnet_agent import BacnetAdapter
    from app.protocols.modbus_tcp import ModbusTcpAdapter
    from app.protocols.mqtt_adapter import MqttAdapter
    from app.protocols.opcua_agent import OpcUaAdapter
    from app.protocols.snmp_agent import SnmpAdapter

    adapter_classes: dict[str, type[ProtocolAdapter]] = {
        "modbus_tcp": ModbusTcpAdapter,
        "mqtt": MqttAdapter,
        "snmp": SnmpAdapter,
        "opcua": OpcUaAdapter,
        "bacnet": BacnetAdapter,
    }
    cls = adapter_classes.get(protocol)
    return cls.supported_fault_types if cls else ProtocolAdapter.supported_fault_types


__all__ = [
    "protocol_manager",
    "get_supported_fault_types",
    "DeviceStats",
    "ProtocolAdapter",
    "RegisterInfo",
]
