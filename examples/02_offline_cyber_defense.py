"""Demo 2: Offline cyber-attack defense with 1-byte tamper rollback."""

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "src"))

from astroq_link.engine import AutonomousEdgeShield


def run_demo() -> None:
    shield = AutonomousEdgeShield(passphrase="KritikAltyapiPQC2026!", ring_slots=4)

    scenarios = [
        (1, b"NODE_STATUS:ONLINE_NOMINAL_01", True, False),
        (2, b"NODE_STATUS:OFFLINE_AUTONOMOUS_02", False, False),
        (3, b"NODE_STATUS:INJECTED_MALICIOUS_03", False, True),
        (4, b"NODE_STATUS:INJECTED_MALICIOUS_04", False, True),
        (5, b"NODE_STATUS:OFFLINE_CLEAN_05", False, False),
        (6, b"NODE_STATUS:RECONNECTED_ONLINE_06", True, False),
    ]

    print("🛡️ AstroQ-Link: İnternet Kesintisi & Hibrit Siber Saldırı Savunma Demosu")
    print("=" * 84)

    for tick, payload, online, tamper in scenarios:
        res = shield.process_frame(
            tick=tick,
            payload=payload,
            internet_online=online,
            simulate_tamper=tamper,
        )
        print(
            f"T={tick:02d} | Mod: {res['mode']:<7} | Slot#{res['slot_id']} | Durum: {res['status']}"
        )

        flushed = res["flushed_alerts"]
        if isinstance(flushed, list) and flushed:
            for alert in flushed:
                print(f"   └── [📡 SOC LIFO BİLDİRİMİ] [{alert.severity}] {alert.description}")

    print("=" * 84)
    print(
        f"📊 ÖZET: İşlenen={shield.stats.frames_processed} | Çevrimdışı={shield.stats.offline_frames} | "
        f"Engellenen Saldırı={shield.stats.attacks_blocked} | Rollback={shield.stats.rollbacks_executed}"
    )


if __name__ == "__main__":
    run_demo()