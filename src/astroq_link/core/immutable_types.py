"""Frozen dataclass definitions enforcing No-Cloning and data immutability."""

from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Optional
from .exceptions import NoCloningViolationError


class PacketPriority(IntEnum):
    """Telemetri paket öncelik seviyeleri."""
    NORMAL = 1
    IMPORTANT = 2
    CRITICAL = 3


class PacketLifecycleState(str, Enum):
    """Paket yaşam döngüsü durumları."""
    CREATED = "CREATED"
    BUFFERED = "BUFFERED"
    TRANSMITTED = "TRANSMITTED"
    DELIVERED = "DELIVERED"
    DROPPED = "DROPPED"
    EXPIRED = "EXPIRED"
    RETRYING = "RETRYING"


@dataclass(frozen=True)
class PacketLifecycleRecord:
    """Her paket geçişinin zaman damgalı ve gerekçeli denetim kaydı."""
    packet_id: int
    state: PacketLifecycleState
    timestamp: float
    base_priority: PacketPriority
    effective_priority: PacketPriority
    reason: str


@dataclass(frozen=True)
class QuantumTelemetryPacket:
    """Dokunulmaz ve kopyalanamaz (No-Cloning) kuantum telemetri paketi."""
    packet_id: int
    altitude_m: float
    velocity_ms: float
    pressure_hpa: float
    qber: float
    is_critical: bool
    status: str
    priority: Optional[PacketPriority] = None
    created_at: float = 0.0
    ttl_seconds: Optional[float] = None

    def __post_init__(self) -> None:
        if self.priority is None:
            resolved = PacketPriority.CRITICAL if self.is_critical else PacketPriority.NORMAL
            object.__setattr__(self, "priority", resolved)
        elif self.priority == PacketPriority.CRITICAL and not self.is_critical:
            object.__setattr__(self, "is_critical", True)

    def is_expired(self, current_time: float) -> bool:
        """Paketin TTL süresinin dolup dolmadığını kontrol eder."""
        if self.ttl_seconds is None:
            return False
        return (current_time - self.created_at) > self.ttl_seconds

    def __copy__(self):
        raise NoCloningViolationError(
            f"Pkt#{self.packet_id}: Kuantum telemetri durumu kopyalanamaz (No-Cloning Theorem)."
        )

    def __deepcopy__(self, memo):
        raise NoCloningViolationError(
            f"Pkt#{self.packet_id}: Kuantum telemetri durumu derin kopyalanamaz (No-Cloning Theorem)."
        )


@dataclass(frozen=True)
class CipherBlock:
    """PQC dairesel şifreleme zincirindeki değiştirilemez veri bloğu."""
    index: int
    payload: bytes
    block_hash: str
    chained_mac: str

    def __copy__(self):
        raise NoCloningViolationError(
            f"Block#{self.index}: Mühürlü şifreli blok bellekte kopyalanamaz."
        )

    def __deepcopy__(self, memo):
        raise NoCloningViolationError(
            f"Block#{self.index}: Mühürlü şifreli blok bellekte derin kopyalanamaz."
        )


@dataclass(frozen=True)
class RollbackAction:
    """Atomik geri alma (Rollback) yığını için işlem kaydı."""
    step_index: int
    action_type: str
    block_hash: str


@dataclass(frozen=True)
class SecurityIncident:
    """Çevrimdışı siber savunma ve SOC öncelikli alarm kaydı."""
    tick: int
    severity: str
    description: str
