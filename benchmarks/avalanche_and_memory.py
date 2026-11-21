"""Benchmark measuring cryptographic avalanche effect (%) and O(1) memory footprint."""

from pathlib import Path
import sys
import tempfile
import tracemalloc

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "src"))

from astroq_link.core import CircularDoublyLinkedList, QuantumTelemetryPacket
from astroq_link.crypto import PQCFileVault


def benchmark_avalanche_and_ram() -> None:
    vault = PQCFileVault(passphrase="AvalancheBenchmarkKey2026!")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        file_a = tmp / "input_a.bin"
        file_b = tmp / "input_b.bin"
        enc_a = tmp / "out_a.pqc"
        enc_b = tmp / "out_b.pqc"

        # 4 KB veri üret ve ikinci dosyada SADECE 1 biti değiştir
        base_data = bytearray(b"ASTROQ_TELEMETRY_STREAM_BLOCK_01" * 128)
        modified_data = bytearray(base_data)
        modified_data[0] ^= 0x01  # Tek bit fark!

        file_a.write_bytes(bytes(base_data))
        file_b.write_bytes(bytes(modified_data))

        vault.encrypt_file(file_a, enc_a)
        vault.encrypt_file(file_b, enc_b)

        cipher_a = enc_a.read_bytes()
        cipher_b = enc_b.read_bytes()
        avalanche_pct = PQCFileVault.compute_avalanche_ratio(cipher_a, cipher_b)

    # Sabit kapasiteli CircularDoublyLinkedList bellek ayak izi testi (50.000 paket akışı)
    tracemalloc.start()
    ring: CircularDoublyLinkedList[QuantumTelemetryPacket] = CircularDoublyLinkedList(
        max_capacity=32, overwrite_on_full=True
    )
    for i in range(50_000):
        ring.append(QuantumTelemetryPacket(i, 1500.0, 40.0, 845.0, 0.02, False, "NOMINAL"))
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    print("📊 Benchmark 2: Kriptografik Çığ Etkisi (Avalanche) & Sabit O(1) RAM Ölçümü")
    print("=" * 78)
    print(f"Girdi Farkı                      : 4.096 bayt içinde yalnızca 1 bit (0.003%)")
    print(f"Şifreli Çıktı Bit Değişimi       : %{avalanche_pct:.2f} (İdeal kriptografik eşik: ~%50.0)")
    print(f"50.000 Paket Akışında Tepe RAM   : {peak_bytes / 1024:.2f} KB (Kapasite: {ring.size} düğüm sabit)")
    print("=" * 78)


if __name__ == "__main__":
    benchmark_avalanche_and_ram()
