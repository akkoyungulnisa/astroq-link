"""Benchmark comparing FIFO Queue vs. LIFO Stack latency after signal blackout."""

from collections import deque
from pathlib import Path
import sys
import time

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "src"))

from astroq_link.core import CriticalLIFOStack, QuantumTelemetryPacket


def benchmark_blackout_recovery(packet_count: int = 10_000) -> None:
    packets = [
        QuantumTelemetryPacket(
            packet_id=i,
            altitude_m=1800.0 + (i * 0.02),
            velocity_ms=35.0,
            pressure_hpa=810.0,
            qber=0.03,
            is_critical=(i == packet_count - 1),
            status="BLACKOUT_BUFFERED",
        )
        for i in range(packet_count)
    ]

    # 1. Klasik FIFO Kuyruk: En son/en güncel pakete ulaşmak için tüm kuyruğu boşaltmak gerekir (O(N))
    fifo_queue: deque[QuantumTelemetryPacket] = deque(packets)
    t0 = time.perf_counter()
    latest_from_fifo = None
    while fifo_queue:
        latest_from_fifo = fifo_queue.popleft()
    fifo_elapsed_us = (time.perf_counter() - t0) * 1_000_000

    # 2. AstroQ CriticalLIFOStack: En güncel paket doğrudan tepededir (O(1))
    lifo_stack: CriticalLIFOStack[QuantumTelemetryPacket] = CriticalLIFOStack()
    for pkt in packets:
        lifo_stack.push(pkt)

    t1 = time.perf_counter()
    latest_from_lifo = lifo_stack.pop()
    lifo_elapsed_us = (time.perf_counter() - t1) * 1_000_000

    assert latest_from_fifo is not None and latest_from_lifo is not None
    assert latest_from_fifo.packet_id == latest_from_lifo.packet_id

    speedup = fifo_elapsed_us / max(lifo_elapsed_us, 0.001)

    print("⏱️ Benchmark 1: Kesinti Sonrası En Güncel Kritik Veriye Erişim (FIFO vs. LIFO)")
    print("=" * 78)
    print(f"Tamponlanan Paket Sayısı         : {packet_count:,}")
    print(f"FIFO Queue Erişim Süresi (O(N))  : {fifo_elapsed_us:10.2f} µs")
    print(f"CriticalLIFOStack Süresi (O(1))  : {lifo_elapsed_us:10.2f} µs")
    print(f"Hızlanma Çarpanı                 : {speedup:10.1f}x daha hızlı ilk kritik yanıt")
    print("=" * 78)


if __name__ == "__main__":
    benchmark_blackout_recovery()
