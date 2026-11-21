"""Unit tests for TelemetryRouter and AutonomousEdgeShield."""

from astroq_link.core import QuantumTelemetryPacket
from astroq_link.engine import AutonomousEdgeShield, TelemetryRouter


def test_telemetry_router_blackout_lifo_recovery() -> None:
    router = TelemetryRouter(ring_capacity=8, stack_capacity=16)

    # T=1: Normal iletişim
    p1 = QuantumTelemetryPacket(1, 1850.0, 40.0, 810.0, 0.02, False, "NOMINAL")
    status1, rec1 = router.process_packet(p1, link_online=True)
    assert status1 == "TRANSMITTED"
    assert rec1 is None

    # T=2 ve T=3: Sinyal kopması (Blackout) -> paketler LIFO Stack'e alınmalı
    p2 = QuantumTelemetryPacket(2, 1900.0, 35.0, 804.0, 0.03, True, "RF_BLACKOUT")
    p3 = QuantumTelemetryPacket(3, 1935.0, 30.0, 800.0, 0.03, True, "RF_BLACKOUT")
    assert router.process_packet(p2, link_online=False)[0] == "BUFFERED_BLACKOUT"
    assert router.process_packet(p3, link_online=False)[0] == "BUFFERED_BLACKOUT"
    assert router.recovery_stack.size == 2

    # T=4: Bağlantı geri geldiğinde Stack'ten EN GÜNCEL paket (p3) ilk sırada kurtarılmalı
    p4 = QuantumTelemetryPacket(4, 1960.0, 25.0, 798.0, 0.02, False, "NOMINAL")
    status4, rec4 = router.process_packet(p4, link_online=True)
    assert status4 == "TRANSMITTED"
    assert rec4 is not None
    assert rec4.packet_id == 3
    assert rec4.altitude_m == 1935.0


def test_telemetry_router_qber_breach_switches_link() -> None:
    router = TelemetryRouter()
    initial_link = router.active_link

    breach_pkt = QuantumTelemetryPacket(10, 1600.0, 50.0, 835.0, 0.19, True, "QUANTUM_BREACH")
    status, _ = router.process_packet(breach_pkt, link_online=True)

    assert status == "BUFFERED_QBER_BREACH"
    assert router.active_link != initial_link
    assert router.stats.qber_breaches == 1


def test_full_2000m_ascent_simulation() -> None:
    router = TelemetryRouter()
    stats = router.simulate_ascent_mission(target_altitude=2000.0)

    assert stats.total_generated > 0
    assert stats.buffered_in_stack > 0
    assert stats.recovered_from_stack > 0


def test_offline_shield_key_zeroization_and_tamper_rollback() -> None:
    shield = AutonomousEdgeShield(passphrase="OtonomKalkan2026!", ring_slots=3)

    # T=1: Çevrimiçi normal işlem
    res1 = shield.process_frame(1, b"FRAME_01", internet_online=True)
    assert res1["status"] == "SEALED_OK"

    # Bir önceki slotun belleği güvenlik gereği sıfırlanmış olmalı (Forward Secrecy)
    head_node = shield.key_ring.get_head()
    assert head_node is not None and head_node.prev is not None
    assert bytes(head_node.prev.data.key_buffer) == b"\x00" * 32

    # T=2 ve T=3: İnternet kesik iken saldırı enjeksiyonu -> Rollback yapılmalı ve alarm yığına alınmalı
    res2 = shield.process_frame(2, b"FRAME_02", internet_online=False, simulate_tamper=True)
    res3 = shield.process_frame(3, b"FRAME_03", internet_online=False, simulate_tamper=True)
    assert res2["status"] == "TAMPER_BLOCKED"
    assert res3["status"] == "TAMPER_BLOCKED"
    assert shield.soc_alert_stack.size == 2

    # T=4: İnternet geri geldiğinde en son saldırı (T=3) SOC merkezine ilk sırada iletilmeli
    res4 = shield.process_frame(4, b"FRAME_04", internet_online=True, simulate_tamper=False)
    alerts = res4["flushed_alerts"]
    assert isinstance(alerts, list) and len(alerts) == 2
    assert alerts[0].tick == 3
    assert alerts[1].tick == 2