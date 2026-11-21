"""Priority-aware telemetry scheduling, aging (starvation prevention), and strategy comparison."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence

from astroq_link.core import (
    CircularDoublyLinkedList,
    CriticalLIFOStack,
    PacketPriority,
    QuantumTelemetryPacket,
)


class SchedulingPolicy(str, Enum):
    """Desteklenen tampon kurtarma ve paket zamanlama politikaları."""
    FIFO = "FIFO"
    LIFO = "LIFO"
    PRIORITY = "PRIORITY"


@dataclass
class _ScheduledEntry:
    packet: QuantumTelemetryPacket
    enqueued_at: float
    seq: int


class PriorityAgingQueue:
    """
    Sıfır dış bağımlılıklı, açlık önleme (aging) destekli öncelik kuyruğu.
    - Uzun süre bekleyen NORMAL/IMPORTANT paketlerin etkin önceliğini yükselterek
      sürekli CRITICAL akışı altında açlık (starvation) oluşmasını önler.
    - Kapasite dolduğunda gelen yüksek öncelikli paket için en düşük öncelikli
      eski paketi düşürür (priority-aware eviction).
    """

    def __init__(self, max_capacity: int = 32, aging_interval: float = 5.0) -> None:
        if max_capacity <= 0:
            raise ValueError("max_capacity pozitif olmalıdır.")
        self.max_capacity = max_capacity
        self.aging_interval = aging_interval
        self._entries: CircularDoublyLinkedList[_ScheduledEntry] = CircularDoublyLinkedList()
        self._seq_counter: int = 0
        self.aged_promotions: int = 0
        self.evicted_low_priority: int = 0

    @property
    def size(self) -> int:
        return self._entries.size

    def is_empty(self) -> bool:
        return self._entries.is_empty()

    def is_full(self) -> bool:
        return self._entries.size >= self.max_capacity

    def effective_priority(self, entry: _ScheduledEntry, current_time: float) -> PacketPriority:
        """Bekleme süresine göre yaşlandırma (aging) uygulanmış etkin önceliği hesaplar."""
        base = int(entry.packet.priority or PacketPriority.NORMAL)
        if self.aging_interval <= 0:
            return PacketPriority(base)
        wait_time = max(0.0, current_time - entry.enqueued_at)
        promotions = int(wait_time // self.aging_interval)
        boosted = min(int(PacketPriority.CRITICAL), base + promotions)
        return PacketPriority(boosted)

    def push(self, packet: QuantumTelemetryPacket, current_time: float) -> tuple[bool, str]:
        """
        Paketi öncelik kuyruğuna ekler.
        Dönüş: (kabul_edildi_mi, karar_gerekçesi)
        """
        self._seq_counter += 1
        incoming = _ScheduledEntry(packet=packet, enqueued_at=current_time, seq=self._seq_counter)

        if not self.is_full():
            self._entries.append(incoming)
            return True, "QUEUED_PRIORITY"

        # Tampon doluysa en düşük etkin öncelikli kurban düğümü bul
        incoming_prio = int(packet.priority or PacketPriority.NORMAL)
        victim_node = None
        victim_key: Optional[tuple[int, float, int]] = None

        curr = self._entries.head
        for _ in range(self._entries.size):
            assert curr is not None
            eff = int(self.effective_priority(curr.data, current_time))
            # Daha düşük öncelikli, eşitlikte daha eski paket kurban seçilir
            cand_key = (eff, curr.data.enqueued_at, curr.data.seq)
            if victim_key is None or cand_key < victim_key:
                victim_key = cand_key
                victim_node = curr
            curr = curr.next

        if victim_node is not None and victim_key is not None and incoming_prio > victim_key[0]:
            self._entries.remove_node(victim_node)
            self._entries.append(incoming)
            self.evicted_low_priority += 1
            return True, "PREEMPTED_LOW_PRIORITY"

        return False, "DROPPED_PRIORITY_FULL"

    def pop(
        self, current_time: float
    ) -> tuple[Optional[QuantumTelemetryPacket], Optional[PacketPriority], int]:
        """
        Süresi dolmuş (TTL) paketleri ayıklar, kalanlar arasından en yüksek etkin
        öncelikli paketi çıkarır.
        Dönüş: (seçilen_paket, etkin_öncelik, ayıklanan_expired_sayısı)
        """
        expired_count = 0

        while not self._entries.is_empty():
            best_node = None
            best_key: Optional[tuple[int, float, int]] = None
            best_eff: PacketPriority = PacketPriority.NORMAL

            curr = self._entries.head
            for _ in range(self._entries.size):
                assert curr is not None
                if curr.data.packet.is_expired(current_time):
                    best_node = curr
                    break
                eff = self.effective_priority(curr.data, current_time)
                # Yüksek öncelik önce; eşitlikte daha erken gelen (FIFO) önce
                cand_key = (int(eff), -curr.data.enqueued_at, -curr.data.seq)
                if best_key is None or cand_key > best_key:
                    best_key = cand_key
                    best_node = curr
                    best_eff = eff
                curr = curr.next

            assert best_node is not None
            entry = self._entries.remove_node(best_node)
            if entry.packet.is_expired(current_time):
                expired_count += 1
                continue

            base_prio = entry.packet.priority or PacketPriority.NORMAL
            if best_eff > base_prio:
                self.aged_promotions += 1
            return entry.packet, best_eff, expired_count

        return None, None, expired_count


@dataclass(frozen=True)
class StrategyBenchmarkResult:
    """FIFO, LIFO ve Priority Queue karşılaştırması için ölçüm çıktısı."""
    policy: SchedulingPolicy
    total_packets: int
    delivered_count: int
    critical_delivered: int
    dropped_or_expired: int
    packet_loss_rate: float
    first_post_blackout_packet_id: Optional[int]
    first_critical_recovery_latency: Optional[float]
    avg_critical_latency: float
    stale_packet_rate: float
    peak_buffer_occupancy: int
    aged_promotions: int
    delivery_order_sample: tuple[int, ...]


def compare_scheduling_strategies(
    workload: Sequence[tuple[QuantumTelemetryPacket, bool]],
    buffer_capacity: int = 16,
    aging_interval: float = 4.0,
    stale_threshold_seconds: float = 12.0,
) -> dict[SchedulingPolicy, StrategyBenchmarkResult]:
    """
    Aynı telemetri iş yükünü (paket, link_online) FIFO, LIFO ve PRIORITY
    politikaları üzerinde çalıştırarak teslim sırası, kritik gecikme,
    kayıp oranı ve bayat (stale) paket oranlarını karşılaştırır.
    """
    results: dict[SchedulingPolicy, StrategyBenchmarkResult] = {}

    for policy in (SchedulingPolicy.FIFO, SchedulingPolicy.LIFO, SchedulingPolicy.PRIORITY):
        fifo_buf: CircularDoublyLinkedList[QuantumTelemetryPacket] = CircularDoublyLinkedList(
            max_capacity=buffer_capacity, overwrite_on_full=False
        )
        lifo_buf: CriticalLIFOStack[QuantumTelemetryPacket] = CriticalLIFOStack(
            max_capacity=buffer_capacity
        )
        prio_buf = PriorityAgingQueue(
            max_capacity=buffer_capacity, aging_interval=aging_interval
        )

        delivered_ids: list[int] = []
        critical_latencies: list[float] = []
        dropped_or_expired = 0
        stale_delivered = 0
        peak_occupancy = 0
        blackout_ended_at: Optional[float] = None
        first_post_blackout_id: Optional[int] = None
        first_critical_latency: Optional[float] = None
        was_in_blackout = False

        for pkt, link_online in workload:
            now = pkt.created_at

            if not link_online:
                was_in_blackout = True
                if pkt.is_expired(now):
                    dropped_or_expired += 1
                    continue

                if policy == SchedulingPolicy.FIFO:
                    if not fifo_buf.is_full():
                        fifo_buf.append(pkt)
                    else:
                        dropped_or_expired += 1
                    peak_occupancy = max(peak_occupancy, fifo_buf.size)
                elif policy == SchedulingPolicy.LIFO:
                    if not lifo_buf.is_full():
                        lifo_buf.push(pkt)
                    else:
                        dropped_or_expired += 1
                    peak_occupancy = max(peak_occupancy, lifo_buf.size)
                else:
                    accepted, _ = prio_buf.push(pkt, now)
                    if not accepted:
                        dropped_or_expired += 1
                    peak_occupancy = max(peak_occupancy, prio_buf.size)
                continue

            # Link online
            if was_in_blackout:
                blackout_ended_at = now
                was_in_blackout = False

            # Bağlantı aktifken önce tampondan 1 paket kurtar
            recovered: Optional[QuantumTelemetryPacket] = None
            if policy == SchedulingPolicy.FIFO:
                while not fifo_buf.is_empty():
                    head = fifo_buf.get_head()
                    assert head is not None
                    cand = fifo_buf.remove_node(head)
                    if cand.is_expired(now):
                        dropped_or_expired += 1
                        continue
                    recovered = cand
                    break
            elif policy == SchedulingPolicy.LIFO:
                while not lifo_buf.is_empty():
                    cand = lifo_buf.pop()
                    if cand.is_expired(now):
                        dropped_or_expired += 1
                        continue
                    recovered = cand
                    break
            else:
                recovered, _, exp_cnt = prio_buf.pop(now)
                dropped_or_expired += exp_cnt

            if recovered is not None:
                delivered_ids.append(recovered.packet_id)
                if first_post_blackout_id is None and blackout_ended_at is not None:
                    first_post_blackout_id = recovered.packet_id
                age = now - recovered.created_at
                if age > stale_threshold_seconds:
                    stale_delivered += 1
                if recovered.priority == PacketPriority.CRITICAL:
                    critical_latencies.append(age)
                    if first_critical_latency is None and blackout_ended_at is not None:
                        first_critical_latency = round(age, 4)

            # Mevcut canlı paketi ilet
            if not pkt.is_expired(now):
                delivered_ids.append(pkt.packet_id)
                if pkt.priority == PacketPriority.CRITICAL:
                    critical_latencies.append(0.0)
            else:
                dropped_or_expired += 1

        total = len(workload)
        delivered_count = len(delivered_ids)
        loss_rate = round(dropped_or_expired / total, 4) if total > 0 else 0.0
        stale_rate = round(stale_delivered / delivered_count, 4) if delivered_count > 0 else 0.0
        avg_crit = (
            round(sum(critical_latencies) / len(critical_latencies), 4)
            if critical_latencies
            else 0.0
        )

        results[policy] = StrategyBenchmarkResult(
            policy=policy,
            total_packets=total,
            delivered_count=delivered_count,
            critical_delivered=len(critical_latencies),
            dropped_or_expired=dropped_or_expired,
            packet_loss_rate=loss_rate,
            first_post_blackout_packet_id=first_post_blackout_id,
            first_critical_recovery_latency=first_critical_latency,
            avg_critical_latency=avg_crit,
            stale_packet_rate=stale_rate,
            peak_buffer_occupancy=peak_occupancy,
            aged_promotions=prio_buf.aged_promotions,
            delivery_order_sample=tuple(delivered_ids[:10]),
        )

    return results