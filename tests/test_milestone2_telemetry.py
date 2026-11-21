"""Milestone 2 (P1): Packet priority, lifecycle, TTL, deduplication, aging, and strategy comparison."""

from astroq_link.core import (
    PacketLifecycleState,
    PacketPriority,
    QuantumTelemetryPacket,
)
from astroq_link.engine import (
    PriorityAgingQueue,
    SchedulingPolicy,
    TelemetryRouter,
    compare_scheduling_strategies,
)


def _make_pkt(
    pkt_id: int,
    priority: PacketPriority = PacketPriority.NORMAL,
    created_at: float = 0.0,
    ttl: float | None = None,
) -> QuantumTelemetryPacket:
    return QuantumTelemetryPacket(
        packet_id=pkt_id,
        altitude_m=1200.0 + pkt_id,
        velocity_ms=45.0,
        pressure_hpa=870.0,
        qber=0.02,
        is_critical=(priority == PacketPriority.CRITICAL),
        status="TEST",
        priority=priority,
        created_at=created_at,
        ttl_seconds=ttl,
    )


def test_duplicate_packet_detection_and_lifecycle() -> None:
    router = TelemetryRouter()
    pkt = _make_pkt(101, PacketPriority.IMPORTANT, created_at=1.0)

    status1, _ = router.process_packet(pkt, link_online=True, current_time=1.0)
    status2, _ = router.process_packet(pkt, link_online=True, current_time=1.5)

    assert status1 == "TRANSMITTED"
    assert status2 == "DROPPED_DUPLICATE"
    assert router.stats.dropped_duplicate == 1

    states = [r.state for r in router.lifecycle_log if r.packet_id == 101]
    assert PacketLifecycleState.CREATED in states
    assert PacketLifecycleState.TRANSMITTED in states
    assert PacketLifecycleState.DELIVERED in states
    assert PacketLifecycleState.DROPPED in states


def test_ttl_expiration_on_arrival_and_in_buffer() -> None:
    router = TelemetryRouter(scheduling_policy=SchedulingPolicy.PRIORITY)

    # 1. Geldiği anda süresi dolmuş paket
    stale_arrival = _make_pkt(1, PacketPriority.NORMAL, created_at=0.0, ttl=5.0)
    status_stale, _ = router.process_packet(stale_arrival, link_online=True, current_time=10.0)
    assert status_stale == "EXPIRED"

    # 2. Blackout sırasında kuyruğa giren ve beklerken TTL süresi dolan paket
    short_ttl_pkt = _make_pkt(2, PacketPriority.NORMAL, created_at=12.0, ttl=3.0)
    valid_pkt = _make_pkt(3, PacketPriority.IMPORTANT, created_at=13.0, ttl=20.0)
    assert router.process_packet(short_ttl_pkt, link_online=False, current_time=12.0)[0] == "BUFFERED_BLACKOUT"
    assert router.process_packet(valid_pkt, link_online=False, current_time=13.0)[0] == "BUFFERED_BLACKOUT"

    # T=18.0'da bağlantı geri gelir: pkt#2 (ttl=3s) elenmeli, pkt#3 kurtarılmalı
    live_pkt = _make_pkt(4, PacketPriority.NORMAL, created_at=18.0, ttl=20.0)
    _, recovered = router.process_packet(live_pkt, link_online=True, current_time=18.0)

    assert recovered is not None
    assert recovered.packet_id == 3
    assert router.stats.expired_packets == 2


def test_starvation_prevention_aging_promotes_normal_packets() -> None:
    queue = PriorityAgingQueue(max_capacity=10, aging_interval=5.0)

    # T=0'da NORMAL paket kuyruğa girer
    normal_pkt = _make_pkt(1, PacketPriority.NORMAL, created_at=0.0)
    queue.push(normal_pkt, current_time=0.0)

    # T=11'de (11s bekleme -> +2 terfi -> etkin öncelik CRITICAL) yeni bir CRITICAL paket gelir
    crit_pkt = _make_pkt(2, PacketPriority.CRITICAL, created_at=11.0)
    queue.push(crit_pkt, current_time=11.0)

    # Yaşlandırma sayesinde açlık önlenir ve uzun süredir bekleyen pkt#1 önce çıkar
    first_out, eff_prio, _ = queue.pop(current_time=11.0)
    assert first_out is not None
    assert first_out.packet_id == 1
    assert eff_prio == PacketPriority.CRITICAL
    assert queue.aged_promotions == 1


def test_priority_preemption_evicts_low_priority_when_full() -> None:
    queue = PriorityAgingQueue(max_capacity=2, aging_interval=50.0)
    queue.push(_make_pkt(1, PacketPriority.NORMAL, created_at=1.0), current_time=1.0)
    queue.push(_make_pkt(2, PacketPriority.NORMAL, created_at=2.0), current_time=2.0)

    # Kapasite doluyken CRITICAL paket geldiğinde en eski NORMAL paketi düşürmeli
    accepted, reason = queue.push(_make_pkt(3, PacketPriority.CRITICAL, created_at=3.0), current_time=3.0)
    assert accepted is True
    assert reason == "PREEMPTED_LOW_PRIORITY"
    assert queue.evicted_low_priority == 1

    top, _, _ = queue.pop(current_time=3.0)
    assert top is not None and top.packet_id == 3


def test_fifo_lifo_and_priority_strategy_comparison() -> None:
    workload = [
        (_make_pkt(1, PacketPriority.NORMAL, created_at=1.0, ttl=30.0), False),
        (_make_pkt(2, PacketPriority.CRITICAL, created_at=2.0, ttl=30.0), False),
        (_make_pkt(3, PacketPriority.NORMAL, created_at=3.0, ttl=30.0), False),
        (_make_pkt(4, PacketPriority.IMPORTANT, created_at=4.0, ttl=30.0), False),
        # T=5.0'da bağlantı geri gelir
        (_make_pkt(5, PacketPriority.NORMAL, created_at=5.0, ttl=30.0), True),
    ]

    comparison = compare_scheduling_strategies(
        workload, buffer_capacity=2, aging_interval=10.0, stale_threshold_seconds=2.5
    )

    # Kapasite 2 olduğunda:
    # FIFO ilk iki paketi (1, 2) tutar ve önce eski olan pkt#1'i (stale) basar
    assert comparison[SchedulingPolicy.FIFO].first_post_blackout_packet_id == 1

    # LIFO ilk iki paketi (1, 2) tutar ve en güncel olan pkt#2'yi (CRITICAL) ilk basar
    assert comparison[SchedulingPolicy.LIFO].first_post_blackout_packet_id == 2

    # PRIORITY NORMAL paketleri (1, 3) eleyip CRITICAL (2) ve IMPORTANT (4) paketleri korur
    prio_res = comparison[SchedulingPolicy.PRIORITY]
    assert prio_res.first_post_blackout_packet_id == 2
    assert prio_res.critical_delivered >= 1