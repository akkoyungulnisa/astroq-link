"""2000m rocket/satellite flight simulator with blackout, priority scheduling, and QBER noise."""

from dataclasses import dataclass
import math
import random
from typing import Optional

from astroq_link.core import (
    CircularDoublyLinkedList,
    CriticalLIFOStack,
    PacketLifecycleRecord,
    PacketLifecycleState,
    PacketPriority,
    QuantumTelemetryPacket,
)
from .scheduler import PriorityAgingQueue, SchedulingPolicy


@dataclass
class MissionStats:
    total_generated: int = 0
    transmitted_live: int = 0
    buffered_in_stack: int = 0
    recovered_from_stack: int = 0
    dropped_overflow: int = 0
    link_switches: int = 0
    qber_breaches: int = 0
    dropped_duplicate: int = 0
    expired_packets: int = 0
    aged_promotions: int = 0


class TelemetryRouter:
    """
    2000m uçuş profili boyunca telemetri paketlerini sabit RAM'li
    CircularDoublyLinkedList tamponunda tutan, RF/Kuantum kesintilerinde
    yedek kanala O(1) geçiş yapan, paket yaşam döngüsü + TTL + duplicate
    kontrolü uygulayan ve seçilen politikaya (LIFO / FIFO / PRIORITY+Aging)
    göre kesinti sonrası kurtarma yapan yönlendirici.
    """

    QBER_THRESHOLD: float = 0.11

    def __init__(
        self,
        ring_capacity: int = 16,
        stack_capacity: int = 32,
        scheduling_policy: SchedulingPolicy = SchedulingPolicy.LIFO,
        aging_interval: float = 5.0,
        deduplicate: bool = True,
    ) -> None:
        self.scheduling_policy = scheduling_policy
        self.deduplicate = deduplicate

        self.onboard_ring: CircularDoublyLinkedList[QuantumTelemetryPacket] = (
            CircularDoublyLinkedList(max_capacity=ring_capacity, overwrite_on_full=True)
        )
        self.recovery_stack: CriticalLIFOStack[QuantumTelemetryPacket] = (
            CriticalLIFOStack(max_capacity=stack_capacity)
        )
        self.fifo_queue: CircularDoublyLinkedList[QuantumTelemetryPacket] = (
            CircularDoublyLinkedList(max_capacity=stack_capacity, overwrite_on_full=False)
        )
        self.priority_queue = PriorityAgingQueue(
            max_capacity=stack_capacity, aging_interval=aging_interval
        )

        self.comm_links: CircularDoublyLinkedList[str] = CircularDoublyLinkedList()
        self.comm_links.append("RF-PRIMARY-915MHz")
        self.comm_links.append("RF-BACKUP-OMNI")
        self.comm_links.append("QKD-OPTICAL-LINK")

        self.stats = MissionStats()
        self.ground_station_log: CircularDoublyLinkedList[QuantumTelemetryPacket] = (
            CircularDoublyLinkedList()
        )
        self.lifecycle_log: list[PacketLifecycleRecord] = []
        self._seen_packet_ids: set[int] = set()

    @property
    def active_link(self) -> str:
        head = self.comm_links.get_head()
        return head.data if head is not None else "NONE"

    def _record_lifecycle(
        self,
        packet: QuantumTelemetryPacket,
        state: PacketLifecycleState,
        timestamp: float,
        reason: str,
        effective_priority: Optional[PacketPriority] = None,
    ) -> None:
        base_prio = packet.priority or PacketPriority.NORMAL
        self.lifecycle_log.append(
            PacketLifecycleRecord(
                packet_id=packet.packet_id,
                state=state,
                timestamp=timestamp,
                base_priority=base_prio,
                effective_priority=effective_priority or base_prio,
                reason=reason,
            )
        )

    def switch_to_next_link(self) -> str:
        """Aktif haberleşme kanalı bozulduğunda O(1) sürede bir sonraki yedek kanala geçer."""
        self.comm_links.rotate_forward()
        self.stats.link_switches += 1
        return self.active_link

    def _enqueue_outage_packet(
        self, packet: QuantumTelemetryPacket, now: float, reason: str
    ) -> tuple[str, Optional[QuantumTelemetryPacket]]:
        if self.scheduling_policy == SchedulingPolicy.LIFO:
            if not self.recovery_stack.is_full():
                self.recovery_stack.push(packet)
                self.stats.buffered_in_stack += 1
                self._record_lifecycle(packet, PacketLifecycleState.BUFFERED, now, reason)
                return (f"BUFFERED_{reason}", None)
            self.stats.dropped_overflow += 1
            self._record_lifecycle(packet, PacketLifecycleState.DROPPED, now, "STACK_FULL")
            return ("DROPPED_STACK_FULL", None)

        if self.scheduling_policy == SchedulingPolicy.FIFO:
            if not self.fifo_queue.is_full():
                self.fifo_queue.append(packet)
                self.stats.buffered_in_stack += 1
                self._record_lifecycle(packet, PacketLifecycleState.BUFFERED, now, reason)
                return (f"BUFFERED_{reason}", None)
            self.stats.dropped_overflow += 1
            self._record_lifecycle(packet, PacketLifecycleState.DROPPED, now, "FIFO_FULL")
            return ("DROPPED_STACK_FULL", None)

        # PRIORITY + Aging modu
        accepted, decision_reason = self.priority_queue.push(packet, now)
        if accepted:
            self.stats.buffered_in_stack += 1
            self._record_lifecycle(
                packet, PacketLifecycleState.BUFFERED, now, f"{reason}:{decision_reason}"
            )
            return (f"BUFFERED_{reason}", None)

        self.stats.dropped_overflow += 1
        self._record_lifecycle(packet, PacketLifecycleState.DROPPED, now, decision_reason)
        return ("DROPPED_STACK_FULL", None)

    def _pop_recovery_packet(self, now: float) -> Optional[QuantumTelemetryPacket]:
        if self.scheduling_policy == SchedulingPolicy.LIFO:
            while not self.recovery_stack.is_empty():
                cand = self.recovery_stack.pop()
                if cand.is_expired(now):
                    self.stats.expired_packets += 1
                    self._record_lifecycle(cand, PacketLifecycleState.EXPIRED, now, "TTL_EXPIRED_IN_STACK")
                    continue
                return cand
            return None

        if self.scheduling_policy == SchedulingPolicy.FIFO:
            while not self.fifo_queue.is_empty():
                head = self.fifo_queue.get_head()
                assert head is not None
                cand = self.fifo_queue.remove_node(head)
                if cand.is_expired(now):
                    self.stats.expired_packets += 1
                    self._record_lifecycle(cand, PacketLifecycleState.EXPIRED, now, "TTL_EXPIRED_IN_FIFO")
                    continue
                return cand
            return None

        # PRIORITY + Aging modu
        prev_promotions = self.priority_queue.aged_promotions
        pkt, eff_prio, exp_cnt = self.priority_queue.pop(now)
        self.stats.expired_packets += exp_cnt
        self.stats.aged_promotions += self.priority_queue.aged_promotions - prev_promotions
        if pkt is not None and eff_prio is not None:
            self._record_lifecycle(
                pkt,
                PacketLifecycleState.TRANSMITTED,
                now,
                "SCHEDULED_PRIORITY_RECOVERY",
                effective_priority=eff_prio,
            )
        return pkt

    def process_packet(
        self,
        packet: QuantumTelemetryPacket,
        link_online: bool = True,
        current_time: Optional[float] = None,
    ) -> tuple[str, Optional[QuantumTelemetryPacket]]:
        """
        Gelen telemetri paketini işler:
        - Duplicate ve TTL süresi dolmuş paketleri eler.
        - Her geçerli paket sabit bellekli onboard_ring halkasına yazılır.
        - Bağlantı kesikse veya QBER sınırı aşıldıysa paket kurtarma tamponuna alınır.
        - Bağlantı geri geldiğinde aktif politikaya göre kurtarma paketi iletilir.
        """
        now = current_time if current_time is not None else packet.created_at
        self._record_lifecycle(packet, PacketLifecycleState.CREATED, now, "INGESTED")

        if self.deduplicate and packet.packet_id in self._seen_packet_ids:
            self.stats.dropped_duplicate += 1
            self._record_lifecycle(packet, PacketLifecycleState.DROPPED, now, "DUPLICATE_PACKET_ID")
            return ("DROPPED_DUPLICATE", None)
        self._seen_packet_ids.add(packet.packet_id)

        if packet.is_expired(now):
            self.stats.expired_packets += 1
            self._record_lifecycle(packet, PacketLifecycleState.EXPIRED, now, "TTL_EXPIRED_ON_ARRIVAL")
            return ("EXPIRED", None)

        self.stats.total_generated += 1
        self.onboard_ring.append(packet)

        qber_breach = packet.qber > self.QBER_THRESHOLD
        if qber_breach:
            self.stats.qber_breaches += 1

        if not link_online or qber_breach:
            self.switch_to_next_link()
            reason = "BLACKOUT" if not link_online else "QBER_BREACH"
            return self._enqueue_outage_packet(packet, now, reason)

        # Bağlantı sağlıklıysa önce tamponda bekleyen paketi kurtar
        recovered_pkt = self._pop_recovery_packet(now)
        if recovered_pkt is not None:
            self.ground_station_log.append(recovered_pkt)
            self.stats.recovered_from_stack += 1
            self._record_lifecycle(
                recovered_pkt, PacketLifecycleState.DELIVERED, now, "RECOVERED_POST_OUTAGE"
            )

        self._record_lifecycle(packet, PacketLifecycleState.TRANSMITTED, now, "LIVE_LINK_ACTIVE")
        self.ground_station_log.append(packet)
        self.stats.transmitted_live += 1
        self._record_lifecycle(packet, PacketLifecycleState.DELIVERED, now, "LIVE_DELIVERED")
        return ("TRANSMITTED", recovered_pkt)

    def simulate_ascent_mission(
        self,
        target_altitude: float = 2000.0,
        blackout_range: tuple[float, float] = (1880.0, 1940.0),
        seed: int = 42,
    ) -> MissionStats:
        """0m'den 2000m tepe noktasına (apogee) kadar uçuş ve kesinti simülasyonu yürütür."""
        rng = random.Random(seed)
        altitude = 0.0
        packet_id = 0
        mission_time = 0.0
        dt = 1.5

        while altitude <= target_altitude:
            packet_id += 1
            mission_time = round(mission_time + dt, 2)
            progress = altitude / target_altitude
            velocity = round(max(12.0, 145.0 * (1.0 - 0.85 * progress)), 2)
            pressure = round(1013.25 * math.exp(-altitude / 8434.5), 2)

            in_blackout = blackout_range[0] <= altitude <= blackout_range[1]
            in_qber_spike = 1580.0 <= altitude <= 1620.0

            if in_qber_spike:
                qber = round(rng.uniform(0.14, 0.21), 3)
                status = "QUANTUM_BREACH"
                critical = True
                priority = PacketPriority.CRITICAL
            elif in_blackout:
                qber = round(rng.uniform(0.02, 0.05), 3)
                status = "RF_BLACKOUT"
                critical = True
                priority = PacketPriority.CRITICAL
            elif altitude >= (target_altitude - 30.0):
                qber = round(rng.uniform(0.015, 0.045), 3)
                status = "APOGEE_APPROACH"
                critical = True
                priority = PacketPriority.CRITICAL
            elif 900.0 <= altitude <= 1100.0:
                qber = round(rng.uniform(0.015, 0.045), 3)
                status = "MAX_Q_TELEMETRY"
                critical = False
                priority = PacketPriority.IMPORTANT
            else:
                qber = round(rng.uniform(0.015, 0.045), 3)
                status = "NOMINAL"
                critical = False
                priority = PacketPriority.NORMAL

            pkt = QuantumTelemetryPacket(
                packet_id=packet_id,
                altitude_m=round(altitude, 1),
                velocity_ms=velocity,
                pressure_hpa=pressure,
                qber=qber,
                is_critical=critical,
                status=status,
                priority=priority,
                created_at=mission_time,
                ttl_seconds=60.0,
            )

            self.process_packet(pkt, link_online=(not in_blackout), current_time=mission_time)
            altitude += velocity * dt

        return self.stats
