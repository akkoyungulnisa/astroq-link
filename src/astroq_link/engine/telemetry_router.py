"""2000m rocket/satellite flight simulator with blackout and QBER noise injection."""

from dataclasses import dataclass
import math
import random
from typing import Optional

from astroq_link.core import (
    CircularDoublyLinkedList,
    CriticalLIFOStack,
    QuantumTelemetryPacket,
)


@dataclass
class MissionStats:
    total_generated: int = 0
    transmitted_live: int = 0
    buffered_in_stack: int = 0
    recovered_from_stack: int = 0
    dropped_overflow: int = 0
    link_switches: int = 0
    qber_breaches: int = 0


class TelemetryRouter:
    """
    2000m uçuş profili boyunca telemetri paketlerini sabit RAM'li
    CircularDoublyLinkedList tamponunda tutan, RF/Kuantum kesintilerinde
    yedek kanala O(1) geçiş yapan ve kritik paketleri CriticalLIFOStack
    üzerinden en güncel durumdan başlayarak kurtaran yönlendirici.
    """

    QBER_THRESHOLD: float = 0.11

    def __init__(self, ring_capacity: int = 16, stack_capacity: int = 32) -> None:
        self.onboard_ring: CircularDoublyLinkedList[QuantumTelemetryPacket] = (
            CircularDoublyLinkedList(max_capacity=ring_capacity, overwrite_on_full=True)
        )
        self.recovery_stack: CriticalLIFOStack[QuantumTelemetryPacket] = (
            CriticalLIFOStack(max_capacity=stack_capacity)
        )
        self.comm_links: CircularDoublyLinkedList[str] = CircularDoublyLinkedList()
        self.comm_links.append("RF-PRIMARY-915MHz")
        self.comm_links.append("RF-BACKUP-OMNI")
        self.comm_links.append("QKD-OPTICAL-LINK")

        self.stats = MissionStats()
        self.ground_station_log: CircularDoublyLinkedList[QuantumTelemetryPacket] = (
            CircularDoublyLinkedList()
        )

    @property
    def active_link(self) -> str:
        head = self.comm_links.get_head()
        return head.data if head is not None else "NONE"

    def switch_to_next_link(self) -> str:
        """Aktif haberleşme kanalı bozulduğunda O(1) sürede bir sonraki yedek kanala geçer."""
        self.comm_links.rotate_forward()
        self.stats.link_switches += 1
        return self.active_link

    def process_packet(
        self,
        packet: QuantumTelemetryPacket,
        link_online: bool = True,
    ) -> tuple[str, Optional[QuantumTelemetryPacket]]:
        """
        Gelen telemetri paketini işler:
        - Her paket sabit bellekli onboard_ring halkasına yazılır.
        - Bağlantı kesikse veya QBER sınırı aşıldıysa kritik paket LIFO yığınına alınır.
        - Bağlantı geri geldiğinde önce yığındaki EN GÜNCEL paket kurtarılır.
        """
        self.stats.total_generated += 1
        self.onboard_ring.append(packet)

        qber_breach = packet.qber > self.QBER_THRESHOLD
        if qber_breach:
            self.stats.qber_breaches += 1

        if not link_online or qber_breach or packet.is_critical:
            if not link_online or qber_breach:
                self.switch_to_next_link()
                if not self.recovery_stack.is_full():
                    self.recovery_stack.push(packet)
                    self.stats.buffered_in_stack += 1
                    reason = "BLACKOUT" if not link_online else "QBER_BREACH"
                    return (f"BUFFERED_{reason}", None)
                else:
                    self.stats.dropped_overflow += 1
                    return ("DROPPED_STACK_FULL", None)

        # Bağlantı sağlıklıysa önce Stack'te bekleyen en taze kritik durumu yer istasyonuna aktar
        recovered_pkt: Optional[QuantumTelemetryPacket] = None
        if not self.recovery_stack.is_empty():
            recovered_pkt = self.recovery_stack.pop()
            self.ground_station_log.append(recovered_pkt)
            self.stats.recovered_from_stack += 1

        self.ground_station_log.append(packet)
        self.stats.transmitted_live += 1
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
        dt = 1.5

        while altitude <= target_altitude:
            packet_id += 1
            # Yükseliş profili: başlangıçta yüksek ivme, tepe noktasına yaklaşırken yavaşlama
            progress = altitude / target_altitude
            velocity = round(max(12.0, 145.0 * (1.0 - 0.85 * progress)), 2)
            pressure = round(1013.25 * math.exp(-altitude / 8434.5), 2)

            in_blackout = blackout_range[0] <= altitude <= blackout_range[1]
            # 1600m civarında kuantum kanalda dinleme/gürültü sıçraması enjeksiyonu
            in_qber_spike = 1580.0 <= altitude <= 1620.0

            if in_qber_spike:
                qber = round(rng.uniform(0.14, 0.21), 3)
                status = "QUANTUM_BREACH"
                critical = True
            elif in_blackout:
                qber = round(rng.uniform(0.02, 0.05), 3)
                status = "RF_BLACKOUT"
                critical = True
            else:
                qber = round(rng.uniform(0.015, 0.045), 3)
                status = "NOMINAL"
                critical = altitude >= (target_altitude - 30.0)

            pkt = QuantumTelemetryPacket(
                packet_id=packet_id,
                altitude_m=round(altitude, 1),
                velocity_ms=velocity,
                pressure_hpa=pressure,
                qber=qber,
                is_critical=critical,
                status=status,
            )

            self.process_packet(pkt, link_online=(not in_blackout))
            altitude += velocity * dt

        return self.stats
