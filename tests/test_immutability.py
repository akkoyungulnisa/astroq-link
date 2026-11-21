"""Unit tests verifying frozen dataclass immutability and No-Cloning guards."""

import copy
from dataclasses import FrozenInstanceError
import pytest

from astroq_link.core import (
    CipherBlock,
    NoCloningViolationError,
    QuantumTelemetryPacket,
    RollbackAction,
    SecurityIncident,
)


def test_telemetry_packet_is_immutable() -> None:
    pkt = QuantumTelemetryPacket(
        packet_id=1,
        altitude_m=1920.5,
        velocity_ms=45.0,
        pressure_hpa=802.1,
        qber=0.03,
        is_critical=False,
        status="NOMINAL",
    )
    with pytest.raises(FrozenInstanceError):
        pkt.qber = 0.01  # type: ignore[misc]


def test_no_cloning_violation_on_copy() -> None:
    pkt = QuantumTelemetryPacket(1, 2000.0, 15.0, 795.0, 0.02, False, "NOMINAL")
    block = CipherBlock(0, b"encrypted", "hash0", "mac0")

    with pytest.raises(NoCloningViolationError):
        copy.copy(pkt)

    with pytest.raises(NoCloningViolationError):
        copy.deepcopy(pkt)

    with pytest.raises(NoCloningViolationError):
        copy.copy(block)

    with pytest.raises(NoCloningViolationError):
        copy.deepcopy(block)


def test_audit_records_are_immutable() -> None:
    action = RollbackAction(step_index=0, action_type="ENCRYPT_CHUNK", block_hash="abc123")
    incident = SecurityIncident(tick=4, severity="CRITICAL_TAMPER", description="1-byte flip")

    with pytest.raises(FrozenInstanceError):
        action.step_index = 99  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        incident.severity = "LOW"  # type: ignore[misc]
