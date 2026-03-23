from app.protocols.base import DeviceStats, ProtocolAdapter, RegisterInfo
from app.protocols.manager import ProtocolManager

protocol_manager = ProtocolManager()

__all__ = ["protocol_manager", "DeviceStats", "ProtocolAdapter", "RegisterInfo"]
