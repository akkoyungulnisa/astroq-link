"""Demo 1: 0m-2000m rocket ascent, 1900m blackout & QBER breach recovery."""

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "src"))

from astroq_link.engine import TelemetryRouter
from astroq_link.io import TelemetryExporter


def run_demo() -> None:
    router = TelemetryRouter(ring_capacity=16, stack_capacity=32)

    print("🚀 AstroQ-Link: 2000m Uçuş, Sinyal Kesintisi (Blackout) ve QBER Savunma Demosu")
    print("=" * 80)

    stats = router.simulate_ascent_mission(
        target_altitude=2000.0,
        blackout_range=(1880.0, 1940.0),
        seed=42,
    )

    csv_path = ROOT_DIR / "data" / "ground_station_verified.csv"
    exported_count = TelemetryExporter.export_telemetry_csv(router.ground_station_log, csv_path)

    print(f"Toplam Üretilen Paket     : {stats.total_generated}")
    print(f"Canlı İletilen Paket      : {stats.transmitted_live}")
    print(f"Kesintide Stack'e Alınan  : {stats.buffered_in_stack}")
    print(f"Stack'ten Kurtarılan      : {stats.recovered_from_stack}")
    print(f"QBER Sınır İhlali         : {stats.qber_breaches}")
    print(f"O(1) Yedek Kanal Geçişi   : {stats.link_switches}")
    print(f"Onboard Ring RAM Boyutu   : {router.onboard_ring.size} / {router.onboard_ring.max_capacity} düğüm (Sabit O(1))")
    print("=" * 80)
    print(f"✅ Yer istasyonu CSV çıktısı oluşturuldu ({exported_count} paket): {csv_path}")


if __name__ == "__main__":
    run_demo()
