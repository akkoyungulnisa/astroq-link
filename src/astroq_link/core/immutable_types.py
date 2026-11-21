"""Frozen dataclass definitions enforcing No-Cloning and data immutability."""

from dataclasses import dataclass
from .exceptions import NoCloningViolationError


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
